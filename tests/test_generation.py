import pytest

from app.assistant.generation import NO_CONTEXT_ANSWER, build_prompt
from app.assistant.models import RetrievedChunk, ScheduleRow


def _chunk(title="Layanan Farmasi", content="Farmasi buka 07.00 sampai 21.00."):
    return RetrievedChunk(
        content=content, title=title, doc_type="layanan", poi_unity_id=None,
        poi_name=None, floor="Lantai 1", is_simulated=True, score=0.8,
    )


def _sched(floor=None):
    return ScheduleRow(
        doctor_name="dr. Fulan Hidayat, Sp.A", specialty="Anak", day_of_week=1,
        start_time="08:00", end_time="14:00", poi_unity_id=None, is_simulated=True,
        floor=floor,
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


def test_prompt_jadwal_menyertakan_lantai_kalau_ada():
    """Regresi: jadwal dokter tanpa lantai bikin LLM tidak pernah sebut lokasi
    poli (bug ditemukan lewat eval_llm_judge -- 4 dari 4 kegagalan Poliklinik
    di dua run berbeda gara-gara ini)."""
    prompt = build_prompt("dokter anak kapan", [], [_sched(floor="Lantai 2")])
    assert "Lantai 2" in prompt


def test_prompt_jadwal_tanpa_lantai_tidak_error():
    prompt = build_prompt("dokter anak kapan", [], [_sched(floor=None)])
    assert "dr. Fulan Hidayat, Sp.A" in prompt


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


def test_split_refusal_membuang_penanda_dari_mana_pun():
    from app.assistant.generation import split_refusal

    # ujung, bentuk normal
    teks, tolak = split_refusal("Maaf, di luar cakupan. [TOLAK]")
    assert tolak is True and "TOLAK" not in teks and teks == "Maaf, di luar cakupan."

    # varian huruf/spasi, dan bukan di ujung -- penanda internal tidak boleh
    # sampai terbaca pengguna di posisi mana pun
    teks, tolak = split_refusal("[ tolak ] Maaf, tidak ada infonya.")
    assert tolak is True and "tolak" not in teks.lower()

    # jawaban sah tidak boleh ikut tertandai
    teks, tolak = split_refusal("Segera menuju IGD di Lantai 1.")
    assert tolak is False and teks == "Segera menuju IGD di Lantai 1."
