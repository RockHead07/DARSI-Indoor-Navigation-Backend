"""Retrieval hybrid: prosa lewat pgvector, jadwal lewat SQL biasa.

Jadwal SENGAJA tidak di-embed. "dr. Fulan praktek jam berapa" itu lookup, bukan
pencarian makna. Vector search di data tabular mengembalikan baris yang mirip
bentuknya, bukan yang benar, dan jam praktek salah di RS bukan kesalahan kecil.
"""

import psycopg

from app.assistant import embedding
from app.assistant.models import RetrievedChunk, ScheduleRow

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


def search_chunks(
    conn: psycopg.Connection,
    query: str,
    current_floor: str | None,
    building: str | None,
    limit: int = 5,
) -> list[RetrievedChunk]:
    """Cari chunk prosa paling relevan. Lantai/gedung hanya mem-bias peringkat."""
    vec = embedding.embed([query])[0]

    with conn.cursor() as cur:
        cur.execute(
            """SELECT k.content, k.title, k.doc_type, k.poi_unity_id, p.name AS poi_name,
                      k.floor, k.building, k.is_simulated,
                      1 - (k.embedding <=> %s::vector) AS score
               FROM knowledge_chunks k
               LEFT JOIN pois p ON p.unity_id = k.poi_unity_id
               ORDER BY k.embedding <=> %s::vector
               LIMIT %s""",
            (str(vec), str(vec), _OVERFETCH),
        )
        rows = cur.fetchall()

    hasil: list[RetrievedChunk] = []
    for r in rows:
        skor = float(r["score"])
        # Bias, bukan filter: chunk di lantai lain tetap ikut, cuma tidak dapat bonus.
        if current_floor and r["floor"] == current_floor:
            skor += FLOOR_BONUS
        if building and r["building"] == building:
            skor += BUILDING_BONUS
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

    if not hasil:
        return []

    hasil.sort(key=lambda c: c.score, reverse=True)

    # Tahap 1: gerbang relevansi. Chunk terbaik pun tidak cukup = tidak ada yang relevan.
    if hasil[0].score < MIN_TOP_SCORE:
        return []

    # Tahap 2: rentang relatif terhadap peringkat 1.
    batas = hasil[0].score * RELATIVE_RATIO
    return [c for c in hasil if c.score >= batas][:limit]


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
