"""Corpus SIMULASI untuk RAG Assistant.

PERINGATAN: seluruh isi berkas ini KARANGAN. RS Islam A. Yani adalah rumah sakit
sungguhan, tapi belum memberikan data operasional dan izinnya belum ada. Nama
dokter memakai pola "Fulan/Fulanah" supaya jelas fiktif.

Semua baris masuk DB dengan is_simulated = true. Saat data asli tersedia:
    DELETE FROM knowledge_chunks WHERE is_simulated = true;
    DELETE FROM doctor_schedules  WHERE is_simulated = true;
lalu ingest ulang dengan is_simulated = false.
"""

# poi_unity_id sengaja None: GUID POI berasal dari Unity lewat POST /api/poi/sync,
# dan POI seperti "Poli Anak" belum ada di scene. Menebak GUID di sini justru
# melanggar aturan "satu pemilik data" (ADR-021). Isi belakangan setelah POI-nya
# benar-benar ada, atau biarkan None (jawaban tetap keluar, cuma tanpa tombol rute).
CHUNKS: list[dict] = [
    {
        "title": "Alur Pendaftaran BPJS Rawat Jalan",
        "doc_type": "sop",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#bpjs",
        "content": (
            "Alur pendaftaran pasien BPJS rawat jalan. Pasien BPJS membawa kartu BPJS "
            "aktif, KTP, dan surat rujukan dari Faskes 1 yang masih berlaku. Rujukan "
            "berlaku 90 hari sejak diterbitkan. Pendaftaran dilayani di loket "
            "Pendaftaran BPJS di Lantai 1 mulai pukul 07.00. Setelah mendapat nomor "
            "antrean, pasien menunggu panggilan di ruang tunggu poli tujuan."
        ),
    },
    {
        "title": "Alur Pasien IGD",
        "doc_type": "sop",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#igd",
        "content": (
            "Alur pasien IGD, Instalasi Gawat Darurat, unit emergency. Pasien gawat "
            "darurat langsung menuju IGD tanpa mendaftar lebih dulu. IGD menangani "
            "korban kecelakaan, cedera, luka, patah tulang, pendarahan, luka bakar, "
            "pingsan, kejang, sesak napas, nyeri dada, serangan jantung, stroke, "
            "keracunan, dan demam tinggi pada anak. Kalau kondisinya mendesak atau "
            "mengancam nyawa, langsung ke IGD, jangan menunggu antrean poli. "
            "Pendaftaran administrasi diurus keluarga setelah pasien ditangani."
        ),
    },
    # Sengaja DIPISAH dari chunk di atas. Sebelumnya jam operasional ikut menempel
    # di sana, dan begitu chunk itu diperkaya daftar kondisi darurat, pertanyaan
    # "igd buka 24 jam tidak" tidak lagi mengenainya (skor jatuh, kalah dari chunk
    # lain yang menyebut "24 jam"). Itu efek dilusi: satu chunk memuat dua topik.
    # Satu chunk = satu topik.
    {
        "title": "Jam Operasional IGD",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#igd_jam",
        "content": (
            "IGD buka 24 jam nonstop, setiap hari, termasuk Sabtu, Minggu, hari libur "
            "nasional, dan tanggal merah. IGD tidak pernah tutup dan tidak punya jam "
            "istirahat. Pasien gawat darurat bisa datang kapan saja, siang maupun "
            "tengah malam."
        ),
    },
    {
        "title": "Alur Rawat Jalan Pasien Umum",
        "doc_type": "sop",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#umum",
        "content": (
            "Alur rawat jalan pasien umum non-BPJS, pasien bayar sendiri, pasien baru "
            "maupun pasien lama. Cara mendaftar berobat jalan: pasien umum mendaftar "
            "langsung di loket Pendaftaran tanpa perlu surat rujukan dan tanpa kartu "
            "BPJS, cukup membawa KTP. Setelah mendaftar, pasien mendapat nomor antrean "
            "lalu menunggu dipanggil di poli tujuan. Pembayaran dilakukan di Kasir "
            "setelah pemeriksaan selesai. Pendaftaran rawat jalan dibuka pukul 07.00 "
            "sampai 15.00."
        ),
    },
    {
        "title": "Layanan Farmasi",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#farmasi",
        "content": (
            "Farmasi melayani penebusan resep pasien rawat jalan dan rawat inap. Jam "
            "layanan pukul 07.00 sampai 21.00. Resep BPJS dilayani di loket terpisah "
            "dari resep umum. Obat racikan membutuhkan waktu tunggu lebih lama."
        ),
    },
    {
        "title": "Layanan Radiologi",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#radiologi",
        "content": (
            "Radiologi melayani pemeriksaan rontgen, USG, dan CT scan. Pemeriksaan "
            "harus membawa surat pengantar dari dokter. Pemeriksaan USG perut "
            "mengharuskan pasien berpuasa 6 jam sebelumnya. Layanan buka pukul 08.00 "
            "sampai 20.00, dan 24 jam untuk kasus dari IGD."
        ),
    },
    {
        "title": "Layanan Laboratorium",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#lab",
        "content": (
            "Laboratorium melayani pemeriksaan darah, urine, dan sampel lain. "
            "Pengambilan sampel darah puasa dilayani pukul 07.00 sampai 09.00. Hasil "
            "pemeriksaan rutin keluar di hari yang sama."
        ),
    },
    {
        "title": "Poli Anak",
        "doc_type": "layanan",
        "floor": "Lantai 2",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#poli_anak",
        "content": (
            "Poli Anak berada di Lantai 2 dan melayani pemeriksaan kesehatan anak, "
            "imunisasi, serta konsultasi tumbuh kembang. Pasien anak dengan demam "
            "tinggi disarankan langsung ke IGD."
        ),
    },
    {
        "title": "Poli Penyakit Dalam",
        "doc_type": "layanan",
        "floor": "Lantai 2",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#poli_dalam",
        "content": (
            "Poli Penyakit Dalam berada di Lantai 2, melayani konsultasi penyakit "
            "kronis seperti diabetes, hipertensi, dan gangguan pencernaan."
        ),
    },
    {
        "title": "Musholla dan Fasilitas Ibadah",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#musholla",
        "content": (
            "Musholla adalah tempat sholat, salat, dan ibadah bagi pasien, keluarga "
            "pasien, maupun pengunjung. Musholla berada di Lantai 1 dekat area kantin, "
            "terbuka 24 jam, dilengkapi tempat wudhu terpisah untuk pria dan wanita. "
            "Tersedia mukena dan sajadah. Pengunjung bisa menunaikan sholat lima waktu "
            "di sini, termasuk sholat Jumat."
        ),
    },
    {
        "title": "FAQ: Berobat tanpa surat rujukan",
        "doc_type": "faq",
        "floor": None,
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#faq_rujukan",
        "content": (
            "Apakah bisa berobat tanpa rujukan? Pasien umum bisa langsung mendaftar "
            "tanpa rujukan. Pasien BPJS memerlukan rujukan dari Faskes 1, kecuali "
            "kasus gawat darurat yang ditangani IGD."
        ),
    },
    {
        "title": "FAQ: Jam besuk pasien rawat inap",
        "doc_type": "faq",
        "floor": None,
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#faq_besuk",
        "content": (
            "Jam besuk pasien rawat inap dibagi dua sesi: siang pukul 11.00 sampai "
            "13.00 dan sore pukul 17.00 sampai 19.00. Anak di bawah 12 tahun tidak "
            "disarankan ikut membesuk."
        ),
    },
    {
        "title": "FAQ: Cara mendapatkan salinan rekam medis",
        "doc_type": "faq",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#faq_rekam_medis",
        "content": (
            "Permintaan salinan rekam medis diajukan di bagian Rekam Medis Lantai 1 "
            "dengan membawa KTP pasien. Permintaan oleh keluarga memerlukan surat kuasa. "
            "Berkas selesai dalam 3 hari kerja."
        ),
    },
]

SCHEDULES: list[dict] = [
    {"doctor_name": "dr. Fulan Hidayat, Sp.A", "specialty": "Anak",
     "day_of_week": 1, "start_time": "08:00", "end_time": "14:00", "poi_unity_id": None},
    {"doctor_name": "dr. Fulan Hidayat, Sp.A", "specialty": "Anak",
     "day_of_week": 3, "start_time": "08:00", "end_time": "14:00", "poi_unity_id": None},
    {"doctor_name": "dr. Fulanah Rahmawati, Sp.PD", "specialty": "Penyakit Dalam",
     "day_of_week": 2, "start_time": "09:00", "end_time": "15:00", "poi_unity_id": None},
    {"doctor_name": "dr. Fulanah Rahmawati, Sp.PD", "specialty": "Penyakit Dalam",
     "day_of_week": 4, "start_time": "09:00", "end_time": "15:00", "poi_unity_id": None},
    {"doctor_name": "dr. Fulan Santoso, Sp.OG", "specialty": "Kandungan",
     "day_of_week": 5, "start_time": "10:00", "end_time": "16:00", "poi_unity_id": None},
]
