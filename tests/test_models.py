import pytest
from app.assistant.models import RetrievedChunk, derive_poi


def _chunk(title: str, poi_unity_id: str | None, poi_name: str | None = None,
           score: float = 0.9) -> RetrievedChunk:
    return RetrievedChunk(
        content="isi",
        title=title,
        doc_type="layanan",
        poi_unity_id=poi_unity_id,
        poi_name=poi_name,
        floor=None,
        is_simulated=True,
        score=score,
    )


def test_derive_poi_ambil_dari_chunk_peringkat_satu():
    chunks = [
        _chunk("Farmasi", "guid-farmasi", "Farmasi"),
        _chunk("IGD", "guid-igd", "IGD"),
    ]
    assert derive_poi(chunks) == ("guid-farmasi", "Farmasi")


def test_derive_poi_null_kalau_peringkat_satu_tanpa_poi():
    """Sengaja TIDAK menyisir ke peringkat 2 — lihat 'Keputusan Penafsiran' di plan."""
    chunks = [
        _chunk("Alur BPJS", None),
        _chunk("Farmasi", "guid-farmasi", "Farmasi"),
    ]
    assert derive_poi(chunks) == (None, None)


def test_derive_poi_daftar_kosong():
    assert derive_poi([]) == (None, None)
