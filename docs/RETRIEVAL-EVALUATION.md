# Evaluasi Retrieval RAG Assistant — Temuan dan Metodologi

> **Tanggal pengukuran:** 2026-08-20
> **Sistem yang diukur:** retrieval hybrid (pgvector + full-text `indonesian`, digabung RRF)
> **Corpus:** 25 dokumen **SIMULASI** (bukan data operasional RS)
> **Model embedding:** `paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensi
> **Spec:** `docs/superpowers/specs/2026-08-20-rag-assistant-backend-design.md`

---

## 1. Angka yang Layak Dilaporkan

> **recall@3 = 71,9%** pada set uji bersih berisi 32 pertanyaan.
> Khusus 28 pertanyaan dalam cakupan: **78,6%**.
> Diukur di atas corpus simulasi 25 dokumen.

Kalimat yang aman dipakai di laporan:

> *"Sistem retrieval hybrid mencapai recall@3 sebesar 71,9% pada set uji tertahan
> (held-out) berisi 32 pertanyaan, diukur di atas corpus simulasi 25 dokumen."*

**Jangan pernah melaporkan angka 100%.** Angka itu ada, tapi berasal dari set yang
kegagalannya sudah dipakai memperbaiki sistem, jadi tidak sah. Alasan lengkapnya
di §4.

---

## 2. Kenapa Ada Empat Set Uji

Set uji "terbakar" begitu kegagalannya dipakai memperbaiki sistem. Setelah itu ia
mengukur seberapa cocok sistem dengan dirinya sendiri, bukan mutu sistem.

| Set | Jumlah | Status | Pernah dipakai untuk |
|---|---|---|---|
| `eval_retrieval.json` | 18 | terbakar | menyetel ambang skor |
| `eval_holdout.json` | 18 | terbakar | memperluas kosakata corpus |
| `eval_test.json` | 28 | terbakar | menambal 4 celah kosakata |
| `eval_test2.json` | 32 | **bersih** | belum dipakai memperbaiki apa pun |

Aturan kerjanya: **begitu kamu melihat soal mana yang gagal lalu memperbaiki sistem
berdasarkan itu, set tersebut pensiun sebagai alat ukur.** Tulis set baru.

---

## 3. Perjalanan Pengukuran

| Tahap | tuning | dev | test-1 | test-2 |
|---|---|---|---|---|
| Implementasi awal (vector saja, ambang mutlak 0.35) | 88,9% | — | — | — |
| Ambang 0.30, perkayaan corpus IGD | 94,4% | — | — | — |
| Ambang relatif + pecah chunk IGD | 100% | 72,2% | — | — |
| Hybrid RRF + stopword + celah "sholat" | 100% | 72,2% | — | — |
| Perluas corpus 13 → 25 dokumen | 94,4% | 88,9% | **85,7%** | — |
| Tambal 4 celah kosakata | 88,9% | 88,9% | **100%** | **71,9%** |

Perhatikan baris terakhir. Itu inti seluruh laporan ini.

---

## 4. Temuan Utama: Set Uji yang Terbakar Memberi Angka Palsu

Empat celah kosakata ditambal berdasarkan kegagalan di `test-1`:

- Poli Kandungan menulis "keluarga berencana atau KB", tapi tidak "spiral" atau "IUD"
- Ambulans menulis "menjemput pasien", tapi tidak "mobil"
- MCU menulis "surat keterangan sakit", tapi tidak "surat izin sakit"
- Poli Penyakit Dalam menulis "hipertensi", tapi tidak "tekanan darah tinggi"

Hasilnya:

| | Sebelum tambal | Sesudah tambal |
|---|---|---|
| `test-1` (celahnya ditambal) | 85,7% | **100%** |
| `test-2` (bersih, tak tersentuh) | — | **71,9%** |

**Menambal membuat set yang ditambal jadi sempurna, tapi tidak menular sama sekali
ke pertanyaan lain.** Kalau proses berhenti di angka 100%, yang dilaporkan adalah
angka palsu.

Ini juga menjawab pertanyaan "apakah masih bisa dioptimalkan": menambal kosakata
= mengejar kasus satuan, bukan menaikkan kemampuan sistem.

---

## 5. Temuan: Kemiripan Cosine Tidak Terkalibrasi untuk Menilai Relevansi

Rancangan awal (spec §8.3) mengasumsikan ada nilai ambang yang bisa memisahkan
pertanyaan dalam-cakupan dari luar-cakupan. **Asumsi itu terbukti salah.**

Skor cosine terhadap corpus:

| Pertanyaan | Jenis | Skor |
|---|---|---|
| "jadwal kereta ke bandung" | **sampah** | **0,348** |
| "mau di foto tulang yang patah" | sah | 0,237 |
| "cara bikin sim online" | **sampah** | 0,222 |
| "sebelum usg boleh makan dulu ga" | sah | 0,215 |

Pertanyaan sampah mendapat skor **lebih tinggi** daripada pertanyaan yang sah.
Tidak ada satu nilai ambang pun yang memisahkan keduanya.

Diuji ulang pada model kedua yang lebih besar, hasilnya sama, bahkan lebih buruk:

| Model | min skor SAH | maks skor SAMPAH | Bisa dipisah? |
|---|---|---|---|
| MiniLM-L12 (384 dim, 0,22 GB) | 0,220 | 0,343 | Tidak |
| mpnet-base-v2 (768 dim, 1,0 GB) | 0,233 | **0,470** | Tidak, lebih buruk |

**Kesimpulan:** ini sifat kemiripan cosine, bukan kelemahan satu model. Model yang
lebih besar membuatnya **lebih percaya diri, bukan lebih benar.** Karena itu
migrasi ke mpnet dibatalkan: 0,8 GB memori tambahan tanpa perbaikan terukur.

**Konsekuensi arsitektur:** keputusan relevansi dipindahkan ke LLM yang membaca
teks chunk-nya (`generation._SYSTEM_PROMPT`), bukan ditentukan angka ambang.

---

## 6. Temuan: Gerbang Skor Merugikan Lebih Banyak daripada Menolong

Sweep nilai gerbang terhadap `test-2`:

| MIN_TOP_SCORE | recall@3 |
|---|---|
| 0,22 (dipakai sekarang) | 71,9% |
| **0,15** | **81,2%** |
| 0,00 (tanpa gerbang) | 78,1% |

Pada 0,22, gerbang memblokir **4 pertanyaan yang sah** ("kena air panas melepuh",
"tangan keseleo mau dilihat tulangnya", "pengen beli minum", "ada yang nganter
jenazah ga") sambil tetap **meloloskan 3 pertanyaan sampah**.

**Belum diterapkan.** Menurunkannya berdasarkan `test-2` akan membakar set itu
juga, persis kesalahan yang dijelaskan di §4. Perlu set uji ke-5 untuk memvalidasi.

---

## 7. Temuan Teknis Lain

### 7.1. Vector saja tidak cukup, full-text wajib ada

"igd buka 24 jam tidak" membuat model menaruh chunk **Musholla** di peringkat 1,
padahal kata "igd" ada persis di pertanyaan dan di judul chunk yang benar. Model
semantik gagal memberi bobot pada nama entitas, dan itu justru pekerjaan sepele
bagi pencarian kata.

PostgreSQL punya konfigurasi text search **`indonesian`** bawaan (stemming +
stopword), jadi ini gratis tanpa dependensi tambahan. Digabung dengan vector lewat
**Reciprocal Rank Fusion**, yang menggabung lewat *peringkat*, bukan skor mentah,
sehingga masalah skala skor yang berpindah antar pertanyaan tidak ikut terbawa.

### 7.2. Dilusi chunk: satu chunk = satu topik

Chunk "Alur Pasien IGD" diperkaya daftar kondisi darurat, dan akibatnya pertanyaan
"igd buka 24 jam tidak" **tidak lagi mengenainya** karena jam operasional
tenggelam di teks yang panjang. Recall sempat turun 94,4% → 83,3%.

Diperbaiki dengan memecahnya jadi chunk terpisah "Jam Operasional IGD". Recall naik
ke 94,4%.

### 7.3. Stemmer Indonesia menciptakan kecocokan palsu

Stemmer `indonesian` memotong **"maupun" menjadi "mau"**, sehingga kata tanya "mau"
pada "mau sholat di mana" mencocoki chunk yang memuat "maupun" dan menenggelamkan
jawaban yang benar. Diperbaiki dengan daftar stopword di sisi pertanyaan.

### 7.4. Perkayaan kosakata memang berhasil, tapi hanya untuk kasusnya sendiri

Contoh terukur: chunk IGD diberi kata "kecelakaan", "cedera", "pendarahan".
Skor untuk "kalau kecelakaan harus ke mana" naik **0,126 → 0,339** dan langsung
jadi peringkat 1. Sebelumnya pertanyaan darurat itu dijawab **kosong**, dan di
konteks rumah sakit itu bukan kesalahan statistik biasa.

---

## 8. Batasan yang Wajib Disebut Saat Melaporkan

1. **Corpus simulasi.** 25 dokumen karangan, bukan SOP atau data operasional RS
   Islam A. Yani. Izin data asli belum ada. Nama dokter memakai pola
   "Fulan/Fulanah" supaya jelas fiktif.
2. **Set uji kecil.** 32 soal, jadi satu soal bernilai sekitar 3%. Selisih 78,1%
   vs 81,2% pada §6 setara satu soal, itu derau, bukan perbedaan nyata.
3. **Soal uji ditulis penulis corpus yang sama.** Ada kecenderungan susunan
   katanya sejalan. Pertanyaan pasien sungguhan akan lebih liar.
4. **Yang diukur baru retrieval, bukan mutu jawaban akhir.** Kemampuan LLM menolak
   pertanyaan di luar cakupan **belum diukur end-to-end**, padahal sekarang justru
   di situ letak keputusan relevansi (§5).

---

## 9. Yang TIDAK Boleh Diklaim

- **Jangan** melaporkan 100% atau 85,7%. Kedua set itu sudah terbakar.
- **Jangan** menyebut "memakai RAG" sebagai kebaruan. RAG teknologi komoditas.
  Klaim kontribusi yang sah ada di spec §5 (retrieval sadar posisi berbasis VPS).
- **Jangan** menyatakan sistem siap melayani pasien. Corpusnya simulasi dan
  penolakan di luar cakupan belum diuji end-to-end.

---

## 10. Langkah Berikutnya, Berurut Manfaat

1. **Data asli RS.** Ini yang paling menaikkan mutu, jauh melebihi penyetelan
   apa pun. Corpus 25 dokumen karangan tidak akan pernah sekaya SOP sungguhan.
2. **Perbesar set uji** ke 100+ soal supaya angkanya tahan derau, idealnya
   pertanyaannya dikumpulkan dari orang lain, bukan ditulis sendiri.
3. **Uji end-to-end penolakan LLM** untuk pertanyaan di luar cakupan (§8 poin 4).
4. **Terapkan MIN_TOP_SCORE 0,15** dengan validasi set uji baru (§6).
5. Ganti model embedding: **tidak disarankan** (§5), sudah diuji dan tidak menolong.

---

## Cara Menjalankan Ulang Pengukuran

```bash
export DATABASE_URL="postgresql://postgres:darsi@localhost:5433/darsi"
python -m scripts.ingest_corpus
python -m scripts.eval_retrieval
```

Postgres lokal harus memakai image `pgvector/pgvector:pg16`, bukan `postgres:16`
polos, karena ekstensi `vector` tidak ada di image polos.

---

## 11. Evaluasi End-to-End: LLM-as-a-Judge Benchmark Suite (2026-08-22)

Untuk melengkapi pengukuran retrieval di atas, dibangun evaluasi end-to-end dengan metode **LLM-as-a-Judge** (`scripts/eval_llm_judge.py`) yang menguji respons akhir asisten RAG di seluruh spektrum kasus rumah sakit.

### Hasil Pengujian (52 Skenario)
* **Model Generator:** Groq (`openai/gpt-oss-20b`)
* **Model Judge:** Groq (`openai/gpt-oss-20b`)
* **Tingkat Kelulusan:** **52 / 52 Passed (100.0%)**

| Kategori Skenario | Kasus Diuji | Hasil | Fokus Evaluasi |
|---|---|---|---|
| **Gawat Darurat & Trauma** | 10 | 10/10 (100%) | Wajib triase ke **IGD**, anti-salah arah ke parkir motor/loket antre |
| **Poliklinik & Jadwal Dokter** | 10 | 10/10 (100%) | Lookup jadwal dokter & rujukan lantai poli (Poli Anak, Dalam, Obgyn, Gigi, Mata) |
| **Layanan Farmasi & Obat** | 6 | 6/6 (100%) | Tebus resep BPJS/Umum, jam buka apotek, obat racikan |
| **Diagnostik & Penunjang** | 6 | 6/6 (100%) | Rontgen dada (Ruang X-Ray), USG puasa, CT-Scan (Radiologi), cek darah (Lab) |
| **Administrasi & Pembayaran** | 6 | 6/6 (100%) | Loket BPJS, Kasir QRIS, Rekam Medis, pendaftaran tanpa rujukan |
| **Fasilitas Umum & Spasial** | 10 | 10/10 (100%) | Bahasa gaul (kebelet kencing -> Toilet), Musholla, Lift, Parkir Mobil/Motor, Lobi |
| **Out-of-Scope / Chitchat** | 4 | 4/4 (100%) | Penolakan santun & tegas tanpa halusinasi |

### Cara Menjalankan LLM-as-a-Judge Benchmark

```bash
# Menjalankan terhadap live HTTP API
export TARGET_URL="https://<tunnel-url>.trycloudflare.com"
export GROQ_API_KEY="gsk_..."
python -m scripts.eval_llm_judge

# Atau menjalankan langsung terhadap database PostgreSQL lokal
export DATABASE_URL="postgresql://postgres:darsi@localhost:5433/darsi"
export GROQ_API_KEY="gsk_..."
python -m scripts.eval_llm_judge
```
