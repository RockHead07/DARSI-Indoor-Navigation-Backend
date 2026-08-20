# RAG Assistant Backend — Design Spec

> **Status:** DISETUJUI UNTUK IMPLEMENTASI (desain, belum ada kode).
> **Tanggal:** 2026-08-20
> **Repo implementasi:** `darsi-backend` (GitHub: `RockHead07/DARSI-Indoor-Navigation-Backend`)
> **Dokumen induk:** `AI-AVATAR-ASSISTANT.md` (repo Unity) — spec ini adalah **Fase 3** dari
> roadmap dokumen tersebut, dikerjakan lebih dulu dan berdiri sendiri.

---

## 1. Ruang Lingkup

### 1.1. Yang dibangun

Backend tanya-jawab berbasis retrieval untuk pertanyaan seputar layanan RS Islam A. Yani:
satu endpoint HTTP yang menerima pertanyaan bahasa natural, mencari informasi relevan dari
basis pengetahuan, lalu menjawab lewat LLM dengan informasi tersebut sebagai konteks.

### 1.2. Yang TIDAK dibangun di spec ini

Ditulis eksplisit supaya tidak ada asumsi menggantung:

| Di luar lingkup | Alasan |
|---|---|
| Avatar VRM 3D, rigging, gesture, viseme | Fase 1/2 di `AI-AVATAR-ASSISTANT.md`, proyek terpisah |
| Text-to-Speech (`audio_url`) | Langkah 4 dokumen induk, ditambahkan di atas fondasi ini nanti |
| Field `gesture` / `expression` di response | Khusus kebutuhan avatar, belum ada konsumennya |
| Keputusan UI (muncul di WebView? panel Unity? tombol mic yang ada?) | Keputusan UX terpisah, dibahas setelah mekanisme retrieval terbukti jalan |
| Mengubah alur voice Unity yang sudah ada | Sudah divalidasi (ADR-024), tidak disentuh |

### 1.3. Hubungan dengan sistem yang sudah jalan

Endpoint ini **berdiri sendiri**. Endpoint `/api/poi/*` dan `/api/presence/*` tidak berubah.
Alur voice di Unity (`OllamaConnector.cs`, Groq primer + Ollama fallback) tetap apa adanya.
Kalau layanan asisten ini mati, navigasi AR tidak ikut terganggu.

---

## 2. Kejujuran Desain: Kenapa RAG Sekarang

Dicatat supaya tidak jadi klaim yang salah di kemudian hari.

**RAG belum diperlukan secara teknis untuk kondisi data hari ini.** Sistem sekarang punya
11 POI dan 55 entri sinonim, seluruhnya muat di satu system prompt (`OllamaConnector.SYSTEM_PROMPT`).
Tanpa langkah retrieval pun sistemnya bekerja, dan untuk ukuran itu pendekatan sekarang justru
yang paling tepat.

Keputusan membangun RAG sekarang adalah **membangun lebih awal untuk kondisi masa depan**
(multi-gedung, ratusan ruangan, SOP dan jadwal yang tidak mungkin dijejalkan ke satu prompt),
diambil sadar oleh pemilik project, dengan pertimbangan tambahan sebagai basis Proyek Akhir
semester 6 dan fondasi Fase 3 dokumen induk.

**Yang TIDAK boleh diklaim:** "memakai RAG" bukan kebaruan. Itu teknologi komoditas.
Lihat §5 untuk klaim kontribusi yang benar-benar bisa dipertahankan.

---

## 3. Arsitektur

```
Unity / WebView
      │  POST /api/assistant/query
      │  { "user_text": "...", "current_floor": "Lantai 1", "building": "..." }
      ▼
┌─────────────────────────────────────────────────────────────┐
│ darsi-backend (FastAPI, Railway)                            │
│                                                             │
│  1. Embed pertanyaan      fastembed (ONNX, lokal)           │
│                                                             │
│  2. Retrieval HYBRID:                                       │
│     ├─ prosa      → pgvector similarity (knowledge_chunks)  │
│     └─ terstruktur→ query SQL biasa    (doctor_schedules)   │
│     (keduanya di-bias oleh floor/building bila dikirim)     │
│                                                             │
│  3. Generate jawaban      Groq (konteks = hasil langkah 2)  │
└─────────────────────────────────────────────────────────────┘
      ▼
  { "answer": "...", "sources": [...], "poi_id": null|"<guid>",
    "contains_simulated_data": true }
```

