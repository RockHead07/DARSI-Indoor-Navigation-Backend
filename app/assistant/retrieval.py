"""Retrieval hybrid: prosa lewat pgvector, jadwal lewat SQL biasa.

Jadwal SENGAJA tidak di-embed. "dr. Fulan praktek jam berapa" itu lookup, bukan
pencarian makna. Vector search di data tabular mengembalikan baris yang mirip
bentuknya, bukan yang benar, dan jam praktek salah di RS bukan kesalahan kecil.
"""

import re

import psycopg

from app.assistant import embedding
from app.assistant.models import RetrievedChunk, ScheduleRow

# Reciprocal Rank Fusion. Menggabung dua pencarian lewat PERINGKAT, bukan skor
# mentah, jadi masalah "skala skor berpindah antar pertanyaan" tidak relevan lagi
# di tahap penggabungan. k=60 nilai standar di literatur RRF.
RRF_K = 60

# ponytail: knob kalibrasi, bukan konstanta fisika. Angkanya ditetapkan lewat
# scripts/eval_retrieval.py, bukan ditebak.
#
# Ambang MUTLAK tunggal (dulu MIN_SCORE) sudah DICABUT, karena terbukti tidak bisa
# bekerja: skala skor berpindah-pindah antar pertanyaan. Terukur pada corpus ini,
# pertanyaan di luar cakupan "harga tiket pesawat ke jakarta" skor tertingginya
# 0.199, sementara jawaban yang BENAR untuk "kalau kecelakaan harus ke mana" hanya
# 0.126. Sampah menang atas jawaban benar, jadi tidak ada satu angka mutlak pun
# yang bisa memisahkan keduanya.
#
# Gantinya dua tahap:
#   1. Gerbang relevansi. Kalau chunk TERBAIK pun tidak mencapai MIN_TOP_SCORE,
#      berarti tidak ada apa pun yang relevan, kembalikan kosong. Ini yang menahan
#      pertanyaan di luar cakupan.
#   2. Rentang relatif. Setelah gerbang lolos, ambil chunk yang skornya masih
#      dalam RELATIVE_RATIO dari peringkat 1. Ini yang mencegah jawaban benar
#      terbuang cuma karena skala skor pertanyaan itu memang rendah.
# 0.22 terukur, bukan ditebak: pertanyaan di luar cakupan "harga tiket pesawat ke
# jakarta" skor tertingginya 0.205, sementara pertanyaan sah "usg perut perlu puasa
# tidak" mengenai chunk yang benar di 0.249. Jaraknya tipis (0.044), jadi kalau
# corpus bertambah, angka ini WAJIB diukur ulang, jangan diasumsikan masih aman.
MIN_TOP_SCORE = 0.22    # gerbang relevansi (spec section 8.3)
RELATIVE_RATIO = 0.75   # ambil yang skornya >= 75% skor peringkat 1
FLOOR_BONUS = 0.05   # tambahan skor kalau chunk selantai dengan user
BUILDING_BONUS = 0.02


# Ambil lebih banyak dari yang dipakai, supaya bias lantai punya ruang menyusun
# ulang peringkat. Pembiasan dilakukan di Python, BUKAN di ORDER BY SQL: menaruh
# CASE di ORDER BY membuat index HNSW tidak terpakai dan query jadi seq scan.
_OVERFETCH = 20

# Kata fungsi/kata tanya yang tidak membawa sinyal isi. Hanya dipakai untuk menyaring
# sisi PERTANYAAN sebelum full-text, tidak memengaruhi vector search. Sengaja pendek
# dan konservatif: kata yang bisa jadi bagian nama layanan (mis. "cara", "jam",
# "daftar", "buka") TIDAK dimasukkan, karena itu justru pembeda antar chunk.
_STOPWORDS = frozenset({
    "yang", "untuk", "dari", "dengan", "pada", "dan", "atau", "adalah", "saja",
    "mau", "mana", "gimana", "bagaimana", "apa", "apakah", "bisa", "boleh",
    "harus", "kalau", "jika", "saya", "aku", "kita", "itu", "ini", "tidak",
    "ada", "juga", "sih", "dong", "nya", "punya", "dapat", "akan",
})


