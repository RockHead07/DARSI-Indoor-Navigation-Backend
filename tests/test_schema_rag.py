"""Verifikasi skema RAG benar-benar terpasang di DB.

Di-skip kalau TEST_DATABASE_URL tidak diset, supaya pytest tetap hijau di mesin
yang belum menyalakan Postgres lokal.
"""

import os

import psycopg
import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL tidak diset"
)


@pytest.fixture
def conn():
    with psycopg.connect(TEST_DATABASE_URL) as c:
        yield c


def test_ekstensi_vector_aktif(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        assert cur.fetchone() is not None


def test_tabel_knowledge_chunks_ada_dengan_dimensi_384(conn):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT atttypmod FROM pg_attribute
               WHERE attrelid = 'knowledge_chunks'::regclass AND attname = 'embedding'"""
        )
        row = cur.fetchone()
        assert row is not None, "kolom embedding tidak ada"
        # pgvector menyimpan dimensi di atttypmod apa adanya
        assert row[0] == 384


def test_index_hnsw_terpasang(conn):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT indexdef FROM pg_indexes
               WHERE tablename = 'knowledge_chunks' AND indexname = 'idx_chunks_embedding'"""
        )
        row = cur.fetchone()
        assert row is not None, "index HNSW tidak ada"
        assert "hnsw" in row[0].lower()


def test_tabel_doctor_schedules_ada(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('doctor_schedules')")
        assert cur.fetchone()[0] is not None


def test_day_of_week_menolak_nilai_di_luar_1_sampai_7(conn):
    with conn.cursor() as cur:
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                """INSERT INTO doctor_schedules
                   (doctor_name, specialty, day_of_week, start_time, end_time)
                   VALUES ('dr. Uji', 'Uji', 8, '08:00', '09:00')"""
            )
        conn.rollback()
