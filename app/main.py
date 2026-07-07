"""DARSI backend — POI read API (T3.4.3).

Portable by design (ADR-001 / ADR-014): talks to plain PostgreSQL via a
DATABASE_URL, using psycopg — NOT the Supabase SDK. Works identically against
Supabase's Postgres or a self-hosted Postgres, so migration is just a connection
string change.

Sync psycopg + sync endpoints on purpose: FastAPI runs sync handlers in a
threadpool, which is plenty for a low-traffic read-only API and sidesteps the
Windows async-event-loop gotcha (psycopg async needs SelectorEventLoop, uvicorn
defaults to ProactorEventLoop on Windows). ponytail: no async where sync is fine.

Endpoints:
  GET  /api/poi/popular              (read-only, no auth)
  GET  /api/poi/search?q=&category=  (read-only, no auth)
  GET  /api/poi/categories           (read-only, no auth)
  POST /api/poi/sync                 (admin token, T3.4-L2 — Unity Editor push)

No response ever includes a distance/meter field — deliberate (ADR-007).
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from pydantic import BaseModel

DATABASE_URL = os.environ.get("DATABASE_URL", "")
POI_SYNC_TOKEN = os.environ.get("POI_SYNC_TOKEN", "")

# Fields exposed to the WebView. NOTE: no "distance" — ADR-007.
# unity_id (stable GUID from Unity POIData) is aliased to "id" — the WebView passes it
# back as launchAR poiId so navigation survives a POI display-name rename. NULL for any
# legacy row not yet synced; the WebView falls back to name in that case.
POI_COLUMNS = "unity_id AS id, name, category, building, floor, status, is_popular, description, photos"

# Kategori POI kanonik — SATU sumber kebenaran. Sync (Unity push) ditolak kalau ada
# kategori di luar daftar ini, jadi typo ketahuan saat klik Sync (fail-loud di boundary),
# bukan diam-diam jadi ikon default di WebView. HARUS sama persis (case-sensitive) dengan
# key categoryIcon() di WebView (app/lib/api.ts) — kalau nambah kategori, update dua-duanya.
POI_CATEGORIES = frozenset({
    # Klinis / instalasi medis
    "IGD", "Poliklinik", "Farmasi", "Laboratorium", "Radiologi",
    "Rawat Inap", "Kamar Operasi", "ICU", "Ruang Bersalin", "Fisioterapi",
    # Administrasi / layanan
    "Pendaftaran", "Kasir", "Informasi", "BPJS", "Rekam Medis",
    # Fasilitas umum
    "Musholla", "Toilet", "Kantin", "ATM", "Parkir", "Ruang Tunggu",
    # Sirkulasi / wayfinding
    "Lift", "Tangga", "Pintu Masuk",
    # Kategori demo kampus (lama) — masih dipakai seed 11 POI
    "Umum", "Administrasi",
})


@asynccontextmanager
async def lifespan(app: FastAPI):
    # sync ConnectionPool managed from an async lifespan (open/close are plain sync calls)
    # check=check_connection: verify a pooled connection is alive before handing it
    # out. Without this, a connection Railway's proxy silently dropped while idle
    # (e.g. no requests for a while) gets reused and fails with
    # "SSL error: unexpected eof while reading" instead of being replaced.
    app.state.pool = ConnectionPool(
        DATABASE_URL,
        open=False,
        kwargs={"row_factory": dict_row},
        check=ConnectionPool.check_connection,
    )
    app.state.pool.open()
    try:
        yield
    finally:
        app.state.pool.close()


app = FastAPI(title="DARSI POI API", lifespan=lifespan)

# WebView is served from a different origin (Next.js), so allow it to fetch.
# ponytail: wide-open CORS is fine for a read-only public POI API; tighten to the
# real WebView origin when it is known.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _fetch(sql: str, params: tuple = ()):
    with app.state.pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


@app.get("/api/poi/popular")
def popular():
    """POIs flagged is_popular, for the Home 'Destinasi Populer' row."""
    return _fetch(f"SELECT {POI_COLUMNS} FROM pois WHERE is_popular = true ORDER BY name")


@app.get("/api/poi/search")
def search(
    q: str = Query("", description="free-text query on name/synonyms"),
    category: str = Query("", description="exact category filter; empty = all"),
):
    """Cari Lokasi results. Empty q + empty category returns everything."""
    clauses, params = [], []
    if q:
        # match on name OR any synonym, case-insensitive
        clauses.append("(name ILIKE %s OR EXISTS (SELECT 1 FROM unnest(synonyms) s WHERE s ILIKE %s))")
        like = f"%{q}%"
        params += [like, like]
    if category and category != "Semua":
        clauses.append("category = %s")
        params.append(category)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return _fetch(f"SELECT {POI_COLUMNS} FROM pois {where} ORDER BY name", tuple(params))


@app.get("/api/poi/categories")
def categories():
    """Distinct categories for the Cari Lokasi filter chips."""
    rows = _fetch("SELECT DISTINCT category FROM pois ORDER BY category")
    return [r["category"] for r in rows]


class PoiSyncEntry(BaseModel):
    id: str  # Unity POIData.poiId (GUID) — stable key, never the display name
    name: str
    category: str
    building: str = ""
    floor: str = ""
    synonyms: list[str] = []


class PoiSyncPayload(BaseModel):
    pois: list[PoiSyncEntry]


@app.post("/api/poi/sync")
def sync_pois(payload: PoiSyncPayload, x_admin_token: str = Header(default="")):
    """Unity Editor push (T3.4-L2): upsert static fields only, keyed by unity_id.

    Never touches `status` — that stays backend-owned (ADR-014). First sync of a
    POI created before the sync tool existed adopts the pre-seeded row by matching
    on `name`, then backfills unity_id so future renames still resolve correctly.
    """
    if not POI_SYNC_TOKEN or x_admin_token != POI_SYNC_TOKEN:
        raise HTTPException(status_code=401, detail="invalid or missing admin token")

    # Fail-loud di boundary: tolak seluruh sync kalau ada kategori tak dikenal, sebutkan
    # POI mana biar bisa langsung dibetulkan di Unity. All-or-nothing sengaja — jangan
    # sebagian ke-upsert lalu sebagian gagal (bikin state DB setengah jadi).
    unknown = sorted({poi.category for poi in payload.pois} - POI_CATEGORIES)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"kategori tidak dikenal: {', '.join(unknown)}. "
                   f"Kategori valid: {', '.join(sorted(POI_CATEGORIES))}",
        )

    created = updated = 0
    with app.state.pool.connection() as conn:
        with conn.cursor() as cur:
            for poi in payload.pois:
                cur.execute("SELECT id FROM pois WHERE unity_id = %s", (poi.id,))
                row = cur.fetchone()
                if row is None:
                    cur.execute("SELECT id FROM pois WHERE name = %s", (poi.name,))
                    row = cur.fetchone()

                if row is None:
                    cur.execute(
                        """INSERT INTO pois (unity_id, name, category, building, floor, synonyms)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (poi.id, poi.name, poi.category, poi.building, poi.floor, poi.synonyms),
                    )
                    created += 1
                else:
                    cur.execute(
                        """UPDATE pois SET unity_id = %s, name = %s, category = %s,
                                            building = %s, floor = %s, synonyms = %s
                           WHERE id = %s""",
                        (poi.id, poi.name, poi.category, poi.building, poi.floor, poi.synonyms, row["id"]),
                    )
                    updated += 1

    return {"synced": created + updated, "created": created, "updated": updated}


@app.get("/health")
def health():
    return {"ok": True}
