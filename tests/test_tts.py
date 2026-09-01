"""Unit tests untuk endpoint dan modul TTS (Fase 2 - Sesi 2).

Menguji:
1. Validasi request model & default voice
2. Hash deterministik & audio file naming
3. Sintesis Tier 1 (edge-tts)
4. Fallback otomatis ke Tier 2 (sherpa-onnx) saat Tier 1 gagal
5. Penanganan kegagalan jika kedua engine gagal (HTTP 503)
6. Static file serving (/static/tts/...)
7. Audio caching (tidak melakukan sintesis ulang jika file sudah ada)
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.assistant.models import AssistantTTSRequest, AssistantTTSResponse
from app.assistant.tts import (
    DEFAULT_VOICE,
    get_audio_hash,
    synthesize_speech,
)
from app.main import app


@pytest.fixture
def client():
    # Menggunakan TestClient FastAPI untuk menguji endpoint
    return TestClient(app)


@pytest.fixture
def temp_tts_dir(tmp_path):
    # Direktori sementara untuk isolasi pengujian sintesis audio
    tts_dir = tmp_path / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)
    return tts_dir


def test_request_model_validasi_dan_default():
    # Validasi default voice dan batasan panjang teks
    req = AssistantTTSRequest(text="Halo ini uji coba")
    assert req.voice == DEFAULT_VOICE
    assert req.text == "Halo ini uji coba"

    with pytest.raises(ValidationError):
        AssistantTTSRequest(text="")

    with pytest.raises(ValidationError):
        AssistantTTSRequest(text="a" * 1001)


def test_audio_hash_deterministik():
    # Teks dan voice yang sama harus menghasilkan hash identik
    h1 = get_audio_hash("Poli Anak di Lantai 2", "id-ID-GadisNeural")
    h2 = get_audio_hash("Poli Anak di Lantai 2", "id-ID-GadisNeural")
    assert h1 == h2
    assert len(h1) == 16

    # Voice atau teks berbeda harus menghasilkan hash berbeda
    h3 = get_audio_hash("Poli Anak di Lantai 2", "id-ID-ArdiNeural")
    assert h1 != h3

    h4 = get_audio_hash("Poli Bedah di Lantai 3", "id-ID-GadisNeural")
    assert h1 != h4


@pytest.mark.anyio
async def test_caching_audio_tidak_sintesis_ulang(temp_tts_dir):
    # Jika file audio sudah ada, kembalikan langsung tanpa memanggil backend TTS
    text = "Uji coba cache TTS"
    voice = "id-ID-GadisNeural"
    file_base = get_audio_hash(text, voice)
    dummy_file = temp_tts_dir / f"{file_base}.mp3"
    dummy_file.write_bytes(b"dummy mp3 data")

    with patch("app.assistant.tts._synthesize_edge_tts") as mock_edge, \
         patch("app.assistant.tts._synthesize_sherpa_onnx") as mock_sherpa:
        filename, engine = await synthesize_speech(text, voice=voice, output_dir=temp_tts_dir)
        assert filename == f"{file_base}.mp3"
        assert engine == "edge-tts"
        mock_edge.assert_not_called()
        mock_sherpa.assert_not_called()


@pytest.mark.anyio
async def test_synthesize_tier1_edge_tts_sukses(temp_tts_dir):
    text = "Tes sintesis edge-tts"
    voice = "id-ID-GadisNeural"
    file_base = get_audio_hash(text, voice)
    expected_path = temp_tts_dir / f"{file_base}.mp3"

    async def fake_edge_tts(t, v, out_path):
        out_path.write_bytes(b"fake edge tts mp3")

    with patch("app.assistant.tts._synthesize_edge_tts", side_effect=fake_edge_tts) as mock_edge:
        filename, engine = await synthesize_speech(text, voice=voice, output_dir=temp_tts_dir)
        assert filename == f"{file_base}.mp3"
        assert engine == "edge-tts"
        assert expected_path.exists()
        assert expected_path.read_bytes() == b"fake edge tts mp3"
        mock_edge.assert_called_once()


@pytest.mark.anyio
async def test_fallback_ke_tier2_sherpa_onnx_saat_edge_tts_gagal(temp_tts_dir):
    text = "Tes fallback offline"
    voice = "id-ID-GadisNeural"
    file_base = get_audio_hash(text, voice)
    expected_path = temp_tts_dir / f"{file_base}.wav"

    def fake_sherpa(t, out_path):
        out_path.write_bytes(b"fake sherpa onnx wav")

    with patch("app.assistant.tts._synthesize_edge_tts", side_effect=RuntimeError("Edge-TTS connection timeout")), \
         patch("app.assistant.tts._synthesize_sherpa_onnx", side_effect=fake_sherpa) as mock_sherpa:
        filename, engine = await synthesize_speech(text, voice=voice, output_dir=temp_tts_dir)
        assert filename == f"{file_base}.wav"
        assert engine == "sherpa-onnx"
        assert expected_path.exists()
        assert expected_path.read_bytes() == b"fake sherpa onnx wav"
        mock_sherpa.assert_called_once()


@pytest.mark.anyio
async def test_kedua_engine_gagal_melempar_runtime_error(temp_tts_dir):
    text = "Tes kegagalan total"
    voice = "id-ID-GadisNeural"

    with patch("app.assistant.tts._synthesize_edge_tts", side_effect=RuntimeError("Edge-TTS DNS error")), \
         patch("app.assistant.tts._synthesize_sherpa_onnx", side_effect=RuntimeError("Sherpa model not loaded")):
        with pytest.raises(RuntimeError) as exc_info:
            await synthesize_speech(text, voice=voice, output_dir=temp_tts_dir)
        assert "Edge-TTS gagal" in str(exc_info.value)
        assert "Sherpa-ONNX fallback juga gagal" in str(exc_info.value)


def test_endpoint_tts_validasi_payload_kosong(client):
    resp = client.post("/api/assistant/tts", json={"text": ""})
    assert resp.status_code == 422


def test_endpoint_tts_sukses_mengembalikan_audio_url_dan_engine(client):
    text = "Poli Anak berada di Lantai 2"
    
    async def fake_synthesize(text, voice, output_dir):
        file_base = get_audio_hash(text, voice)
        target = output_dir / f"{file_base}.mp3"
        target.write_bytes(b"ID3dummy")
        return f"{file_base}.mp3", "edge-tts"

    with patch("app.assistant.router.synthesize_speech", side_effect=fake_synthesize):
        resp = client.post("/api/assistant/tts", json={"text": text})
        assert resp.status_code == 200
        data = resp.json()
        assert "audio_url" in data
        assert "engine_used" in data
        assert data["engine_used"] == "edge-tts"
        assert data["audio_url"].endswith(".mp3")
        assert "/static/tts/" in data["audio_url"]


def test_endpoint_tts_503_saat_sintesis_gagal(client):
    with patch("app.assistant.router.synthesize_speech", side_effect=RuntimeError("Both TTS engines failed")):
        resp = client.post("/api/assistant/tts", json={"text": "Tes error"})
        assert resp.status_code == 503
        assert "detail" in resp.json()


def test_static_audio_file_dapat_diunduh_via_get(client):
    # Verifikasi bahwa file audio yang disimpan di static/tts/ dapat diakses via GET
    text = "Tes unduh static audio"
    voice = DEFAULT_VOICE
    file_base = get_audio_hash(text, voice)
    static_tts_dir = Path("static/tts")
    static_tts_dir.mkdir(parents=True, exist_ok=True)
    test_file = static_tts_dir / f"{file_base}.mp3"
    test_file.write_bytes(b"\xFF\xFB\x90\x44" + b"\x00" * 100)  # Dummy MP3 frame header

    try:
        resp = client.get(f"/static/tts/{file_base}.mp3")
        assert resp.status_code == 200
        assert len(resp.content) > 0
    finally:
        if test_file.exists():
            test_file.unlink(missing_ok=True)


@pytest.mark.anyio
async def test_live_edge_tts_synthesis(temp_tts_dir):
    # Pengujian langsung ke layanan Edge-TTS (Tier 1) untuk memastikan payload audio valid
    text = "Poli Anak di Lantai 2"
    filename, engine = await synthesize_speech(text, voice="id-ID-GadisNeural", output_dir=temp_tts_dir)
    assert engine == "edge-tts"
    assert filename.endswith(".mp3")
    audio_file = temp_tts_dir / filename
    assert audio_file.exists()
    assert audio_file.stat().st_size > 1000  # File MP3 asli memiliki ukuran valid (> 1 KB)

