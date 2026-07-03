"""DARSI backend — POI read API (T3.4.3).

Portable by design (ADR-001 / ADR-014): talks to plain PostgreSQL via a
DATABASE_URL, using psycopg — NOT the Supabase SDK. Works identically against
Supabase's Postgres or a self-hosted Postgres, so migration is just a connection
string change.

Sync psycopg + sync endpoints on purpose: FastAPI runs sync handlers in a
threadpool, which is plenty for a low-traffic read-only API and sidesteps the
Windows async-event-loop gotcha (psycopg async needs SelectorEventLoop, uvicorn
defaults to ProactorEventLoop on Windows). ponytail: no async where sync is fine.

Endpoints (all read-only, no auth):
  GET /api/poi/popular
  GET /api/poi/search?q=&category=
  GET /api/poi/categories

No response ever includes a distance/meter field — deliberate (ADR-007).
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Fields exposed to the WebView. NOTE: no "distance" — ADR-007.
POI_COLUMNS = "name, category, building, floor, status, is_popular"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # sync ConnectionPool managed from an async lifespan (open/close are plain sync calls)
    app.state.pool = ConnectionPool(DATABASE_URL, open=False, kwargs={"row_factory": dict_row})
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


@app.get("/health")
def health():
    return {"ok": True}
