"""Susun prompt lalu panggil LLM: Bifrost (medgemma, GPU eksternal) primer, Groq fallback.

Rencana sebelumnya (Qwen lokal via Ollama di server `vm-amma`) DIBATALKAN --
`vm-amma` terverifikasi (lspci) TIDAK punya GPU sama sekali, cuma 2 vCPU, jadi
inferensi 7B CPU-only akan selalu timeout dan jatuh ke Groq. Lihat memori
`vm-amma-no-gpu-pending-decision`.

Bifrost adalah gateway OpenAI-compatible yang di-host TERPISAH (hcm-lab.id,
GPU sungguhan, dikelola tim PSDKU/HCM), bukan service di docker-compose ini --
jadi tidak butuh GPU di `vm-amma` sama sekali. Modelnya (medgemma) di-tuning
domain medis, relevan untuk asisten RS dibanding Groq yang general-purpose.

Groq tetap dipanggil dari SERVER, bukan dari APK -- ini menutup utang keamanan
yang tercatat di OllamaConnector.cs (key ikut ter-bundle ke APK kalau dipanggil
dari client). Prinsip yang sama berlaku untuk BIFROST_API_KEY.
"""

import os

import httpx

from app.assistant.models import RetrievedChunk, ScheduleRow

# Bifrost: gateway eksternal (bukan service Docker lokal), auth via header
# "x-api-key" (bukan "Authorization: Bearer" seperti Groq -- format gateway ini
# memang beda, dikonfirmasi dari contoh curl yang diberikan tim HCM Lab).
BIFROST_URL = os.environ.get("BIFROST_URL", "https://bifrost.hcm-lab.id/v1/chat/completions")
# medgemma menghasilkan reasoning trace panjang sebelum "content" (terukur
# langsung: prompt realistis satu chunk = 14.7 detik, "Halo AI!" saja = 9.3
# detik). 20 detik (nilai lama Groq) terlalu mepet kalau chunk+jadwal lebih
# banyak; 30 detik ngasih ruang tanpa bikin user menunggu lama saat jatuh ke
# Groq (fallback tetap kena kalau Bifrost benar-benar mati/timeout).
BIFROST_MODEL = os.environ.get("BIFROST_MODEL", "llama.cpp/medgemma-1.5-4b-it-q4")
BIFROST_TIMEOUT_SECONDS = 30

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# Sama dengan yang dipakai OllamaConnector.cs. llama-3.1-8b-instant dihentikan Groq
# untuk free/developer tier per 2026-08-16 (balas 404 kalau dipakai).
GROQ_MODEL = "openai/gpt-oss-20b"
GROQ_TIMEOUT_SECONDS = 20

NO_CONTEXT_ANSWER = (
    "Maaf, saya tidak punya informasi soal itu. Silakan tanyakan ke petugas "
    "Informasi di Lantai 1."
)

_HARI = {1: "Senin", 2: "Selasa", 3: "Rabu", 4: "Kamis",
         5: "Jumat", 6: "Sabtu", 7: "Minggu"}

_SYSTEM_PROMPT = """Kamu asisten informasi RS Islam A. Yani.

Aturan:
- Jawab HANYA berdasarkan informasi di bawah. Jangan mengarang apa pun yang tidak ada di sana.
- TRIASE GAWAT DARURAT: Jika pengguna menyebutkan kondisi gawat darurat atau kecelakaan (misal tertabrak motor/mobil, tabrakan, pendarahan, patah tulang, luka parah, pingsan, kejang, demam tinggi/step anak, sesak napas akut, nyeri dada), WAJIB langsung mengarahkan pasien untuk segera menuju ke IGD di Lantai 1 tanpa perlu menunggu pendaftaran poli.
- WAYFINDING & LOKASI: Jika pertanyaan menanyakan tempat, fasilitas, ATAU jadwal praktek dokter/poliklinik (misal toilet, farmasi, kasir, radiologi, rontgen, musholla, kantin, lift, parkir mobil/motor, jadwal dokter, poli), sebutkan nama lokasi dan lantainya dengan jelas di awal jawaban -- termasuk lantai poli kalau informasinya tersedia di JADWAL PRAKTEK DOKTER.
- Jika informasinya tidak cukup, katakan terus terang dan arahkan ke petugas Informasi di Lantai 1.
- Pertanyaan di luar urusan rumah sakit (resep masakan, cuaca, jadwal kereta, dll): tolak dengan santun dan tegaskan kamu hanya melayani informasi RS Islam A. Yani. JANGAN sebutkan nama lokasi/lantai/POI apa pun (misal "Lantai 1", "petugas Informasi") di jawaban penolakan ini -- itu cuma relevan untuk pertanyaan yang sungguhan tentang RS.
- Jawab ringkas, jelas, dan santun dalam Bahasa Indonesia, maksimal 3 kalimat.
- Jangan menyebutkan ID teknis atau istilah kode internal kepada pengguna."""


def build_prompt(
    user_text: str,
    chunks: list[RetrievedChunk],
    schedules: list[ScheduleRow],
) -> str:
    """Rakit prompt dari konteks hasil retrieval.

    Sengaja gagal kalau tidak ada konteks sama sekali: meneruskan pertanyaan ke LLM
    tanpa bahan justru mengundang jawaban karangan, dan di konteks RS itu berbahaya.
    GUID POI tidak pernah dimasukkan ke prompt (lihat models.derive_poi).
    """
    if not chunks and not schedules:
        raise ValueError("tidak boleh menyusun prompt tanpa konteks")

    bagian: list[str] = [_SYSTEM_PROMPT, "", "INFORMASI:"]

    for c in chunks:
        bagian.append(f"- [{c.title}] {c.content}")

    if schedules:
        bagian.append("")
        bagian.append("JADWAL PRAKTEK DOKTER:")
        for s in schedules:
            lokasi = f", {s.floor}" if s.floor else ""
            bagian.append(
                f"- {s.doctor_name} ({s.specialty}{lokasi}), "
                f"{_HARI[s.day_of_week]} {s.start_time}-{s.end_time}"
            )

    bagian.append("")
    bagian.append(f"PERTANYAAN: {user_text}")
    bagian.append("JAWABAN:")
    return "\n".join(bagian)


def generate_answer(prompt: str) -> str:
    """Coba Bifrost (medgemma) dulu, Groq kalau gagal. Melempar RuntimeError hanya
    kalau DUA-DUANYA gagal, biar penanganannya (503) tetap di router seperti sebelumnya.
    """
    try:
        return _try_bifrost(prompt)
    except Exception as e_bifrost:
        try:
            return _try_groq(prompt)
        except Exception as e_groq:
            raise RuntimeError(
                f"Bifrost gagal ({e_bifrost}) dan Groq fallback juga gagal ({e_groq})"
            ) from e_groq


def _try_bifrost(prompt: str) -> str:
    api_key = os.environ.get("BIFROST_API_KEY", "")
    if not api_key:
        raise RuntimeError("BIFROST_API_KEY kosong")

    resp = httpx.post(
        BIFROST_URL,
        headers={"x-api-key": api_key},
        json={
            "model": BIFROST_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        },
        timeout=BIFROST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _try_groq(prompt: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY kosong")

    resp = httpx.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        },
        timeout=GROQ_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()