def search_chunks(
    conn: psycopg.Connection,
    query: str,
    current_floor: str | None,
    building: str | None,
    limit: int = 5,
) -> list[RetrievedChunk]:
    """Cari chunk prosa paling relevan lewat gabungan vector + full-text Indonesia.

    Dua pencarian dijalankan berdampingan lalu digabung dengan RRF:
      - vector (pgvector) menangkap kemiripan MAKNA
      - full-text 'indonesian' menangkap kecocokan KATA, terutama nama entitas

    Vector saja terbukti tidak cukup. Terukur: pertanyaan "igd buka 24 jam tidak"
    membuat model embedding menaruh chunk Musholla di peringkat 1, padahal kata
    "igd" ada persis di pertanyaan dan di judul chunk yang benar.

    Lantai/gedung hanya mem-bias peringkat vector, tidak pernah mem-filter.
    """
    vec = embedding.embed([query])[0]
    # Kata < 3 huruf dan kata fungsi dibuang sebelum masuk full-text. Terukur:
    # stemmer 'indonesian' memotong "maupun" jadi "mau", sehingga kata tanya "mau"
    # pada "mau sholat di mana" mencocoki chunk yang memuat "maupun" dan
    # menenggelamkan jawaban yang benar. Kata fungsi tidak membawa sinyal isi.
    terms = [
        t for t in re.findall(r"\w+", query.lower())
        if len(t) >= 3 and t not in _STOPWORDS
    ]
    tsquery = " OR ".join(terms)

    with conn.cursor() as cur:
        cur.execute(
            """SELECT k.id, k.content, k.title, k.doc_type, k.poi_unity_id,
                      p.name AS poi_name, k.floor, k.building, k.is_simulated,
                      1 - (k.embedding <=> %s::vector) AS score
               FROM knowledge_chunks k
               LEFT JOIN pois p ON p.unity_id = k.poi_unity_id
               ORDER BY k.embedding <=> %s::vector
               LIMIT %s""",
            (str(vec), str(vec), _OVERFETCH),
        )
        vrows = cur.fetchall()

        lrows = []
        if tsquery:
            cur.execute(
                """SELECT k.id, k.content, k.title, k.doc_type, k.poi_unity_id,
                          p.name AS poi_name, k.floor, k.building, k.is_simulated,
                          ts_rank(k.tsv, websearch_to_tsquery('indonesian', %s)) AS score
                   FROM knowledge_chunks k
                   LEFT JOIN pois p ON p.unity_id = k.poi_unity_id
                   WHERE k.tsv @@ websearch_to_tsquery('indonesian', %s)
                   ORDER BY score DESC
                   LIMIT %s""",
                (tsquery, tsquery, _OVERFETCH),
            )
            lrows = cur.fetchall()

    # Bias diterapkan SEBELUM fusi, pada skor vector, supaya skalanya konsisten.
    # Kalau ditambahkan setelah RRF, satu bonus 0.05 akan melompati puluhan
    # peringkat sekaligus karena selisih antar-skor RRF cuma ~0.0003.
    def _bias(r) -> float:
        s = float(r["score"])
        if current_floor and r["floor"] == current_floor:
            s += FLOOR_BONUS
        if building and r["building"] == building:
            s += BUILDING_BONUS
        return s

    vsorted = sorted(vrows, key=_bias, reverse=True)

    # Gerbang kasar saja, SENGAJA tidak diandalkan sebagai penentu relevansi.
    #
    # Terukur, dan ini alasannya: pertanyaan sampah "jadwal kereta ke bandung"
    # mendapat cosine 0.348, sementara pertanyaan sah "sebelum usg boleh makan
    # dulu ga" cuma 0.215. Sampah menang atas yang sah. Tidak ada satu ambang pun
    # yang bisa memisahkan keduanya dengan model embedding ini.
    #
    # Jadi gerbang ini hanya menyaring yang benar-benar jauh (mis. "resep rendang
    # padang" di 0.090). Keputusan relevansi yang sesungguhnya ada di LLM, yang
    # membaca teks chunk-nya dan diperintahkan menolak kalau tidak menjawab
    # (lihat generation._SYSTEM_PROMPT). Itu pembaca yang jauh lebih baik daripada
    # satu angka kemiripan.
    #
    # Lexical TIDAK boleh membuka gerbang sendirian: satu kata kebetulan ("resep",
    # "cara", "jadwal") langsung mematahkannya.
    best_cosine = _bias(vsorted[0]) if vsorted else 0.0
    if best_cosine < MIN_TOP_SCORE:
        return []

    rrf: dict[int, float] = {}
    meta: dict[int, dict] = {}
    for peringkat, r in enumerate(vsorted, start=1):
        rrf[r["id"]] = rrf.get(r["id"], 0.0) + 1.0 / (RRF_K + peringkat)
        meta[r["id"]] = r
    for peringkat, r in enumerate(lrows, start=1):
        rrf[r["id"]] = rrf.get(r["id"], 0.0) + 1.0 / (RRF_K + peringkat)
        meta.setdefault(r["id"], r)

    urut = sorted(rrf.items(), key=lambda kv: kv[1], reverse=True)
    # Chunk yang muncul di KEDUA pencarian dapat skor ~2x, jadi rentang relatif ini
    # otomatis mengutamakan yang disepakati dua-duanya.
    batas = urut[0][1] * RELATIVE_RATIO

    hasil: list[RetrievedChunk] = []
    for cid, skor in urut:
        if skor < batas:
            break
        r = meta[cid]
        hasil.append(
            RetrievedChunk(
                content=r["content"],
                title=r["title"],
                doc_type=r["doc_type"],
                poi_unity_id=r["poi_unity_id"],
                poi_name=r["poi_name"],
                floor=r["floor"],
                is_simulated=r["is_simulated"],
                score=skor,
            )
        )
    return hasil[:limit]


