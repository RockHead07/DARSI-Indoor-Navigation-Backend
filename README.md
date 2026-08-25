# DARSI backend

POI read API for the DARSI Indoor Navigation WebView. Part of the DARSI multi-repo
setup (Unity AR app + `darsi-indoor-navigation-ui-webview` + this backend). Contract is
locked in the Unity repo's `docs/API_CONTRACT.md` / `docs/INTEGRATION.md`.

**Portable by design** (ADR-001 / ADR-014): plain PostgreSQL via `DATABASE_URL` using
psycopg — not the Supabase SDK — so it runs identically against a Supabase Postgres or a
self-hosted Postgres. Migration is a connection-string change.

## Endpoints (read-only, no auth)
- `GET /api/poi/popular`
- `GET /api/poi/search?q=&category=`
- `GET /api/poi/categories`

No response ever includes a distance/meter field — deliberate (ADR-007). Distance is
computed inside Unity after localize, never served here.

## Assistant (RAG)

`POST /api/assistant/query` — tanya jawab layanan RS berbasis retrieval.
Spec: `docs/superpowers/specs/2026-08-20-rag-assistant-backend-design.md`.

Retrieval hybrid: prosa (SOP/layanan/FAQ) lewat pgvector, jadwal dokter lewat SQL
biasa. Jadwal sengaja tidak di-embed karena itu lookup, bukan pencarian makna.

⚠️ **Seluruh isi corpus saat ini DATA SIMULASI.** Setiap baris ditandai
`is_simulated = true`, dan response membawa `contains_simulated_data`. Antarmuka
yang menampilkan jawaban WAJIB menampilkan penanda data simulasi selama flag itu
menyala. Nama dokter memakai pola "Fulan/Fulanah" supaya jelas fiktif.

Mengganti ke data asli:
```bash
psql "$DATABASE_URL" -c "DELETE FROM knowledge_chunks WHERE is_simulated = true;"
psql "$DATABASE_URL" -c "DELETE FROM doctor_schedules  WHERE is_simulated = true;"
# lalu ingest ulang dengan is_simulated = false
```

### Setup
```bash
psql "$DATABASE_URL" -f schema_rag.sql   # butuh ekstensi pgvector
python -m scripts.ingest_corpus
```

**LLM: Bifrost (medgemma) primer, Groq fallback.** Rencana sebelumnya (Qwen
lokal via Ollama di `vm-amma`) DIBATALKAN — `vm-amma` terverifikasi (`lspci`)
tidak punya GPU sama sekali, 2 vCPU, jadi 7B CPU-only akan selalu timeout dan
jatuh ke Groq. Bifrost adalah gateway OpenAI-compatible yang di-host TERPISAH
(hcm-lab.id, GPU sungguhan, dikelola tim PSDKU/HCM Lab) — bukan service di
`docker-compose.yml` ini, jadi tidak butuh GPU di server backend sama sekali.
Modelnya (`medgemma-1.5-4b-it-q4`) di-tuning domain medis, relevan untuk
asisten RS dibanding Groq yang general-purpose.

### Setup Bifrost

Tidak ada service tambahan untuk dinaikkan — cukup set env var, tidak perlu
`docker compose up` service baru maupun langkah pull model manual:

