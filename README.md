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
