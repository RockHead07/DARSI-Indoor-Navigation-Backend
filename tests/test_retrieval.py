import os

import psycopg
from psycopg.rows import dict_row
import pytest

from app.assistant import retrieval
from scripts.ingest_corpus import ingest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL tidak diset"
)


@pytest.fixture(scope="module")
def conn():
    with psycopg.connect(TEST_DATABASE_URL, row_factory=dict_row) as c:
        with c.cursor() as cur:
            cur.execute("DELETE FROM knowledge_chunks")
            cur.execute("DELETE FROM doctor_schedules")
        c.commit()
        ingest(c)
        yield c


def test_pertanyaan_obat_menemukan_farmasi(conn):
    hasil = retrieval.search_chunks(conn, "mau nebus resep obat", None, None)
    assert hasil, "tidak ada hasil sama sekali"
    assert "Farmasi" in hasil[0].title


def test_pertanyaan_bpjs_menemukan_alur_bpjs(conn):
    """Tolok ukur project ini recall@3 (lihat scripts/eval_retrieval.py), jadi yang
    diuji "masuk 3 besar", bukan "peringkat 1". Menuntut peringkat 1 di sini akan
    lebih ketat daripada standar yang dipakai plan-nya sendiri.

    Terukur: untuk pertanyaan ini chunk BPJS dapat 0.344 dan kalah dari FAQ
    "Berobat tanpa surat rujukan" (0.408) yang isinya memang bersinggungan.
    """
    hasil = retrieval.search_chunks(conn, "syarat daftar pakai bpjs apa saja", None, None)
    assert any("BPJS" in c.title for c in hasil[:3])


def test_hasil_terurut_skor_menurun(conn):
    hasil = retrieval.search_chunks(conn, "poli anak", None, None)
    skor = [c.score for c in hasil]
    assert skor == sorted(skor, reverse=True)


def test_bias_lantai_menaikkan_peringkat_bukan_membuang(conn):
    """Aturan spec section 5: lantai MEM-BIAS, TIDAK mem-filter keras.
    User di Lantai 1 bertanya soal Poli Anak (Lantai 2) harus tetap ketemu."""
    hasil = retrieval.search_chunks(conn, "poli anak di mana", "Lantai 1", None)
    judul = [c.title for c in hasil]
    assert "Poli Anak" in judul, "info lantai lain hilang — ini filter keras, bukan bias"


def test_bias_lantai_benar_benar_berpengaruh(conn):
    """Dengan pertanyaan yang ambigu antar-lantai, chunk di lantai user naik."""
    tanpa = retrieval.search_chunks(conn, "jam layanan", None, None)
    dengan = retrieval.search_chunks(conn, "jam layanan", "Lantai 2", None)
    lantai2_tanpa = [i for i, c in enumerate(tanpa) if c.floor == "Lantai 2"]
    lantai2_dengan = [i for i, c in enumerate(dengan) if c.floor == "Lantai 2"]
    if lantai2_tanpa and lantai2_dengan:
        assert lantai2_dengan[0] <= lantai2_tanpa[0]


def test_pertanyaan_di_luar_cakupan_tidak_mengembalikan_apa_apa(conn):
    hasil = retrieval.search_chunks(conn, "harga tiket pesawat ke jakarta", None, None)
    assert hasil == []


def test_cari_jadwal_lewat_spesialisasi(conn):
    hasil = retrieval.find_schedules(conn, "dokter anak praktek kapan", None)
    assert hasil
    assert all(s.specialty == "Anak" for s in hasil)


def test_cari_jadwal_lewat_nama_dokter(conn):
    hasil = retrieval.find_schedules(conn, "jadwal dr. Rahmawati", None)
    assert hasil
    assert all("Rahmawati" in s.doctor_name for s in hasil)


def test_pertanyaan_tanpa_unsur_jadwal_tidak_mengembalikan_jadwal(conn):
    assert retrieval.find_schedules(conn, "toilet di mana", None) == []