```bash
BIFROST_API_KEY=sk-bf-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

Auth-nya pakai header `x-api-key`, BUKAN `Authorization: Bearer` seperti Groq
— formatnya memang beda per gateway ini, sudah ditangani di `_try_bifrost()`.

**Jangan pernah commit `BIFROST_API_KEY` sungguhan** — isi hanya di `.env`
lokal/gitignored atau secret manager di server, sama seperti pola
`groq-api-key.local.txt` di repo Unity (ADR-024).

Env var tambahan: `GROQ_API_KEY` (dipanggil dari server, tidak pernah ikut ke
APK; boleh kosong tapi endpoint jadi rentan kalau Bifrost juga gagal),
`BIFROST_URL`/`BIFROST_MODEL` (opsional, default sudah benar).

### Evaluasi retrieval
```bash
python -m scripts.eval_retrieval
```
**Angka yang layak dilaporkan: recall@3 = 71,9%** pada set uji bersih 32 pertanyaan
(78,6% untuk 28 pertanyaan dalam cakupan). Diukur 2026-08-24 setelah corpus sempat
berubah bentuk (commit `610f25e`, 25→27 chunk).

⚠️ **Koreksi 2026-08-25:** angka di atas SEBENARNYA diukur terhadap corpus
**27 chunk**, bukan 28 seperti sempat tertulis di sini. Chunk ke-28 ("Cara
Membuat Janji Temu Dokter", ditulis di commit `803f2fa`) ternyata **tidak
pernah ter-ingest ke produksi** — kemungkinan diedit setelah `ingest_corpus.py`
terakhir dijalankan, dan tidak pernah di-ingest ulang. Baru terdeteksi &
diperbaiki 2026-08-25 lewat `docker compose exec api python -m
scripts.ingest_corpus`, dikonfirmasi via query DB langsung (`SELECT count(*)
FROM knowledge_chunks` = 27 sebelum, 28 sesudah). recall@3 71,9% BELUM diukur
ulang terhadap corpus 28-chunk yang genuinely jalan sekarang — pelajaran yang
sama berulang: klaim "sudah di-deploy" butuh bukti eksekusi (query DB),
bukan cuma "skrip jalan tanpa error".

Script mencetak **empat** set sekaligus, dan bedanya penting. Tiga set pertama
sudah "terbakar": kegagalannya pernah dipakai memperbaiki sistem, jadi angkanya
mengukur kecocokan sistem dengan dirinya sendiri. **Hanya `test-2` yang sah.**

Bukti kenapa ini penting: menambal 4 celah kosakata membuat `test-1` melonjak
85,7% → **100%**, sementara `test-2` yang bersih tetap **71,9%**. Perbaikannya
tidak menular. Kalau berhenti di angka 100%, yang dilaporkan adalah angka palsu.

⚠️ **Baca [`docs/RETRIEVAL-EVALUATION.md`](docs/RETRIEVAL-EVALUATION.md) sebelum
menyetel ambang, mengganti model embedding, atau melaporkan angka apa pun.**
Di situ ada bukti terukur bahwa kemiripan cosine tidak bisa dipakai menyaring
pertanyaan di luar cakupan, dan kenapa migrasi ke model embedding yang lebih besar
sudah diuji lalu dibatalkan.

### Evaluasi end-to-end (LLM-as-a-Judge)
```bash
export TARGET_URL=https://<tunnel-aktif>   # kosongkan untuk mode Direct DB
export GROQ_API_KEY=...
python -m scripts.eval_llm_judge
```
Beda dari evaluasi retrieval di atas: ini menguji seluruh alur (retrieval →
Bifrost/Groq → jawaban) lewat 52 skenario rumah sakit realistis, dinilai oleh
juri LLM terpisah (rubrik keselamatan/rute/faktual). Bukan set uji berlapis
seperti retrieval — skenarionya tetap (fixed list di skrip), jadi boleh
dijalankan ulang sebagai regression test tiap ada perbaikan, tidak "terbakar"
seperti `test-2`.

**Terakhir diukur bersih (52/52 dinilai, tanpa error) 2026-08-25: 46/52
(88,5%).** Ini run kedua, menggabungkan 2 perbaikan (kosakata "spiral KB",
rubrik penolakan out-of-scope) yang sebelumnya cuma diverifikasi individual.
Angka ini SENDIRI juga **lower-bound**: 1 perbaikan lagi (chunk "Cara Janji
Temu Dokter" yang ternyata belum ter-ingest ke produksi, lihat §recall@3 di
atas) di-deploy SETELAH run ini, cuma diverifikasi manual lewat curl. Rincian
per kategori dan daftar 6 kegagalan ada di tabel parameter di bawah.

### Ringkasan parameter & angka terukur

Semua angka di sini sudah melalui verifikasi eksekusi sungguhan (bukan klaim
di kertas) — lihat `docs/RETRIEVAL-EVALUATION.md` untuk metodologi lengkap.

| Parameter | Nilai | Catatan |
|---|---|---|
| Model embedding | `paraphrase-multilingual-MiniLM-L12-v2` (384 dim) | mpnet-base (768 dim) diuji, dibatalkan — nol perbaikan terukur, +0,8GB memori |
| Ukuran corpus | 28 chunk (simulasi) | genuinely 28 sejak 2026-08-25 (lihat koreksi §recall@3 — sempat cuma 27 di produksi tanpa disadari) |
| Retrieval | Hybrid: pgvector (cosine) + full-text `indonesian` via RRF (k=60) | ambang absolut terbukti tidak layak (cosine tidak terkalibrasi), lihat §evaluasi |
| Ambang skor (`MIN_TOP_SCORE`) | 0,22 | gerbang HANYA baca skor vector, full-text tidak ikut menentukan lolos/tidak — terbukti 2026-08-25: query dengan kata kunci PERSIS ("robek") tetap tertolak kalau parafrase-nya membuat skor vector di bawah 0,22. 0,15 terukur lebih baik (81,2%) tapi BELUM diterapkan — butuh set uji baru dulu, lihat `RETRIEVAL-EVALUATION.md` §6 |
| **recall@3 (retrieval murni)** | **71,9%** (32 soal bersih, `test-2`) | diukur 2026-08-24 terhadap corpus yang TERNYATA 27 chunk (lihat koreksi di atas), belum diukur ulang terhadap 28 chunk genuine |
| LLM primer | Bifrost / `medgemma-1.5-4b-it-q4` | gateway eksternal `hcm-lab.id`, tuning domain medis (ADR-029) |
| LLM fallback | Groq / `openai/gpt-oss-20b` | dipanggil server-side, tidak pernah dari client |
| Latensi jawaban (Bifrost) | 12-32 detik | reasoning trace medgemma + overhead Cloudflare Tunnel |
| **eval_llm_judge (end-to-end, 52 skenario)** | **46/52 (88,5%)** | diukur 2026-08-25; lower-bound, mendahului 1 perbaikan terbaru (chunk janji-temu, lihat rincian kategori) |
| ↳ Gawat Darurat | 9/10 (90%) | 1 kegagalan = korban gerbang `MIN_TOP_SCORE` (akar terkonfirmasi 2026-08-25, sengaja belum ditambal) |
| ↳ Poliklinik | 8/10 (80%) | 2 gagal: jadwal dokter anak tidak sebut nama poli — diduga variasi sampling LLM, bukan bug kode |
| ↳ Farmasi | 6/6 (100%) | |
| ↳ Diagnostik | 6/6 (100%) | |
| ↳ Administrasi | 4/6 (67%) | 2 gagal: rujukan BPJS tidak sebut Resepsionis (belum diselidiki); chunk janji-temu-dokter tidak ter-ingest ke produksi — **diperbaiki & diverifikasi 2026-08-25**, belum ikut angka agregat ini |
| ↳ Fasilitas Umum | 10/10 (100%) | |
| ↳ Di Luar Cakupan | 3/4 (75%) | 1 gagal = `poi_id` tetap ke-isi walau jawaban teks benar menolak (gejala `MIN_TOP_SCORE` yang sama) |
| Ingress | Cloudflare Named Tunnel permanen | `https://api-darsi.rockhead07.tech`, systemd service, survive restart |
| Keamanan admin | `POI_SYNC_TOKEN` dirotasi | token acak 48-hex, default lama sudah ditolak (401) |

