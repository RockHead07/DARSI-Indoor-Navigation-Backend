"""Susun prompt lalu panggil LLM: Qwen lokal (Ollama) primer, Groq fallback.

Peran ini TERBALIK dari pola OllamaConnector.cs di repo Unity (ADR-024, Groq
primer/Ollama fallback) -- dan itu memang benar, bukan inkonsistensi. Di sana
Ollama LAN developer tidak terjangkau dari lapangan, jadi harus jadi fallback.
Di sini Ollama jalan satu Docker network dengan backend ini sendiri (lihat
docker-compose.yml), selalu terjangkau, gratis, dan tanpa API key. Groq jadi
jaring pengaman kalau Qwen gagal/timeout/model belum tertarik.

Groq tetap dipanggil dari SERVER, bukan dari APK -- ini menutup utang keamanan
yang tercatat di OllamaConnector.cs (key ikut ter-bundle ke APK kalau dipanggil
dari client).
"""

import os

import httpx

from app.assistant.models import RetrievedChunk, ScheduleRow

# Qwen lokal via Ollama (OpenAI-compatible endpoint). URL-nya nama service Docker
# ("ollama"), BUKAN localhost -- localhost di dalam kontainer api adalah kontainer
# itu sendiri, bukan host tempat Ollama jalan.
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434").rstrip("/") + "/v1/chat/completions"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
# Lebih longgar dari Groq: request pertama setelah container idle bisa kena cold
# load ke VRAM. Pre-warm di startup (lihat prewarm_ollama) biasanya menghindari ini.
OLLAMA_TIMEOUT_SECONDS = 30

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
- WAYFINDING & LOKASI: Jika pertanyaan menanyakan tempat atau fasilitas (misal toilet, farmasi, kasir, radiologi, rontgen, musholla, kantin, lift, parkir mobil/motor), sebutkan nama lokasi dan lantainya dengan jelas di awal jawaban.
- Jika informasinya tidak cukup, katakan terus terang dan arahkan ke petugas Informasi di Lantai 1.
- Pertanyaan di luar urusan rumah sakit (resep masakan, cuaca, jadwal kereta, dll): tolak dengan santun dan tegaskan kamu hanya melayani informasi RS Islam A. Yani.
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
            bagian.append(
                f"- {s.doctor_name} ({s.specialty}), "
                f"{_HARI[s.day_of_week]} {s.start_time}-{s.end_time}"
            )

    bagian.append("")
    bagian.append(f"PERTANYAAN: {user_text}")
    bagian.append("JAWABAN:")
    return "\n".join(bagian)


def generate_answer(prompt: str) -> str:
    """Coba Qwen lokal dulu, Groq kalau gagal. Melempar RuntimeError hanya kalau
    DUA-DUANYA gagal, biar penanganannya (503) tetap di router seperti sebelumnya.
    """
    try:
        return _try_ollama(prompt)
    except Exception as e_ollama:
        try:
            return _try_groq(prompt)
        except Exception as e_groq:
            raise RuntimeError(
                f"Ollama gagal ({e_ollama}) dan Groq fallback juga gagal ({e_groq})"
            ) from e_groq


def _try_ollama(prompt: str) -> str:
    resp = httpx.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        },
        timeout=OLLAMA_TIMEOUT_SECONDS,
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


def prewarm_ollama() -> None:
    """Panggilan dummy di startup biar Qwen sudah termuat ke VRAM sebelum request
    pertama sungguhan (pola sama seperti OllamaConnector.PreWarmModel di Unity).

    Best-effort, TIDAK melempar exception. Ollama mungkin masih menarik image
    container atau modelnya belum ditarik manual (langkah sekali jalan, lihat
    README) -- itu bukan alasan menggagalkan startup service, karena Groq
    fallback tetap menutupi sampai Qwen siap.
    """
    try:
        httpx.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": "hi"}],
                "temperature": 0,
            },
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        print(f"[startup] Ollama ({OLLAMA_MODEL}) siap.")
    except Exception as e:
        print(f"[startup] Ollama pre-warm gagal ({e}). Groq fallback dipakai sampai Qwen siap.")
