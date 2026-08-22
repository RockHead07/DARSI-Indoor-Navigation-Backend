"""Corpus SIMULASI untuk RAG Assistant.

PERINGATAN: seluruh isi berkas ini KARANGAN. RS Islam A. Yani adalah rumah sakit
sungguhan, tapi belum memberikan data operasional dan izinnya belum ada. Nama
dokter memakai pola "Fulan/Fulanah" supaya jelas fiktif.

Semua baris masuk DB dengan is_simulated = true. Saat data asli tersedia:
    DELETE FROM knowledge_chunks WHERE is_simulated = true;
    DELETE FROM doctor_schedules  WHERE is_simulated = true;
lalu ingest ulang dengan is_simulated = false.
"""

# Mapping GUID resmi dari scene Unity (TestingHCM.unity / POIData):
# IGD: 033e7541-05e9-4726-bc84-0825c5d12e10 (Lantai 1)
# Farmasi: de030876-deb4-427e-92af-382a38a2d669 (Lantai 1)
# Radiologi: 207c8f68-f4ea-45de-9f0f-7d7be08cd633 (Lantai 1)
# Ruang X-Ray: 8e3021a9-76a3-48ab-9e87-f5d832a3921c (Lantai 1)
# Resepsionis: b328d86f-541a-4148-b82c-e4fc2a5939ea (Lantai 1)
# Toilet: dc295a0d-434d-4c41-9728-5bd9f8a0fb0b (Lantai 1)
# Lift Lantai 1: d52a7a82-ce07-47d3-a5ba-d2b07c678a0c (Lantai 1)
# Lift Lantai 2: b3a375ee-9aa8-476a-bd6a-8a68b7308896 (Lantai 2)
# Parkir Mobil: 58139f04-3ca8-4f9c-87b7-f0a9887ed0de (Ground)
# Parkir Motor Karyawan: e42f1d1f-5b4d-45a5-93e4-07e88a6a6618 (Ground)
# Ground (Lobi Utama): eb8f0e33-2832-484e-862a-c123b2259b05 (Ground)