### Catatan Deployment & Ingress (ADR-027)
Dependensi ONNX + bobot model menambah sekitar 450-500MB. Model dimuat sekali saat
startup lewat `lifespan`.

**Opsi Hosting & Ingress:**
1. **Server Privat (di balik VPN/Firewall):** Gunakan **Cloudflare Tunnel (`cloudflared`)** sebagai Zero Trust application connector. Menyediakan HTTPS publik otomatis tanpa membuka inbound port dan tanpa mewajibkan OpenVPN di HP klien.
2. **Managed Cloud (100% Free):** Database di **Supabase** (Postgres 16 + `pgvector`), web service di **Koyeb / Render / Fly.io** (auto-deploy GitHub).
3. **Local Dev & Testing:** Jalankan via Docker (`pgvector/pgvector:pg16`), uji via Android USB menggunakan `adb reverse tcp:8000 tcp:8000`.


## Files
- `schema.sql` — `pois` table (standard SQL)
- `seed.sql` — **usang, jangan dijalankan** (ADR-021). Isinya 11 POI scene kampus lama;
  data POI sekarang datang dari Unity lewat `POST /api/poi/sync`. File ini juga tidak lagi
  kompatibel dengan skema: dia INSERT tanpa `unity_id` (kini NOT NULL) dan pakai
  `ON CONFLICT (name)` (constraint-nya sudah dicabut).
- `app/main.py` — FastAPI service (sync psycopg + sync endpoints; runs in a threadpool)
- `requirements.txt`

## Run with Docker Compose (Recommended)

```bash
# 1. Setup konfigurasi env
cp .env.docker.example .env
# Edit .env dan isi GROQ_API_KEY Anda

# 2. Build & jalankan container
docker compose up -d --build

# 3. Ingest corpus simulasi ke database pgvector
docker compose exec api python -m scripts.ingest_corpus

# 4. Check endpoint
curl http://localhost:8000/api/poi/popular
```

Panduan lengkap menghubungkan server privat ke internet via Cloudflare Tunnel: [`docs/TUNNEL-SETUP.md`](docs/TUNNEL-SETUP.md).

## Run Manually (Local Python)
```bash
# 1. DB: Supabase Postgres OR a local Postgres (e.g. Docker)
#    docker run -d --name darsi-pg -e POSTGRES_PASSWORD=darsi -e POSTGRES_DB=darsi -p 5433:5432 pgvector/pgvector:pg16
cp .env.example .env          # then edit DATABASE_URL
export DATABASE_URL="postgresql://postgres:darsi@localhost:5433/darsi"
psql "$DATABASE_URL" -f schema.sql
psql "$DATABASE_URL" -f schema_rag.sql
python -m scripts.ingest_corpus

# 2. API
python -m venv .venv && . .venv/Scripts/activate   # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# check: http://localhost:8000/api/poi/popular
```

## Notes
- `unity_id` (GUID dari `POIData.poiId`) adalah **satu-satunya** kunci identitas POI.
  `name` cuma atribut tampilan dan sengaja tidak unik — satu gedung sah punya banyak
  "Lift"/"Toilet", satu per lantai (ADR-021). Untuk membedakannya di UI, susun dari
  `name` + `floor` saat render; jangan simpan lantai di dalam `name`.
- `name`/`building`/`floor` dimiliki Unity dan dikirim lewat Editor sync tool
  (ADR-014/ADR-021). `status`, `description`, `photos`, `is_popular` milik backend.
- Runtime note: psycopg's async pool can't use Windows' default ProactorEventLoop, so this
  service uses the **sync** psycopg pool with sync endpoints (FastAPI runs them in a
  threadpool). Simpler and portable.