def find_schedules(
    conn: psycopg.Connection,
    user_text: str,
    poi_unity_id: str | None,
) -> list[ScheduleRow]:
    """Lookup jadwal. Cocokkan spesialisasi atau nama dokter yang DISEBUT di pertanyaan.

    Arah pencocokannya sengaja terbalik dari pencarian biasa: nilai dari DB dicari
    KEBERADAANNYA di dalam teks pertanyaan, bukan sebaliknya.

    Nama dokter dipecah jadi token, BUKAN diambil per posisi kata. "dr. Fulanah
    Rahmawati, Sp.PD" harus ketemu baik lewat "Fulanah" maupun "Rahmawati", dan
    pendekatan posisi (split_part ke-2) diam-diam mengembalikan kosong untuk yang
    kedua. Kosong itu gejala paling berbahaya di sini: terlihat seperti "jadwal
    tidak ada", bukan seperti bug. Token >= 4 huruf membuang "dr" dan gelar pendek.

    poi_unity_id di-cast ::text karena Postgres tidak bisa menyimpulkan tipe
    parameter yang bernilai NULL (AmbiguousParameter). Tidak perlu penjaga
    "IS NOT NULL": poi_unity_id = NULL memang tidak pernah cocok.
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT doctor_name, specialty, day_of_week, start_time, end_time,
                      poi_unity_id, is_simulated
               FROM doctor_schedules
               WHERE %(teks)s ILIKE '%%' || specialty || '%%'
                  OR EXISTS (
                        SELECT 1
                        FROM unnest(string_to_array(
                                 regexp_replace(doctor_name, '[.,]', '', 'g'), ' ')) AS w
                        WHERE length(w) >= 4 AND %(teks)s ILIKE '%%' || w || '%%'
                     )
                  OR poi_unity_id = %(poi)s::text
               ORDER BY day_of_week, start_time""",
            {"teks": user_text, "poi": poi_unity_id},
        )
        rows = cur.fetchall()

    return [
        ScheduleRow(
            doctor_name=r["doctor_name"],
            specialty=r["specialty"],
            day_of_week=r["day_of_week"],
            start_time=r["start_time"].strftime("%H:%M"),
            end_time=r["end_time"].strftime("%H:%M"),
            poi_unity_id=r["poi_unity_id"],
            is_simulated=r["is_simulated"],
        )
        for r in rows
    ]
