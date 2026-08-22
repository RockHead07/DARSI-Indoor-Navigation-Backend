"""Susun prompt lalu panggil Groq.

Groq dipanggil dari SERVER, bukan dari APK. Ini menutup utang keamanan yang sudah
tercatat di Assets/Speech Recognition/OllamaConnector.cs di repo Unity: kalau
dipanggil dari client, groqApiKey ikut ter-bundle ke APK dan bisa diekstrak
siapa pun yang men-decompile-nya.
"""

import os

import httpx

from app.assistant.models import RetrievedChunk, ScheduleRow

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
    """Panggil Groq. Melempar RuntimeError kalau gagal, biar penanganannya di router."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY kosong")

    try:
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
    except Exception as e:
        raise RuntimeError(f"Groq gagal: {e}") from e
