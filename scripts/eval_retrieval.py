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
#   test    — set BERSIH. Ditulis setelah corpus diperluas dan sebelum pengukuran
#             apa pun, dan tidak pernah dipakai menyetel. Ini angka yang paling
#             layak dilaporkan. Begitu isinya dipakai memperbaiki sistem, set ini
#             ikut terbakar dan harus diganti set baru.
SET_UJI = [
    ("tuning ", DATA_DIR / "eval_retrieval.json"),
    ("dev    ", DATA_DIR / "eval_holdout.json"),
    ("test-1 ", DATA_DIR / "eval_test.json"),
    ("test-2 ", DATA_DIR / "eval_test2.json"),
    ("test-3 ", DATA_DIR / "eval_test3.json"),
    ("test-4 ", DATA_DIR / "eval_test4.json"),
]


def _jalankan(conn, cases) -> tuple[dict, list]:
    """Pisah recall soal SAH dari penolakan soal SAMPAH -- SATU angka gabungan
    dari keduanya sudah terbukti menyesatkan (2026-08-26): test-4 sempat
    terbaca 75,0% padahal recall soal sah sebenarnya 95,8%, cuma tertutup 7
    soal sampah yang "gagal" (tidak kosong).

    Sejak ADR-036 gerbang SENGAJA dilonggarkan (MIN_TOP_SCORE 0,15) dan
    penyaringan sampah diserahkan ke LLM (build_prompt/generation.py), bukan
    lagi ke retrieval. Jadi sampah yang lolos gerbang di sini BUKAN kegagalan
    -- itu memang perilaku yang diharapkan sekarang, sepanjang jawaban LLM-nya
    tetap benar menolak (diverifikasi terpisah lewat eval_llm_judge.py).
    """
    sah_lolos = sah_total = sampah_lolos_gerbang = sampah_total = 0
    gagal_sah = []
    for case in cases:
        hasil = retrieval.search_chunks(conn, case["q"], None, None, limit=TOP_K)
        judul = [c.title for c in hasil]
        harap = case["expect"]
        if harap is None:
            sampah_total += 1
            if judul != []:
                sampah_lolos_gerbang += 1
        else:
            sah_total += 1
            if harap in judul:
                sah_lolos += 1
            else:
                gagal_sah.append((case["q"], harap, judul))
    return {
        "sah_lolos": sah_lolos, "sah_total": sah_total,
        "sampah_lolos_gerbang": sampah_lolos_gerbang, "sampah_total": sampah_total,
    }, gagal_sah


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
            r, gagal_sah = _jalankan(conn, cases)
            sl, st = r["sah_lolos"], r["sah_total"]
            xl, xt = r["sampah_lolos_gerbang"], r["sampah_total"]
            print(f"\n[{nama}] recall@{TOP_K} SOAL SAH: {sl}/{st} = {sl / st:.1%}"
                  if st else f"\n[{nama}] (tidak ada soal sah)")
            if xt:
                print(f"          soal sampah lolos gerbang (diserahkan ke LLM, "
                      f"lihat eval_llm_judge.py): {xl}/{xt} = {xl / xt:.1%}")
            for q, expect, dapat in gagal_sah:
                print(f"  - \"{q}\"\n      harusnya: {expect}\n      dapatnya: {dapat}")

    print("\nCATATAN: diukur di atas corpus SIMULASI.")
    print("[tuning] dipakai menyetel ambang. Optimistis, JANGAN dilaporkan.")
    print("[dev]    kegagalannya pernah dipakai memperbaiki corpus. Terbakar.")
    print("[test-1] kegagalannya dipakai menambal 4 celah kosakata. Ikut terbakar.")
    print("[test-2] terbakar untuk PARAMETER AMBANG (dipakai belajar 0.15 > 0.22),")
    print("         masih sah untuk mengukur kualitas retrieval secara umum.")
    print("[test-3] dipakai memilih MIN_TOP_SCORE 2026-08-26. Terbakar sejak itu.")
    print("[test-4] disegel, ditulis bersamaan test-3 sebelum pengukuran apa pun.")
    print("         INI angka yang dilaporkan. Sekali dipakai memperbaiki sesuatu,")
    print("         dia ikut terbakar dan butuh set ke-7.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
