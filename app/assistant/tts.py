"""Modul sintesis suara TTS (Fase 2 - Sesi 2).

Menerapkan arsitektur hybrid 2-tier sesuai ADR-033:
- Tier 1 (Primer): edge-tts (id-ID-GadisNeural) untuk sintesis neural alami,
  latensi rendah, dan beban CPU/GPU server mendekati 0%.
- Tier 2 (Fallback Offline): sherpa-onnx (model lokal ONNX bahasa Indonesia)
  yang aktif secara otomatis jika koneksi internet terputus atau edge-tts gagal.

Hasil sintesis disimpan secara statis di static/tts/ dengan penamaan hash
deterministik sha256(voice + text), sehingga request berulang otomatis
memanfaatkan cache disk (0 overhead sintesis ulang).
"""

import asyncio
import hashlib
import os
from pathlib import Path

import edge_tts
try:
    import sherpa_onnx
except ImportError:
    sherpa_onnx = None  # type: ignore

DEFAULT_VOICE = "id-ID-GadisNeural"
STATIC_TTS_DIR = Path(os.environ.get("TTS_OUTPUT_DIR", "static/tts"))
EDGE_TTS_TIMEOUT_SECONDS = int(os.environ.get("EDGE_TTS_TIMEOUT_SECONDS", "15"))

# Konfigurasi model Sherpa-ONNX lokal (opsional via ENV)
SHERPA_VITS_MODEL = os.environ.get("SHERPA_ONNX_VITS_MODEL", "")
SHERPA_VITS_LEXICON = os.environ.get("SHERPA_ONNX_VITS_LEXICON", "")
SHERPA_VITS_TOKENS = os.environ.get("SHERPA_ONNX_VITS_TOKENS", "")
SHERPA_VITS_DATA_DIR = os.environ.get("SHERPA_ONNX_VITS_DATA_DIR", "")

_sherpa_tts_instance = None


def get_audio_hash(text: str, voice: str) -> str:
    """Menghasilkan hash deterministik sepanjang 16 karakter untuk teks dan voice."""
    payload = f"{voice}:{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


async def _synthesize_edge_tts(text: str, voice: str, output_path: Path) -> None:
    """Tier 1: Sintesis suara menggunakan Microsoft Edge Neural Voice."""
    communicate = edge_tts.Communicate(text, voice)
    await asyncio.wait_for(
        communicate.save(str(output_path)),
        timeout=EDGE_TTS_TIMEOUT_SECONDS,
    )


def _get_sherpa_tts():
    """Menginisialisasi engine sherpa-onnx jika dependensi dan model tersedia."""
    global _sherpa_tts_instance
    if _sherpa_tts_instance is not None:
        return _sherpa_tts_instance

    if sherpa_onnx is None:
        raise RuntimeError("Paket sherpa-onnx tidak terpasang di sistem.")

    if not SHERPA_VITS_MODEL or not os.path.exists(SHERPA_VITS_MODEL):
        raise RuntimeError(
            f"Model Sherpa-ONNX Vits tidak ditemukan pada path '{SHERPA_VITS_MODEL}'. "
            "Set SHERPA_ONNX_VITS_MODEL ke path file ONNX valid."
        )

    config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                model=SHERPA_VITS_MODEL,
                lexicon=SHERPA_VITS_LEXICON,
                tokens=SHERPA_VITS_TOKENS,
                data_dir=SHERPA_VITS_DATA_DIR,
            ),
            num_threads=2,
            provider="cpu",
        )
    )
    if not config.validate():
        raise RuntimeError("Konfigurasi Sherpa-ONNX tidak valid.")

    _sherpa_tts_instance = sherpa_onnx.OfflineTts(config)
    return _sherpa_tts_instance


def _synthesize_sherpa_onnx(text: str, output_path: Path) -> None:
    """Tier 2: Sintesis suara offline lokal menggunakan model Sherpa-ONNX."""
    tts_engine = _get_sherpa_tts()
    audio = tts_engine.generate(text, sid=0, speed=1.0)
    if len(audio.samples) == 0:
        raise RuntimeError("Sherpa-ONNX menghasilkan buffer audio kosong.")
    sherpa_onnx.write_wave(str(output_path), audio.samples, audio.sample_rate)


async def synthesize_speech(
    text: str,
    voice: str = DEFAULT_VOICE,
    output_dir: Path | None = None,
) -> tuple[str, str]:
    """Sintesis ucapan dari teks menggunakan mekanisme 2-Tier Fallback.

    Mengembalikan tuple (filename, engine_used).
    Jika file audio dengan hash teks & voice sudah ada di disk, langsung dikembalikan (cache).
    """
    if not text or not text.strip():
        raise ValueError("Teks untuk sintesis suara tidak boleh kosong.")

    target_dir = output_dir or STATIC_TTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    file_base = get_audio_hash(text.strip(), voice)
    mp3_path = target_dir / f"{file_base}.mp3"
    wav_path = target_dir / f"{file_base}.wav"

    # 1. Cek Cache Disk
    if mp3_path.exists() and mp3_path.stat().st_size > 0:
        return f"{file_base}.mp3", "edge-tts"
    if wav_path.exists() and wav_path.stat().st_size > 0:
        return f"{file_base}.wav", "sherpa-onnx"

    e_edge: Exception | None = None
    e_sherpa: Exception | None = None

    # 2. Tier 1: Coba Edge-TTS
    try:
        await _synthesize_edge_tts(text.strip(), voice, mp3_path)
        if mp3_path.exists() and mp3_path.stat().st_size > 0:
            return f"{file_base}.mp3", "edge-tts"
    except Exception as exc:
        e_edge = exc
        if mp3_path.exists():
            mp3_path.unlink(missing_ok=True)

    # 3. Tier 2: Fallback ke Sherpa-ONNX Offline
    try:
        _synthesize_sherpa_onnx(text.strip(), wav_path)
        if wav_path.exists() and wav_path.stat().st_size > 0:
            return f"{file_base}.wav", "sherpa-onnx"
    except Exception as exc:
        e_sherpa = exc
        if wav_path.exists():
            wav_path.unlink(missing_ok=True)

    # 4. Kedua Tier Gagal
    raise RuntimeError(
        f"Edge-TTS gagal ({e_edge}) dan Sherpa-ONNX fallback juga gagal ({e_sherpa})"
    )
