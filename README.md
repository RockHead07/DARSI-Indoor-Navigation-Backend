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
**Angka FINAL (2026-08-26): recall@3 soal sah = 95,8%** (23/24) pada `test-4`,
set uji disegel yang tidak pernah dipakai memperbaiki apa pun. Diukur terhadap
corpus 28-chunk yang genuine (lihat koreksi di bawah), setelah `MIN_TOP_SCORE`
diturunkan ke 0,15 (ADR-036).

⚠️ **Koreksi metodologi 2026-08-26:** angka lama (71,9%/78,6%, diukur
2026-08-24) menggabungkan recall soal sah dengan penolakan soal sampah jadi
satu persentase. Sejak `MIN_TOP_SCORE` sengaja dilonggarkan dan penyaringan
sampah diserahkan ke LLM (bukan lagi ke retrieval, lihat ADR-036), angka
gabungan itu jadi menyesatkan -- `test-4` sempat terbaca 75,0% padahal recall
soal sahnya sebenarnya 95,8%, cuma tertutup 7 soal sampah yang "gagal" (tidak
kosong) padahal itu memang perilaku yang diharapkan sekarang. `eval_retrieval.py`
sudah diperbaiki untuk melaporkan keduanya terpisah.

⚠️ **Koreksi 2026-08-25 (masih berlaku):** angka lama di atas SEBENARNYA
diukur terhadap corpus **27 chunk**, bukan 28 seperti sempat tertulis di sini. Chunk ke-28 ("Cara
Membuat Janji Temu Dokter", ditulis di commit `803f2fa`) ternyata **tidak
pernah ter-ingest ke produksi** — kemungkinan diedit setelah `ingest_corpus.py`
terakhir dijalankan, dan tidak pernah di-ingest ulang. Baru terdeteksi &
diperbaiki 2026-08-25 lewat `docker compose exec api python -m
scripts.ingest_corpus`, dikonfirmasi via query DB langsung (`SELECT count(*)
FROM knowledge_chunks` = 27 sebelum, 28 sesudah) — pelajaran yang sama
berulang: klaim "sudah di-deploy" butuh bukti eksekusi (query DB), bukan cuma
"skrip jalan tanpa error".

Script mencetak **enam** set sekaligus (`test-3`/`test-4` ditambahkan
2026-08-26, lihat `docs/RETRIEVAL-EVALUATION.md` §6), dan bedanya penting.
Lima set pertama sudah "terbakar" untuk berbagai keperluan (lihat catatan yang
dicetak skrip untuk masing-masing). **Hanya `test-4` yang belum pernah dipakai
memperbaiki apa pun** — itu yang layak dilaporkan.

Bukti kenapa "set terbakar" penting: menambal 4 celah kosakata membuat
`test-1` melonjak 85,7% → **100%**, sementara `test-2` yang saat itu masih
bersih tetap **71,9%**. Perbaikannya tidak menular. Kalau berhenti di angka
100%, yang dilaporkan adalah angka palsu.

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

**Terakhir diukur bersih (52/52 dinilai, tanpa error) 2026-08-26: 51/52
(98,1%).** Menggabungkan SEMUA perbaikan konten yang pernah ditemukan lewat
eval ini (kosakata KB, rubrik out-of-scope, chunk janji-temu-dokter, WAYFINDING
administrasi/BPJS, konsistensi Kasir→Resepsionis). Response API sejak run ini
juga membawa field `provider` (`bifrost`/`groq`) -- setiap baris hasil eval
mencatatnya, jadi kegagalan intermiten bisa dikorelasikan dengan fallback,
bukan diduga.

**Satu-satunya kegagalan run itu (luka-robek/berdarah) SUDAH DIPERBAIKI
setelahnya** lewat ADR-036 (`MIN_TOP_SCORE` 0,22→0,15) — diverifikasi via curl
DAN via 3 percobaan run 52-skenario susulan (2026-08-26), `#06` PASS di
**3 dari 3** dan Di Luar Cakupan PASS **4/4 di ketiganya**. Dua fix inti
(ambang + penanda `[TOLAK]`) terbukti kokoh, bukan kebetulan sekali jalan.

⚠️ **Belum ada satu pun dari 3 run susulan itu yang bersih 52/52** — tiap run
kena 6-8 kegagalan infrastruktur (`503 Service Unavailable` dari endpoint kita
sendiri, sekali juga `[WinError 10054]` jaringan lokal), bukan kegagalan
jawaban. Lihat entri `MIN_TOP_SCORE`/Bifrost di bawah untuk detail dan
statusnya sebagai utang baru. Dua kegagalan KONTEN nyata yang tersisa (bukan
infra): jadwal dokter kadang tidak sebut nama poli (`#12`, sudah lama diduga
variasi sampling), dan "Loket obat racikan di sebelah mana" (`#25`, BARU --
jawabannya jujur bilang tidak tersedia detailnya, yang sebenarnya benar karena
corpus memang tidak merinci loket racikan terpisah; prioritas rendah, sama
kelasnya dengan `#12`).

### Ringkasan parameter & angka terukur

Semua angka di sini sudah melalui verifikasi eksekusi sungguhan (bukan klaim
di kertas) — lihat `docs/RETRIEVAL-EVALUATION.md` untuk metodologi lengkap.

| Parameter | Nilai | Catatan |
|---|---|---|
| Model embedding | `paraphrase-multilingual-MiniLM-L12-v2` (384 dim) | mpnet-base (768 dim) diuji, dibatalkan — nol perbaikan terukur, +0,8GB memori |
| Ukuran corpus | 28 chunk (simulasi) | genuinely 28 sejak 2026-08-25 (lihat koreksi §recall@3 — sempat cuma 27 di produksi tanpa disadari) |
| Retrieval | Hybrid: pgvector (cosine) + full-text `indonesian` via RRF (k=60) | ambang absolut terbukti tidak layak (cosine tidak terkalibrasi), lihat §evaluasi |
| Ambang skor (`MIN_TOP_SCORE`) | **0,15** (sejak 2026-08-26, ADR-036) | dulu 0,22 — gerbang HANYA baca skor vector, full-text tidak ikut menentukan lolos/tidak, jadi kata kunci PERSIS ("robek") pun tidak menolong. Diputuskan lewat asimetri biaya (sampah lolos → LLM menolak dgn benar; sah diblokir → penolakan buta ke kasus luka berdarah), bukan cuma kemenangan angka. Detail lengkap: `RETRIEVAL-EVALUATION.md` §6 |
| **recall@3 soal sah** | **95,8%** (23/24, `test-4`) | diukur 2026-08-26, set disegel, belum pernah dipakai memperbaiki apa pun. Metodologi diperbaiki: TIDAK lagi digabung dengan penolakan soal sampah (lihat `RETRIEVAL-EVALUATION.md` §6) |
| LLM primer | Bifrost / `medgemma-1.5-4b-it-q4` | gateway eksternal `hcm-lab.id`, tuning domain medis (ADR-029) |
| LLM fallback | Groq / `openai/gpt-oss-20b` | dipanggil server-side, tidak pernah dari client |
| Latensi jawaban (Bifrost) | 12-32 detik | reasoning trace medgemma + overhead Cloudflare Tunnel |
| **eval_llm_judge (end-to-end, 52 skenario)** | **51/52 (98,1%)** | diukur 2026-08-26; FINAL, mencakup semua fix yang pernah ditemukan lewat eval ini |
| ↳ Gawat Darurat | 9/10 (90%) | 1 kegagalan = korban gerbang `MIN_TOP_SCORE` lama (0,22) — **sudah diperbaiki** oleh ADR-036, belum ikut angka agregat run ini |
| ↳ Poliklinik | 10/10 (100%) | |
| ↳ Farmasi | 6/6 (100%) | |
| ↳ Diagnostik | 6/6 (100%) | |
| ↳ Administrasi | 6/6 (100%) | chunk janji-temu-dokter (tidak ter-ingest) + WAYFINDING administrasi/BPJS + konsistensi Kasir→Resepsionis, semua diperbaiki 2026-08-25/26 |
| ↳ Fasilitas Umum | 10/10 (100%) | |
| ↳ Di Luar Cakupan | 4/4 (100%) | lolos di run ini sebelum ambang diturunkan. Diverifikasi ULANG setelah ADR-036 (8/8 pertanyaan sampah tetap ditolak LLM dengan benar) — argumen asimetri gerbang terbukti, bukan kebetulan |
| `poi_id` saat menolak | **Diperbaiki 2026-08-26** | dulu bocor (mis. "prakiraan cuaca" → `poi_name: IGD`) — makin sering muncul setelah gerbang dilonggarkan. Sekarang LLM menandai penolakan (`[TOLAK]`, dibuang dari teks sebelum sampai ke pengguna), `poi_id`/`poi_name` dipaksa `null` kalau tertandai. Solusi "buang poi kalau namanya tak disebut di teks" DIUJI DAN GUGUR: 4 dari 11 POI resmi tidak pernah muncul apa adanya di jawaban (`Radiology` vs "Radiologi", dll) |
| ⚠️ **Stabilitas Bifrost/jaringan** | **~10-15% gagal di bawah beban** (UTANG BARU 2026-08-26) | Terukur di 3 percobaan eval 52-skenario berturut-turut, masing-masing kena 6-8 kegagalan `503`/koneksi (endpoint kita balas 503 HANYA kalau Bifrost DAN Groq fallback DUA-DUANYA gagal untuk request yang sama, lihat `router.py`). Diagnosis lewat `docker compose logs api` BUNTU -- container tidak mencetak log request/exception ke stdout sama sekali. Belum diselidiki lebih jauh (butuh nambah logging, di luar cakupan sesi ini). Bukan bug RAG, tapi relevan untuk kesiapan lapangan sungguhan. |
| Ingress | Cloudflare Named Tunnel permanen | `https://api-darsi.rockhead07.tech`, systemd service, survive restart (port host 8050, ADR-027 Amandemen 027-B) |
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
