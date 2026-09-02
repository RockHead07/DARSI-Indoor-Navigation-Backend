FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FASTEMBED_CACHE_PATH=/app/.fastembed_cache

WORKDIR /app

# Install system dependencies needed for building packages / healthchecks
# bzip2 WAJIB: python:3.11-slim tidak menyertakannya secara default, tapi model
# TTS Tier 2 di bawah dikompres .tar.bz2 -- tanpa ini "tar xj" gagal exec bzip2.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    bzip2 \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Model TTS Tier 2 offline (ADR-033 Amandemen 033-C): vits-piper-id_ID-news_tts-medium
# dari rilis resmi sherpa-onnx, dipilih karena SATU-SATUNYA suara Indonesia siap-pakai
# di ekosistem itu saat ini. Diunduh SAAT BUILD (bukan runtime/volume terpisah) supaya
# image self-contained -- pola yang sama dengan FastEmbed di bawah, cuma FastEmbed
# unduh sendiri saat runtime pertama kali sedangkan model TTS ini dipastikan sudah ada
# sebelum kontainer jalan (Tier 2 harus tetap bisa dipakai walau internet server putus
# SETELAH kontainer start, jadi tidak boleh bergantung unduhan runtime).
#
# CATATAN LISENSI (jangan hapus tanpa baca ADR-033 Amandemen 033-C dulu): metadata
# provenance suara ini di sumber resminya (rhasspy/piper-voices) tercampur dengan
# suara Malayalam lain -- lisensi persisnya TIDAK bisa diverifikasi bersih. Diterima
# sadar untuk Tier 2 (cadangan jarang aktif), BUKAN untuk jadi suara utama.
RUN mkdir -p /app/models/vits-id && \
    curl -sL "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-id_ID-news_tts-medium-int8.tar.bz2" \
    | tar xj -C /app/models/vits-id --strip-components=1 && \
    test -f /app/models/vits-id/id_ID-news_tts-medium.onnx

# Create cache directory for FastEmbed weights and static TTS output
RUN mkdir -p /app/.fastembed_cache /app/static/tts

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
