"""Masukkan corpus simulasi ke DB, lengkap dengan embedding-nya.

Idempoten lewat ON CONFLICT: jalankan berkali-kali aman, baris tidak menggandakan.

Pakai:
    export DATABASE_URL=...
    python -m scripts.ingest_corpus
"""

import os
import sys

import psycopg

from app.assistant import embedding
from data import corpus_simulasi


def ingest(conn: psycopg.Connection, is_simulated: bool = True) -> dict:
    """Embed lalu upsert seluruh corpus. Mengembalikan jumlah baris per tabel."""
    embedding.load_model()

    chunks = corpus_simulasi.CHUNKS
    vectors = embedding.embed([c["content"] for c in chunks])

    with conn.cursor() as cur:
        for chunk, vec in zip(chunks, vectors):
            cur.execute(
                """INSERT INTO knowledge_chunks
                       (content, embedding, doc_type, title, poi_unity_id,
                        building, floor, is_simulated, source_ref)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (title, source_ref) DO UPDATE SET
                       content = EXCLUDED.content,
                       embedding = EXCLUDED.embedding,
                       doc_type = EXCLUDED.doc_type,
                       poi_unity_id = EXCLUDED.poi_unity_id,
                       building = EXCLUDED.building,
                       floor = EXCLUDED.floor,
                       is_simulated = EXCLUDED.is_simulated""",
                (chunk["content"], str(vec), chunk["doc_type"], chunk["title"],
                 chunk["poi_unity_id"], chunk["building"], chunk["floor"],
                 is_simulated, chunk["source_ref"]),
            )

        for s in corpus_simulasi.SCHEDULES:
            cur.execute(
                """INSERT INTO doctor_schedules
                       (doctor_name, specialty, poi_unity_id, day_of_week,
                        start_time, end_time, is_simulated)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (doctor_name, day_of_week, start_time) DO UPDATE SET
                       specialty = EXCLUDED.specialty,
                       poi_unity_id = EXCLUDED.poi_unity_id,
                       end_time = EXCLUDED.end_time,
                       is_simulated = EXCLUDED.is_simulated""",
                (s["doctor_name"], s["specialty"], s["poi_unity_id"], s["day_of_week"],
                 s["start_time"], s["end_time"], is_simulated),
            )
    conn.commit()
    return {"chunks": len(chunks), "schedules": len(corpus_simulasi.SCHEDULES)}


def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL kosong.", file=sys.stderr)
        return 1
    with psycopg.connect(url) as conn:
        hasil = ingest(conn)
    print(f"Selesai: {hasil['chunks']} chunk, {hasil['schedules']} jadwal (SIMULASI).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
