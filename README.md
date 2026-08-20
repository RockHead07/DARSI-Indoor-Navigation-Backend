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

Env var tambahan: `GROQ_API_KEY` (dipanggil dari server, tidak pernah ikut ke APK).

### Evaluasi retrieval
```bash
python -m scripts.eval_retrieval
```
Mencetak recall@3 terhadap `data/eval_retrieval.json`. Angkanya diukur di atas
corpus simulasi, jadi mengukur mekanisme retrieval, bukan kesiapan lapangan.

### Catatan deployment
Dependensi ONNX + bobot model menambah sekitar 450-500MB. Model dimuat sekali saat
startup lewat `lifespan`. Kalau pemakaian memori Railway melewati batas paket, itu
keputusan biaya yang perlu dibicarakan, bukan diakali dengan menurunkan kualitas model.


## Files
- `schema.sql` — `pois` table (standard SQL)
- `seed.sql` — **usang, jangan dijalankan** (ADR-021). Isinya 11 POI scene kampus lama;
  data POI sekarang datang dari Unity lewat `POST /api/poi/sync`. File ini juga tidak lagi
  kompatibel dengan skema: dia INSERT tanpa `unity_id` (kini NOT NULL) dan pakai
  `ON CONFLICT (name)` (constraint-nya sudah dicabut).
- `app/main.py` — FastAPI service (sync psycopg + sync endpoints; runs in a threadpool)
- `requirements.txt`

## Run (dev)
```bash
# 1. DB: Supabase Postgres OR a local Postgres (e.g. Docker)
#    docker run -d --name darsi-pg -e POSTGRES_PASSWORD=darsi -e POSTGRES_DB=darsi -p 5433:5432 postgres:16
cp .env.example .env          # then edit DATABASE_URL
export DATABASE_URL="postgresql://postgres:darsi@localhost:5433/darsi"
psql "$DATABASE_URL" -f schema.sql
# TIDAK ada seed — isi POI dari Unity: menu DARSI > Sync POIs to Backend

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