### 3.1. Embedding lokal, bukan API pihak ketiga

Embedding dihitung di dalam service memakai **ONNX runtime** (`fastembed`), bukan
`sentence-transformers` + `torch`.

Alasan: service ini sekarang sangat ringan (`fastapi`, `uvicorn`, `psycopg`).
`sentence-transformers` menarik `torch` (~800MB-2GB terpasang) plus bobot model,
berisiko menabrak batas memori/image Railway. ONNX memberi sifat yang sama
(lokal, tanpa API key, portable) dengan footprint jauh lebih kecil.

**Angka terverifikasi (2026-08-20):** model `paraphrase-multilingual-MiniLM-L12-v2`
berukuran **0.22 GB**, ditambah `onnxruntime` dan tokenizer, totalnya sekitar
**450-500MB**. (Revisi: draf awal dokumen ini menulis "~180MB", itu taksiran yang
belum diverifikasi dan terlalu optimistis.) Tetap jauh di bawah jalur `torch`,
tapi angka inilah yang dipakai saat menilai batas Railway di §11.

Tidak memakai API embedding eksternal karena itu menambah satu API key dan satu titik
kegagalan baru untuk dijaga, persis masalah yang baru selesai dirapikan di jalur Groq/Ollama.

### 3.2. Groq dipanggil dari server, bukan dari client

Ini sekaligus menutup utang keamanan yang **sudah tercatat di kode**, di
`Assets/Speech Recognition/OllamaConnector.cs`:

> `// ponytail: groqApiKey ikut ter-bundle ke APK (field publik, tersimpan di scene/prefab) —`
> `// ... Sebelum rilis produksi, pindahkan panggilan Groq ke backend proxy supaya key tidak`
> `// pernah ikut ke client.`

Untuk jalur asisten, key hanya ada di environment server (`GROQ_API_KEY`), tidak pernah
ikut ke APK.

---

## 4. Strategi Retrieval: Hybrid

Corpus proyek ini bercampur dua jenis data yang butuh penanganan berbeda.

| Jenis data | Contoh | Cara dicari | Alasan |
|---|---|---|---|
| **Prosa** | SOP pendaftaran, alur BPJS, info layanan, deskripsi ruangan | Vector search (pgvector) | Pertanyaannya bervariasi bentuknya, yang dicari kesamaan **makna** |
| **Terstruktur** | Jadwal praktek dokter | Query SQL biasa | Pertanyaannya **lookup**, bukan pencarian makna |

**Kenapa jadwal dokter sengaja TIDAK di-embed.** Pertanyaan "dr. Ahmad praktek jam berapa"
adalah pencarian baris yang tepat, bukan baris yang mirip. Vector search pada data tabular
cenderung mengembalikan baris yang bentuknya serupa, bukan yang benar. Jam praktek yang salah
di konteks rumah sakit bukan kesalahan kecil, jadi jalur ini harus deterministik.

Hasil dari kedua jalur digabung menjadi satu blok konteks sebelum dikirim ke LLM.

---

## 5. Retrieval Sadar Posisi (klaim kontribusi)

Ini pembeda yang sah untuk proyek ini, karena berasal dari kemampuan yang memang unik di
sistemnya: aplikasi tahu posisi user dari VPS MultiSet setelah localize berhasil.

Request boleh menyertakan `current_floor` dan `building`. Bila ada, keduanya dipakai untuk
**mem-bias** peringkat hasil retrieval, bukan sekadar disimpan.

Perbedaannya konkret:

- RAG biasa: "toilet di mana?" menarik semua chunk soal toilet, jawabannya generik.
- Sistem ini: user terlokalisasi di Lantai 1, retrieval memprioritaskan chunk lantai 1,
  jawabannya menjadi spesifik terhadap posisi user saat itu.

**Aturan penting:** `current_floor` dan `building` bersifat **opsional dan hanya mem-bias**,
tidak pernah mem-filter keras. Kalau user di Lantai 1 bertanya soal layanan yang hanya ada di
Lantai 2, jawabannya tetap harus ditemukan. Filter keras akan membuat sistem "buta" terhadap
informasi di luar lantai user, dan itu kegagalan yang lebih buruk daripada urutan hasil yang
kurang optimal.

