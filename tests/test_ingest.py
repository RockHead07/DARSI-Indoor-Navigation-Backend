import os

import psycopg
import pytest

from data import corpus_simulasi
from scripts.ingest_corpus import ingest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL tidak diset"
)


@pytest.fixture
def conn():
    with psycopg.connect(TEST_DATABASE_URL) as c:
        with c.cursor() as cur:
            cur.execute("DELETE FROM knowledge_chunks")
            cur.execute("DELETE FROM doctor_schedules")
        c.commit()
        yield c


def test_ingest_memasukkan_semua_baris(conn):
    hasil = ingest(conn)
    assert hasil["chunks"] == len(corpus_simulasi.CHUNKS)
    assert hasil["schedules"] == len(corpus_simulasi.SCHEDULES)


def test_semua_baris_ditandai_simulasi(conn):
    ingest(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM knowledge_chunks WHERE NOT is_simulated")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM doctor_schedules WHERE NOT is_simulated")
        assert cur.fetchone()[0] == 0


def test_ingest_idempoten(conn):
    """Jalankan dua kali tidak menggandakan baris."""
    ingest(conn)
    ingest(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM knowledge_chunks")
        assert cur.fetchone()[0] == len(corpus_simulasi.CHUNKS)


def test_embedding_tersimpan_dengan_dimensi_benar(conn):
    ingest(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT vector_dims(embedding) FROM knowledge_chunks LIMIT 1")
        assert cur.fetchone()[0] == 384


def test_nama_dokter_memakai_pola_fiktif(conn):
    """Aturan spec section 7.1: nama dokter wajib jelas karangan."""
    for s in corpus_simulasi.SCHEDULES:
        assert "Fulan" in s["doctor_name"]
