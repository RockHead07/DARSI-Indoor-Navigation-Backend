"""Test ini memuat model sungguhan (0.22 GB), jadi lambat di jalannya yang pertama.
Sengaja tidak di-mock: yang perlu dibuktikan justru dimensi dan perilaku model asli,
karena dimensi yang meleset merusak skema DB.
"""

import pytest

from app.assistant import embedding


@pytest.fixture(scope="module", autouse=True)
def _load():
    embedding.load_model()


def test_dimensi_harus_384():
    """384 dikunci di skema DB (vector(384)). Kalau ini gagal, skema ikut salah."""
    vecs = embedding.embed(["poli anak di lantai berapa"])
    assert len(vecs) == 1
    assert len(vecs[0]) == embedding.EMBEDDING_DIM == 384


def test_embed_banyak_teks_sekaligus():
    vecs = embedding.embed(["farmasi", "instalasi gawat darurat", "toilet"])
    assert len(vecs) == 3
    assert all(len(v) == 384 for v in vecs)


def test_hasilnya_deterministik():
    a = embedding.embed(["alur pendaftaran bpjs"])[0]
    b = embedding.embed(["alur pendaftaran bpjs"])[0]
    assert a == pytest.approx(b)


def test_kalimat_indonesia_yang_mirip_makna_lebih_dekat_daripada_yang_beda():
    """Bukti kasar bahwa Bahasa Indonesia benar-benar dipahami model, bukan sekadar
    diproses. Kalau ini gagal, pilihan modelnya yang salah, bukan kodenya."""
    def cos(u, v):
        dot = sum(x * y for x, y in zip(u, v))
        nu = sum(x * x for x in u) ** 0.5
        nv = sum(y * y for y in v) ** 0.5
        return dot / (nu * nv)

    obat, apotek, parkir = embedding.embed(["tempat ambil obat", "apotek", "parkir mobil"])
    assert cos(obat, apotek) > cos(obat, parkir)


def test_embed_tanpa_load_model_gagal_berisik():
    embedding._model = None
    with pytest.raises(RuntimeError, match="belum dimuat"):
        embedding.embed(["apa saja"])
    embedding.load_model()  # pulihkan untuk test lain