CHUNKS: list[dict] = [
    {
        "title": "Alur Pasien IGD dan Penanganan Darurat",
        "doc_type": "sop",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": "033e7541-05e9-4726-bc84-0825c5d12e10",
        "source_ref": "corpus_simulasi.py#igd",
        "content": (
            "Alur pasien IGD (Instalasi Gawat Darurat) dan unit emergency. Pasien gawat "
            "darurat langsung menuju IGD di Lantai 1 tanpa mendaftar lebih dulu di loket biasa. "
            "IGD menangani korban kecelakaan lalu lintas, tabrakan motor, tabrakan mobil, "
            "jatuh dari ketinggian, luka robek, pendarahan hebat, patah tulang, cedera kepala, "
            "luka bakar, pingsan, tidak sadarkan diri, kejang-kejang, sesak napas akut, "
            "nyeri dada mendadak, serangan jantung, stroke, keracunan makanan/zat kimia, "
            "dan demam tinggi mendadak atau step pada anak. Jika kondisi darurat atau "
            "mengancam nyawa, segera masuk IGD. Administrasi diurus keluarga belakangan."
        ),
    },
    {
        "title": "Jam Operasional IGD",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": "033e7541-05e9-4726-bc84-0825c5d12e10",
        "source_ref": "corpus_simulasi.py#igd_jam",
        "content": (
            "IGD buka 24 jam nonstop setiap hari termasuk Sabtu, Minggu, dan hari libur nasional. "
            "Layanan gawat darurat, dokter jaga, perawat emergency, dan ambulans siap 24 jam. "
            "Di luar jam buka poliklinik rawat jalan, IGD adalah unit utama yang melayani pasien darurat."
        ),
    },
    {
        "title": "Layanan Farmasi dan Pengambilan Obat",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": "de030876-deb4-427e-92af-382a38a2d669",
        "source_ref": "corpus_simulasi.py#farmasi",
        "content": (
            "Layanan Farmasi dan Apotek RS melayani penebusan resep obat dokter, pembelian obat bebas, "
            "serta obat racikan untuk pasien rawat jalan maupun rawat inap. Farmasi berada di Lantai 1. "
            "Jam operasional apotek adalah pukul 07.00 sampai 21.00 WIB. Resep BPJS dilayani di loket "
            "khusus BPJS, sedangkan resep umum/pribadi di loket farmasi umum."
        ),
    },
    {
        "title": "Alur Pendaftaran BPJS Rawat Jalan",
        "doc_type": "sop",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": "b328d86f-541a-4148-b82c-e4fc2a5939ea",
        "source_ref": "corpus_simulasi.py#bpjs",
        "content": (
            "Alur pendaftaran pasien BPJS rawat jalan. Pasien membawa kartu BPJS/KIS aktif, KTP, dan "
            "surat rujukan dari Faskes 1 (Puskesmas/Klinik) yang masih berlaku. Rujukan berlaku 90 hari. "
            "Pendaftaran dilayani di Loket Resepsionis / Pendaftaran BPJS di Lantai 1 mulai pukul 07.00. "
            "Setelah mengambil nomor antrean dan diverifikasi petugas, pasien menuju ruang tunggu poli tujuan."
        ),
    },
    {
        "title": "Alur Rawat Jalan Pasien Umum",
        "doc_type": "sop",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": "b328d86f-541a-4148-b82c-e4fc2a5939ea",
        "source_ref": "corpus_simulasi.py#umum",
        "content": (
            "Alur rawat jalan pasien umum (non-BPJS/bayar pribadi). Pasien umum mendaftar langsung di Loket "
            "Resepsionis / Pendaftaran Lantai 1 dengan menunjukkan KTP tanpa perlu surat rujukan. Pendaftaran "
            "dibuka pukul 07.00 hingga 15.00 WIB. Setelah pemeriksaan di poli selesai, pembayaran dilakukan di Kasir."
        ),
    },
    {
        "title": "Layanan Radiologi",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": "207c8f68-f4ea-45de-9f0f-7d7be08cd633",
        "source_ref": "corpus_simulasi.py#radiologi",
        "content": (
            "Instalasi Radiologi melayani pemeriksaan radiologi diagnostik lengkap, meliputi USG perut, "
            "USG kandungan, CT scan, dan pemeriksaan rontgen sinar-X. Pasien yang memerlukan pemeriksaan "
            "organ dalam atau dugaan patah tulang dirujuk ke Radiologi di Lantai 1. Pemeriksaan memerlukan "
            "surat pengantar dokter. Sebelum USG perut, pasien wajib puasa 6 jam. Layanan buka 08.00-20.00 "
            "dan 24 jam untuk pasien darurat IGD."
        ),
    },
    {
        "title": "Ruang X-Ray dan Foto Rontgen",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": "8e3021a9-76a3-48ab-9e87-f5d832a3921c",
        "source_ref": "corpus_simulasi.py#xray",
        "content": (
            "Ruang X-Ray (Foto Rontgen) melayani foto rontgen dada (thorax), rontgen tulang, rontgen gigi, "
            "dan rontgen kepala/anggota gerak untuk mendeteksi retak tulang, patah tulang, atau infeksi paru. "
            "Ruang X-Ray berada di bagian Radiologi Lantai 1."
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
            "Laboratorium melayani cek darah lengkap, tes darah, periksa urine atau air seni, "
            "dahak, dan sampel lain. Tersedia pemeriksaan gula darah, kolesterol, asam "
            "urat, dan fungsi ginjal. Pengambilan sampel darah puasa dilayani pukul "
            "07.00 sampai 09.00 di Lantai 1. Hasil pemeriksaan rutin keluar di hari yang sama."
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
            "Poli Anak berada di Lantai 2 dan melayani pemeriksaan kesehatan anak, bayi, balita, "
            "imunisasi rutin, serta konsultasi tumbuh kembang. Pasien anak dengan kondisi gawat darurat "
            "seperti demam sangat tinggi, kejang, atau sesak napas disarankan langsung menuju IGD di Lantai 1."
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
            "Poli Penyakit Dalam berada di Lantai 2, melayani konsultasi dan pengobatan penyakit kronis "
            "pada orang dewasa seperti diabetes (kencing manis), hipertensi (darah tinggi), kolesterol, "
            "asam urat, maag/GERD lambung, tipes, gangguan ginjal, dan gangguan pencernaan."
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
            "kasus gawat darurat yang langsung ditangani IGD."
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
        "poi_unity_id": "b328d86f-541a-4148-b82c-e4fc2a5939ea",
        "source_ref": "corpus_simulasi.py#faq_rekam_medis",
        "content": (
            "Permintaan salinan rekam medis, fotokopi hasil pemeriksaan, hasil lab, "
            "atau resume medis diajukan di bagian Administrasi / Rekam Medis Lantai 1 dengan membawa "
            "KTP pasien. Permintaan oleh keluarga memerlukan surat kuasa. Berkas "
            "selesai dalam 3 hari kerja."
        ),
    },
    {
        "title": "Kasir dan Cara Pembayaran",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": "b328d86f-541a-4148-b82c-e4fc2a5939ea",
        "source_ref": "corpus_simulasi.py#kasir",
        "content": (
            "Loket Kasir melayani pembayaran biaya pemeriksaan dokter, obat farmasi, dan tindakan medis. "
            "Pembayaran bisa dilakukan secara tunai, kartu debit, kartu kredit, dan QRIS. Pasien umum "
            "membayar setelah pemeriksaan selesai. Loket Kasir berada di Lantai 1 dekat loket Pendaftaran."
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
            "Rawat inap atau opname tersedia dalam kelas 3, kelas 2, kelas 1, dan VIP di Lantai 2. "
            "Pendaftaran rawat inap diurus di bagian Admisi setelah dokter menyatakan pasien perlu menginap."
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
            "Poli Gigi berada di Lantai 2 melayani sakit gigi, gigi berlubang, tambal gigi, cabut gigi, "
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
            "Poli Mata berada di Lantai 2 melayani pemeriksaan mata, keluhan mata merah, mata gatal, "
            "penglihatan kabur, rabun jauh/dekat, katarak, dan pembuatan resep kacamata."
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
            "Poli Kandungan dan Kebidanan berada di Lantai 2 melayani pemeriksaan kehamilan, kontrol "
            "rutin ibu hamil, USG kandungan, keluhan haid, keputihan, program hamil, "
            "dan konsultasi keluarga berencana (KB). Ibu yang akan melahirkan ditangani di Ruang Bersalin."
        ),
    },
    {
        "title": "Area Parkir Mobil",
        "doc_type": "layanan",
        "floor": "Ground",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": "58139f04-3ca8-4f9c-87b7-f0a9887ed0de",
        "source_ref": "corpus_simulasi.py#parkir_mobil",
        "content": (
            "Area Parkir Mobil berada di area Ground / pelataran depan rumah sakit untuk kendaraan roda empat "
            "pengunjung dan pasien. Karcis parkir mobil diambil di pintu gerbang masuk."
        ),
    },
    {
        "title": "Area Parkir Sepeda Motor",
        "doc_type": "layanan",
        "floor": "Ground",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": "e42f1d1f-5b4d-45a5-93e4-07e88a6a6618",
        "source_ref": "corpus_simulasi.py#parkir_motor",
        "content": (
            "Area Parkir Motor Karyawan dan Pengunjung berada di sisi samping area Ground untuk kendaraan roda dua. "
            "Harap kunci ganda sepeda motor Anda."
        ),
    },
    {
        "title": "Fasilitas Lift dan Elevator",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": "d52a7a82-ce07-47d3-a5ba-d2b07c678a0c",
        "source_ref": "corpus_simulasi.py#lift",
        "content": (
            "Fasilitas Lift / Elevator tersedia untuk akses cepat antara Lantai 1 (Ground) dan Lantai 2. "
            "Lift diprioritaskan untuk pasien berkursi roda, brankar/tandu, lansia, dan ibu hamil."
        ),
    },
    {
        "title": "Lobi Utama dan Informasi",
        "doc_type": "layanan",
        "floor": "Ground",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": "eb8f0e33-2832-484e-862a-c123b2259b05",
        "source_ref": "corpus_simulasi.py#lobi",
        "content": (
            "Lobi Utama dan pintu masuk rumah sakit berada di lantai Ground. Tempat drop off pasien, "
            "meja resepsionis, dan petugas keamanan siap membantu mengarahkan pengunjung."
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
            "pasien di Lantai 1, buka pukul 06.00 sampai 21.00 WIB."
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
            "Mesin ATM Center tersedia di Lantai 1 dekat lobi utama untuk tarik tunai dan transfer berbagai bank."
        ),
    },
    {
        "title": "Layanan Ambulans",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": "033e7541-05e9-4726-bc84-0825c5d12e10",
        "source_ref": "corpus_simulasi.py#ambulans",
        "content": (
            "Layanan ambulans gawat darurat tersedia 24 jam di unit IGD Lantai 1 untuk jemput pasien darurat atau rujukan."
        ),
    },
    {
        "title": "Fasilitas Toilet dan Kamar Mandi",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": "dc295a0d-434d-4c41-9728-5bd9f8a0fb0b",
        "source_ref": "corpus_simulasi.py#toilet",
        "content": (
            "Fasilitas Toilet dan Kamar Mandi umum tersedia di Lantai 1 (dekat lobi dan musholla) serta di Lantai 2. "
            "Digunakan untuk buang air kecil, buang air besar (BAB), cuci tangan, dan sanitasi pengunjung (pria, wanita, difabel)."
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
