"""Sweep MIN_TOP_SCORE dan laporkan trade-off-nya secara terpisah.

Kenapa terpisah: menurunkan ambang MENAIKKAN recall soal sah sekaligus
MENURUNKAN penolakan soal sampah. Satu angka gabungan menyembunyikan
pertukaran itu, dan nilai "terbaik" jadi tergantung komposisi set uji
(banyak soal sampah -> ambang tinggi menang; sedikit -> ambang rendah menang).
Angka yang dipakai mengambil keputusan harus yang dipisah.

Juga mencetak skor cosine tertinggi untuk beberapa pertanyaan diagnostik,
supaya "apakah ambang X cukup untuk kasus Y" dijawab dengan angka, bukan dugaan.

Pakai (di server, di mana DATABASE_URL tersedia):
    docker compose exec api python -m scripts.sweep_threshold
"""

import json
import os
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app.assistant import embedding, retrieval

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TOP_K = 3
KANDIDAT = [0.00, 0.10, 0.12, 0.15, 0.18, 0.20, 0.22, 0.25]

SET_UJI = [
    ("tuning", "eval_retrieval.json"),
    ("dev   ", "eval_holdout.json"),
    ("test-1", "eval_test.json"),
    ("test-2", "eval_test2.json"),
    ("test-3", "eval_test3.json"),
    ("test-4", "eval_test4.json"),
]

# Pertanyaan yang diketahui gagal di gerbang 0,22. Dicetak skor mentahnya supaya
# terlihat apakah ambang kandidat benar-benar melewatkannya, bukan diasumsikan.
DIAGNOSTIK = [
    "Tangan kena pisau robek berdarah banyak",   # eval_llm_judge #06
    "kena air panas melepuh",                    # test-2, tercatat di RETRIEVAL-EVALUATION 6
    "tangan saya keseleo mau dilihat tulangnya",
    "pengen beli minum",
    "ada yang nganter jenazah ga",
]


def skor_tertinggi(conn, query: str) -> float:
    """Nilai yang dibaca gerbang: cosine tertinggi, tanpa bias lantai/gedung.

    Direplikasi langsung di sini (bukan lewat search_chunks) karena search_chunks
    mengembalikan hasil yang SUDAH lolos gerbang -- kalau gerbangnya menolak,
    hasilnya kosong dan skornya tidak bisa dilihat sama sekali.
    """
    vec = embedding.embed([query])[0]
    with conn.cursor() as cur:
        cur.execute(
            """SELECT 1 - (embedding <=> %s::vector) AS score
               FROM knowledge_chunks ORDER BY embedding <=> %s::vector LIMIT 1""",
            (str(vec), str(vec)),
        )
        row = cur.fetchone()
    return float(row["score"]) if row else 0.0


def ukur(conn, cases: list) -> tuple[int, int, int, int]:
    """Kembalikan (sah_lolos, sah_total, sampah_ditolak, sampah_total)."""
    sah_lolos = sah_total = sampah_tolak = sampah_total = 0
    for case in cases:
        hasil = retrieval.search_chunks(conn, case["q"], None, None, limit=TOP_K)
        judul = [c.title for c in hasil]
        if case["expect"] is None:
            sampah_total += 1
            if judul == []:
                sampah_tolak += 1
        else:
            sah_total += 1
            if case["expect"] in judul:
                sah_lolos += 1
    return sah_lolos, sah_total, sampah_tolak, sampah_total


def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL kosong.", file=sys.stderr)
        return 1

    embedding.load_model()
    semua = [(nama, json.loads((DATA_DIR / f).read_text(encoding="utf-8")))
             for nama, f in SET_UJI if (DATA_DIR / f).exists()]

    with psycopg.connect(url, row_factory=dict_row) as conn:
        print("\n=== SKOR DIAGNOSTIK (cosine tertinggi, nilai yang dibaca gerbang) ===")
        for q in DIAGNOSTIK:
            print(f"  {skor_tertinggi(conn, q):.3f}  \"{q}\"")

        asli = retrieval.MIN_TOP_SCORE
        try:
            for nama, cases in semua:
                print(f"\n=== {nama} ({len(cases)} soal) ===")
                print("  ambang | soal sah (recall@3) | soal sampah (ditolak) | gabungan")
                for amb in KANDIDAT:
                    retrieval.MIN_TOP_SCORE = amb
                    sl, st, xt, xs = ukur(conn, cases)
                    gab = (sl + xt) / (st + xs)
                    tanda = " <-- sekarang" if abs(amb - asli) < 1e-9 else ""
                    print(f"   {amb:.2f}   |  {sl:2d}/{st:2d} = {sl / st:5.1%}      "
                          f"|  {xt:2d}/{xs:2d} = {xt / xs if xs else 0:5.1%}      "
                          f"|  {gab:5.1%}{tanda}")
        finally:
            retrieval.MIN_TOP_SCORE = asli

    print("\nCATATAN: 'gabungan' TIDAK boleh jadi satu-satunya dasar keputusan --")
    print("nilainya bergeser mengikuti proporsi soal sampah di tiap set.")
    print("test-3 = set penyetelan (boleh dipakai memilih ambang, setelah itu terbakar).")
    print("test-4 = disegel, ditulis bersamaan test-3 sebelum pengukuran apa pun.")
    print("         HANYA dibuka sekali untuk melaporkan angka akhir.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
