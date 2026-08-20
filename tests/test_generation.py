import pytest

from app.assistant.generation import NO_CONTEXT_ANSWER, build_prompt
from app.assistant.models import RetrievedChunk, ScheduleRow


def _chunk(title="Layanan Farmasi", content="Farmasi buka 07.00 sampai 21.00."):
    return RetrievedChunk(
        content=content, title=title, doc_type="layanan", poi_unity_id=None,
        poi_name=None, floor="Lantai 1", is_simulated=True, score=0.8,
    )


def _sched():
    return ScheduleRow(
        doctor_name="dr. Fulan Hidayat, Sp.A", specialty="Anak", day_of_week=1,
        start_time="08:00", end_time="14:00", poi_unity_id=None, is_simulated=True,
    )


def test_prompt_memuat_isi_chunk():
    prompt = build_prompt("farmasi buka jam berapa", [_chunk()], [])
    assert "Farmasi buka 07.00 sampai 21.00." in prompt


def test_prompt_memuat_pertanyaan_user():
    prompt = build_prompt("farmasi buka jam berapa", [_chunk()], [])
    assert "farmasi buka jam berapa" in prompt


def test_prompt_memuat_jadwal_dalam_bentuk_terbaca():
    prompt = build_prompt("dokter anak kapan", [], [_sched()])
    assert "dr. Fulan Hidayat, Sp.A" in prompt
    assert "Senin" in prompt
    assert "08:00" in prompt


def test_prompt_melarang_mengarang():
    prompt = build_prompt("apa saja", [_chunk()], [])
    assert "jangan mengarang" in prompt.lower()


def test_prompt_tidak_pernah_memuat_guid():
    """poi_id diturunkan dari metadata, LLM tidak boleh diminta menghasilkannya."""
    c = _chunk()
    c.poi_unity_id = "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"
    prompt = build_prompt("di mana farmasi", [c], [])
    assert "9b1deb4d" not in prompt


def test_tanpa_konteks_sama_sekali_menolak_tanpa_memanggil_llm():
    with pytest.raises(ValueError, match="tanpa konteks"):
        build_prompt("pertanyaan di luar cakupan", [], [])


def test_pesan_penolakan_tersedia_dan_jujur():
    assert "tidak" in NO_CONTEXT_ANSWER.lower()
