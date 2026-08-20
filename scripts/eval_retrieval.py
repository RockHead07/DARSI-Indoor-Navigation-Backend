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

EVAL_PATH = Path(__file__).resolve().parent.parent / "data" / "eval_retrieval.json"
TOP_K = 3


def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL kosong.", file=sys.stderr)
        return 1

    cases = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    embedding.load_model()

    lolos, gagal = 0, []
    with psycopg.connect(url, row_factory=dict_row) as conn:
        for case in cases:
            hasil = retrieval.search_chunks(conn, case["q"], None, None, limit=TOP_K)
            judul = [c.title for c in hasil]
            if case["expect"] in judul:
                lolos += 1
            else:
                gagal.append((case["q"], case["expect"], judul))

    total = len(cases)
    print(f"\nrecall@{TOP_K}: {lolos}/{total} = {lolos / total:.1%}")
    print(f"MIN_TOP_SCORE={retrieval.MIN_TOP_SCORE}  RELATIVE_RATIO={retrieval.RELATIVE_RATIO}  FLOOR_BONUS={retrieval.FLOOR_BONUS}")

    if gagal:
        print(f"\n{len(gagal)} pertanyaan meleset:")
        for q, expect, dapat in gagal:
            print(f"  - \"{q}\"\n      harusnya: {expect}\n      dapatnya: {dapat}")

    print("\nCATATAN: angka ini diukur di atas corpus SIMULASI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
