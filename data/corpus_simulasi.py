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
            "istirahat. Pasien gawat darurat tetap dilayani kapan saja: pagi, siang, "
            "sore, malam hari, larut malam, tengah malam, dini hari, maupun subuh. "
            "Di luar jam poli, IGD adalah satu-satunya layanan yang tetap buka."
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
            "Radiologi melayani foto rontgen, sinar X, USG, dan CT scan. Di sinilah "
            "tulang, dada, dan organ dalam difoto, termasuk untuk memastikan tulang "
            "retak atau patah. Pemeriksaan harus membawa surat pengantar dari dokter. "
            "Sebelum USG perut, pasien wajib berpuasa, tidak makan dan tidak minum "
            "selama 6 jam. Layanan buka pukul 08.00 sampai 20.00, dan 24 jam untuk "
            "kasus dari IGD."
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
            "Laboratorium melayani cek darah, tes darah, periksa urine atau air seni, "
            "dahak, dan sampel lain. Tersedia pemeriksaan gula darah, kolesterol, asam "
            "urat, dan fungsi ginjal. Pengambilan sampel darah puasa dilayani pukul "
            "07.00 sampai 09.00. Hasil pemeriksaan rutin keluar di hari yang sama."
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
            "Poli Penyakit Dalam berada di Lantai 2, melayani konsultasi penyakit kronis "
            "pada orang dewasa seperti diabetes atau kencing manis, hipertensi atau "
            "tekanan darah tinggi, kolesterol tinggi, asam urat, penyakit lambung, "
            "tipes, dan gangguan pencernaan."
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
            "Permintaan salinan rekam medis, fotokopi hasil pemeriksaan, hasil lab, "
            "atau resume medis diajukan di bagian Rekam Medis Lantai 1 dengan membawa "
            "KTP pasien. Permintaan oleh keluarga memerlukan surat kuasa. Berkas "
            "selesai dalam 3 hari kerja."
        ),
    },

    # ── Perluasan corpus (tahap 2) ────────────────────────────────────────────
    # Ditulis untuk menutup topik yang lazim ditanyakan di RS tapi belum terwakili,
    # bukan sekadar mengejar soal uji yang gagal. Kosakatanya sengaja memakai
    # istilah awam sekaligus istilah resmi, karena pasien memakai keduanya.
    {
        "title": "Kasir dan Cara Pembayaran",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#kasir",
        "content": (
            "Kasir melayani pembayaran biaya pemeriksaan, obat, dan tindakan. "
            "Pembayaran bisa tunai, kartu debit, kartu kredit, dan QRIS. Pasien umum "
            "membayar setelah pemeriksaan selesai. Pasien BPJS tidak membayar biaya "
            "yang ditanggung, tetapi selisih biaya naik kelas dibayar di Kasir. "
            "Kuitansi diminta di loket yang sama."
        ),
    },
    {
        "title": "Rawat Inap dan Kelas Kamar",
        "doc_type": "layanan",
        "floor": "Lantai 2",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#rawat_inap",
        "content": (
            "Rawat inap atau opname tersedia dalam kelas 3, kelas 2, kelas 1, dan VIP. "
            "Pasien BPJS mendapat kelas sesuai haknya dan boleh naik kelas dengan "
            "membayar selisih. Pendaftaran rawat inap diurus di Admisi setelah dokter "
            "menyatakan pasien perlu menginap. Satu penunggu pasien diperbolehkan "
            "menginap di kamar."
        ),
    },
    {
        "title": "Poli Gigi",
        "doc_type": "layanan",
        "floor": "Lantai 2",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#poli_gigi",
        "content": (
            "Poli Gigi melayani sakit gigi, gigi berlubang, tambal gigi, cabut gigi, "
            "pembersihan karang gigi, dan pemasangan gigi palsu. Tindakan cabut gigi "
            "tidak dilakukan saat gusi sedang bengkak dan meradang."
        ),
    },
    {
        "title": "Poli Mata",
        "doc_type": "layanan",
        "floor": "Lantai 2",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#poli_mata",
        "content": (
            "Poli Mata melayani pemeriksaan mata, keluhan mata merah, mata gatal, "
            "penglihatan kabur, minus, plus, silinder, pemeriksaan katarak, dan "
            "pembuatan resep kacamata."
        ),
    },
    {
        "title": "Poli Kandungan dan Kebidanan",
        "doc_type": "layanan",
        "floor": "Lantai 2",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#poli_obgyn",
        "content": (
            "Poli Kandungan dan Kebidanan melayani pemeriksaan kehamilan, kontrol "
            "rutin ibu hamil, USG kandungan, keluhan haid, keputihan, program hamil, "
            "dan konsultasi keluarga berencana atau KB, termasuk pemasangan dan pelepasan "
            "spiral atau IUD, susuk atau implan, suntik KB, dan pil KB. Ibu yang akan melahirkan "
            "ditangani di Ruang Bersalin, bukan di poli."
        ),
    },
    {
        "title": "Area Parkir",
        "doc_type": "layanan",
        "floor": "Ground",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#parkir",
        "content": (
            "Area parkir kendaraan pengunjung tersedia untuk mobil dan sepeda motor, "
            "terletak di area depan dan samping gedung. Karcis parkir diambil di pintu "
            "masuk dan dibayar saat keluar. Parkir khusus karyawan terpisah dari parkir "
            "pengunjung."
        ),
    },
    {
        "title": "Kantin dan Tempat Makan",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#kantin",
        "content": (
            "Kantin menyediakan makanan dan minuman untuk pengunjung serta keluarga "
            "pasien, buka pukul 06.00 sampai 21.00. Makanan pasien rawat inap diatur "
            "terpisah oleh Instalasi Gizi sesuai diet yang ditentukan dokter, jadi "
            "keluarga sebaiknya tidak membawakan makanan dari luar tanpa izin perawat."
        ),
    },
    {
        "title": "ATM dan Layanan Perbankan",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#atm",
        "content": (
            "Mesin ATM tersedia di Lantai 1 dekat lobi utama untuk tarik tunai dan "
            "transfer. Tersedia beberapa bank. Kalau ATM sedang gangguan, pembayaran "
            "di Kasir tetap bisa memakai kartu debit atau QRIS."
        ),
    },
    {
        "title": "Layanan Ambulans",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#ambulans",
        "content": (
            "Layanan ambulans tersedia 24 jam. Mobil ambulans dipakai untuk menjemput "
            "pasien dari rumah, mengantar pasien pulang, rujukan antar "
            "rumah sakit, dan mengantar jenazah. Permintaan ambulans diajukan lewat "
            "IGD atau bagian Informasi. Biaya ambulans dihitung berdasarkan jarak "
            "tempuh."
        ),
    },
    {
        "title": "Fisioterapi dan Rehabilitasi Medik",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#fisio",
        "content": (
            "Fisioterapi atau rehabilitasi medik melayani terapi pasca patah tulang, "
            "nyeri punggung, nyeri lutut, kaku sendi, pemulihan pasca stroke, dan "
            "latihan jalan. Terapi dijadwalkan beberapa kali pertemuan dan memerlukan "
            "surat pengantar dari dokter."
        ),
    },
    {
        "title": "Medical Check Up dan Surat Keterangan Sehat",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#mcu",
        "content": (
            "Medical check up melayani pemeriksaan kesehatan berkala, syarat melamar "
            "kerja, syarat sekolah, dan syarat perjalanan. Surat keterangan sehat dan "
            "surat keterangan sakit, yang juga disebut surat izin sakit atau surat izin "
            "tidak masuk kerja dan sekolah, diterbitkan setelah pemeriksaan dokter. Pemeriksaan "
            "MCU sebaiknya dilakukan pagi hari dalam kondisi puasa."
        ),
    },
    {
        "title": "Informasi dan Cara Membuat Janji Temu",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#janji",
        "content": (
            "Bagian Informasi di lobi Lantai 1 membantu pertanyaan umum, penunjuk arah, "
            "dan pendaftaran janji temu dengan dokter. Janji temu bisa dibuat langsung "
            "di loket atau lewat telepon pada jam kerja. Pasien yang sudah punya janji "
            "tetap perlu mendaftar ulang di loket sebelum masuk poli."
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