Konsekuensi ini juga menjaga kesesuaian dengan ADR-007/ADR-011 (posisi hanya valid setelah
localize berhasil): sebelum localize, field ini kosong dan sistem tetap berfungsi normal.

---

## 6. Skema Data

### 6.1. Ekstensi

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

pgvector adalah ekstensi PostgreSQL open-source standar, bukan fitur proprietary Supabase.
Ini menjaga prinsip portabilitas ADR-001/ADR-014: migrasi antar host Postgres tetap
`pg_dump`/`pg_restore`, syaratnya host tujuan mengaktifkan ekstensi ini.

### 6.2. `knowledge_chunks` (prosa)

| kolom | tipe | keterangan |
|---|---|---|
| `id` | bigint identity PK | |
| `content` | text NOT NULL | teks chunk, inilah yang di-embed |
| `embedding` | vector(384) NOT NULL | lihat §6.4 soal dimensi |
| `doc_type` | text NOT NULL | `sop` / `layanan` / `faq` / `poi_detail` |
| `title` | text NOT NULL | label sumber, dipakai untuk sitasi di response |
| `poi_unity_id` | text NULL, FK → `pois(unity_id)` ON DELETE SET NULL | **sumber sah `poi_id`** di response |
| `building` | text NULL | untuk bias retrieval (§5) |
| `floor` | text NULL | untuk bias retrieval (§5) |
| `is_simulated` | boolean NOT NULL DEFAULT true | siklus data (§7) |
| `source_ref` | text NOT NULL DEFAULT '' | asal chunk (berkas/bagian), untuk telusur balik |
| `created_at` / `updated_at` | timestamptz | mengikuti pola tabel `pois` |

Index: HNSW `vector_cosine_ops` pada `embedding`, plus index biasa pada `doc_type` dan `floor`.

### 6.3. `doctor_schedules` (terstruktur)

| kolom | tipe | keterangan |
|---|---|---|
| `id` | bigint identity PK | |
| `doctor_name` | text NOT NULL | **fiktif**, lihat §7 |
| `specialty` | text NOT NULL | mis. `Anak`, `Penyakit Dalam` |
| `poi_unity_id` | text NULL, FK → `pois(unity_id)` ON DELETE SET NULL | poli/ruangan tempat praktek |
| `day_of_week` | smallint NOT NULL CHECK (1..7) | 1 = Senin |
| `start_time` / `end_time` | time NOT NULL | |
| `is_simulated` | boolean NOT NULL DEFAULT true | |
| `created_at` / `updated_at` | timestamptz | |

### 6.4. Dimensi vektor: terkunci di 384

