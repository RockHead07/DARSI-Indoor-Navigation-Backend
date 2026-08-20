"""Ukur kualitas retrieval: berapa persen pertanyaan yang chunk benarnya masuk 3 besar.

Ini yang membuat "RAG-nya bagus" jadi angka, bukan perasaan. Dipakai juga untuk
menyetel MIN_SCORE dan FLOOR_BONUS di app/assistant/retrieval.py.

CATATAN JUJUR: evaluasi ini berjalan di atas corpus SIMULASI. Yang diukur adalah
kualitas mekanisme retrieval, BUKAN kesiapan sistem terhadap pertanyaan pasien
sungguhan. Sebutkan batasan ini kalau angkanya dilaporkan.

Pakai:
    export DATABASE_URL=...
    python -m scripts.eval_retrieval
"""

import json
import os
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app.assistant import embedding, retrieval

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TOP_K = 3

# Dua set, dan bedanya penting:
#   tuning  — dipakai untuk menyetel ambang dan memperkaya corpus. Angkanya
#             OPTIMISTIS dan tidak boleh dilaporkan sebagai kinerja sistem,
#             karena sistemnya memang disetel terhadap set ini.
#   holdout — soal bergaya awam yang TIDAK pernah dipakai menyetel apa pun.
#             Inilah angka yang layak dilaporkan.
SET_UJI = [
    ("tuning ", DATA_DIR / "eval_retrieval.json"),
    ("holdout", DATA_DIR / "eval_holdout.json"),
]


def _jalankan(conn, cases) -> tuple[int, int, list]:
    lolos, gagal = 0, []
    for case in cases:
        hasil = retrieval.search_chunks(conn, case["q"], None, None, limit=TOP_K)
        judul = [c.title for c in hasil]
        harap = case["expect"]
        # expect=null berarti pertanyaan di luar cakupan: hasil yang BENAR adalah
        # kosong. Ini menguji gerbang relevansi, bukan kemampuan mencari.
        benar = (judul == []) if harap is None else (harap in judul)
        if benar:
            lolos += 1
        else:
            gagal.append((case["q"], harap, judul))
    return lolos, len(cases), gagal


def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL kosong.", file=sys.stderr)
        return 1

    embedding.load_model()
    print(f"\nMIN_TOP_SCORE={retrieval.MIN_TOP_SCORE}  "
          f"RELATIVE_RATIO={retrieval.RELATIVE_RATIO}  "
          f"FLOOR_BONUS={retrieval.FLOOR_BONUS}")

    with psycopg.connect(url, row_factory=dict_row) as conn:
        for nama, path in SET_UJI:
            cases = json.loads(path.read_text(encoding="utf-8"))
            lolos, total, gagal = _jalankan(conn, cases)
            print(f"\n[{nama}] recall@{TOP_K}: {lolos}/{total} = {lolos / total:.1%}")
            for q, expect, dapat in gagal:
                harap = "(kosong)" if expect is None else expect
                print(f"  - \"{q}\"\n      harusnya: {harap}\n      dapatnya: {dapat}")

    print("\nCATATAN: diukur di atas corpus SIMULASI.")
    print("Angka [tuning] optimistis (sistem disetel terhadapnya).")
    print("Angka [holdout] yang layak dilaporkan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