**Terverifikasi 2026-08-20.** Model yang dipakai:
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` lewat `fastembed`.

| properti | nilai |
|---|---|
| dimensi | **384** |
| ukuran | 0.22 GB |
| Bahasa Indonesia | **didukung**, tercantum eksplisit di daftar 50 bahasa model |

Kandidat lain di fastembed ditolak karena kelebihan ukuran tanpa kebutuhan yang sepadan:
`paraphrase-multilingual-mpnet-base-v2` (768 dim, 1.0 GB) dan `multilingual-e5-large`
(1024 dim, 2.24 GB). Catatan: `multilingual-e5-small` yang sempat disebut di draf awal
**tidak tersedia** di fastembed.

Alasan ini dijadikan aturan eksplisit: mengganti model embedding setelah data masuk berarti
**seluruh isi tabel harus di-embed ulang**, karena vektor dari dua model berbeda tidak
sebanding.

---

## 7. Data Simulasi: Penanganan dan Siklus Hidup

Seluruh isi corpus awal adalah **data simulasi**. RS Islam A. Yani belum memberikan data
operasional sungguhan, dan izin untuk itu belum ada.

### 7.1. Aturan yang mengikat

1. **Setiap baris ditandai di database** (`is_simulated = true`), bukan sekadar dicatat di
   dokumen. Penandaan yang hanya ada di dokumen akan hilang begitu orang lain menyentuh datanya.
2. **Response API menyertakan `contains_simulated_data`.** Kalau ada satu saja sumber simulasi
   yang dipakai menyusun jawaban, flag ini `true`.
3. **Antarmuka apa pun yang menampilkan jawaban WAJIB menampilkan penanda data simulasi**
   selama flag di atas `true`. Ini bukan opsional: nama dokter dan jam praktek fiktif yang
   ditampilkan tanpa penanda, atas nama rumah sakit sungguhan, bisa menyesatkan pasien.
4. **Nama dokter dalam corpus adalah karangan** dan tidak boleh menyerupai nama staf asli
   RS Islam A. Yani.

### 7.2. Jalur pergantian ke data asli

Begitu data sungguhan tersedia:

```sql
DELETE FROM knowledge_chunks WHERE is_simulated = true;
DELETE FROM doctor_schedules  WHERE is_simulated = true;
```

lalu ingest ulang dengan `is_simulated = false`. Tidak ada kemungkinan data simulasi dan data
asli tercampur tanpa disadari, karena pemisahnya kolom, bukan ingatan.

---

## 8. Kontrak API

### 8.1. `POST /api/assistant/query`

Request:

```json
{
  "user_text": "poli anak di mana, dokternya siapa?",
  "current_floor": "Lantai 1",
  "building": "RS Islam Ahmad Yani"
}
```

`current_floor` dan `building` opsional (§5).

Response sukses:

```json
{
  "answer": "Poli Anak berada di Lantai 2. Hari ini dr. Fulan Sp.A praktek sampai pukul 14.00.",
  "sources": [
    { "title": "Poli Anak — Layanan", "doc_type": "layanan", "is_simulated": true },
    { "title": "Jadwal praktek", "doc_type": "schedule", "is_simulated": true }
  ],
  "poi_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "poi_name": "Poli Anak",
  "contains_simulated_data": true
}
```

### 8.2. Aturan `poi_id`: diturunkan, tidak dikarang

`poi_id` diambil dari kolom `poi_unity_id` milik chunk hasil retrieval berperingkat
tertinggi. **LLM tidak pernah diminta menghasilkan GUID.** Model bahasa tidak andal
mereproduksi string identitas panjang secara persis, dan GUID yang salah satu karakter akan
menggagalkan navigasi tanpa gejala yang jelas.

Ini pola yang sama dengan ADR-021 di repo Unity: setiap data punya satu pemilik sah, sisanya
diturunkan, bukan disalin ulang.

Kalau chunk teratas tidak punya `poi_unity_id`, `poi_id` bernilai `null` dan jawabannya tetap
diberikan sebagai teks (tidak semua pertanyaan berujung ke navigasi).

### 8.3. Mode kegagalan

| Kondisi | Perilaku |
|---|---|
| Retrieval tidak menemukan apa pun di atas ambang kemiripan | Jawab jujur bahwa informasinya tidak tersedia. **Jangan** teruskan ke LLM tanpa konteks, karena itu mengundang jawaban karangan. Nilai ambangnya **ditentukan dari set evaluasi (§10)**, bukan ditebak: ambil nilai yang menyaring pertanyaan di luar cakupan tanpa membuang pertanyaan yang seharusnya terjawab |
| Groq gagal / timeout | HTTP 503 dengan pesan jelas. Tidak ada fallback ke Ollama di sisi server (Ollama adalah LAN lokal developer, tidak terjangkau dari Railway) |
| Model embedding gagal dimuat saat startup | Service gagal start dengan pesan eksplisit, bukan diam-diam jalan tanpa kemampuan retrieval |
| `DATABASE_URL` / `GROQ_API_KEY` kosong | Gagal saat startup dengan pesan jelas |

Prinsipnya: gagal dengan berisik di batas sistem, mengikuti pola yang sudah dipakai
`POST /api/poi/sync` (menolak seluruh sync kalau ada kategori tak dikenal).

---

## 9. Draf Corpus Simulasi

Contoh representatif. Isi lengkap ditulis saat implementasi, mengikuti struktur ini.

### 9.1. `doc_type: sop`

> **Alur pendaftaran pasien BPJS rawat jalan.** Pasien BPJS membawa kartu BPJS aktif, KTP, dan
> surat rujukan dari Faskes 1 yang masih berlaku. Rujukan berlaku 90 hari sejak diterbitkan.
> Pendaftaran dilayani di loket Pendaftaran BPJS, Lantai 1, mulai pukul 07.00. Setelah
> mendapat nomor antrean, pasien menunggu panggilan di ruang tunggu poli tujuan.
> *(title: "Alur Pendaftaran BPJS Rawat Jalan", floor: "Lantai 1", is_simulated: true)*

> **Alur pasien IGD.** Pasien gawat darurat langsung menuju IGD tanpa mendaftar lebih dulu.
> Pendaftaran administrasi diurus keluarga setelah pasien ditangani. IGD melayani 24 jam.
> *(title: "Alur Pasien IGD", floor: "Lantai 1", is_simulated: true)*

### 9.2. `doc_type: layanan`

> **Farmasi.** Melayani penebusan resep pasien rawat jalan dan rawat inap. Jam layanan
> 07.00 sampai 21.00. Resep BPJS dilayani di loket terpisah dari resep umum.
> *(title: "Layanan Farmasi", poi_unity_id: `<guid Farmasi>`, is_simulated: true)*

### 9.3. `doc_type: faq`

> **Apakah bisa berobat tanpa rujukan?** Pasien umum bisa langsung mendaftar tanpa rujukan.
> Pasien BPJS memerlukan rujukan dari Faskes 1, kecuali kasus gawat darurat yang ditangani IGD.
> *(title: "FAQ: Berobat tanpa rujukan", is_simulated: true)*

### 9.4. `doctor_schedules`

| doctor_name | specialty | day_of_week | start | end |
|---|---|---|---|---|
| dr. Fulan Hidayat, Sp.A | Anak | 1 (Senin) | 08.00 | 14.00 |
| dr. Fulanah Rahmawati, Sp.PD | Penyakit Dalam | 2 (Selasa) | 09.00 | 15.00 |

Nama memakai pola "Fulan/Fulanah" yang dalam bahasa Indonesia dipahami sebagai penanda nama
karangan, sesuai aturan §7.1 poin 4.

---

## 10. Evaluasi

Tanpa pengukuran, "RAG-nya bagus" hanya perasaan. Disiapkan **set evaluasi kecil berisi 15-20
pasangan** pertanyaan dan chunk yang seharusnya terambil, disimpan sebagai berkas di repo.

Metrik yang dicatat: berapa persen pertanyaan yang chunk benarnya masuk 3 besar hasil retrieval.

Ini juga yang membuat laporan Proyek Akhir bisa memuat angka hasil pengukuran, bukan klaim
tanpa data. Catatan jujur yang harus ikut dilaporkan: **evaluasi ini berjalan di atas corpus
simulasi**, jadi ia mengukur kualitas mekanisme retrieval, bukan kesiapan sistem terhadap
pertanyaan pasien sungguhan.

---

## 11. Deployment

- Menyusul pola yang ada: `Procfile` + variabel environment di Railway.
- Variabel baru: `GROQ_API_KEY`.
- **Model embedding dimuat sekali saat startup** (di `lifespan`, mengikuti pola pool koneksi
  yang sudah ada), bukan per-request. Tanpa ini, request pertama akan lambat seperti gejala
  pre-warm Ollama yang sudah dikenal di repo Unity.
- Perlu diperhatikan saat implementasi: ukuran image dan memori Railway setelah `fastembed`
  masuk. Kalau ternyata melewati batas paket yang dipakai, itu keputusan biaya yang harus
  disampaikan ke pemilik project, bukan diakali diam-diam dengan menurunkan kualitas model.

---

## 12. Hal yang Diverifikasi Saat Implementasi

Ketiganya **sudah diverifikasi 2026-08-20**, sebelum plan implementasi ditulis:

| # | Pertanyaan | Hasil |
|---|---|---|
| 1 | Model embedding multilingual di fastembed, dan dimensinya | `paraphrase-multilingual-MiniLM-L12-v2`, **384 dim**, 0.22 GB, Bahasa Indonesia didukung (§6.4) |
| 2 | Jejak dependensi ONNX terhadap Railway | **~450-500MB** total (§3.1). Angka draf awal "180MB" salah dan sudah dikoreksi |
| 3 | pgvector di Supabase Postgres yang dipakai | **Tersedia v0.8.2** (mendukung HNSW), tapi **belum aktif**. Perlu `CREATE EXTENSION vector;` sebagai langkah migrasi pertama |

Sisa risiko yang masih harus diukur saat implementasi berjalan, bukan dari dokumen:
pemakaian memori runtime sesungguhnya di Railway setelah model dimuat. Kalau melewati
batas paket yang dipakai, itu keputusan biaya yang disampaikan ke pemilik project, bukan
diakali dengan menurunkan kualitas model.
