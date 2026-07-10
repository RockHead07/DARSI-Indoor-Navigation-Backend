-- DARSI backend — POI schema (T3.4.1)
-- Portable standard PostgreSQL — no Supabase-proprietary features, so migrating
-- to a self-hosted Postgres later is just pg_dump/pg_restore (ADR-001 / ADR-014).

CREATE TABLE IF NOT EXISTS pois (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- Stable key pushed from Unity POIData.poiId (GUID, T3.4-L1/L2). NULL for rows
    -- that predate the sync tool; first sync adopts them by matching on `name`
    -- (see POST /api/poi/sync in app/main.py) and backfills this column.
    unity_id    text UNIQUE,
    -- name doubles as the poiId sent to Unity for now (exact-match resolution,
    -- see ROADMAP T1.4). Unique so it can act as the stable key until POIData
    -- gains a real id field (ADR-014 phasing / T3.4-L1).
    name        text NOT NULL UNIQUE,
    category    text NOT NULL,
    building    text,                 -- owned by Unity/POIData (ADR-014)
    floor       text,                 -- owned by Unity/POIData (ADR-014)
    status      text NOT NULL DEFAULT 'Buka'
                    CHECK (status IN ('Buka', 'Antre', 'Penuh')),  -- owned by backend (ADR-014)
    is_popular  boolean NOT NULL DEFAULT false,
    synonyms    text[] NOT NULL DEFAULT '{}',   -- mirrors POIData.sinonim, aids search
    -- Display-only detail content for the WebView detail sheet — owned by backend
    -- (ADR-014), never consumed by Unity.
    description text NOT NULL DEFAULT '',
    photos      text[] NOT NULL DEFAULT '{}',   -- image URLs; empty = UI renders placeholder
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Search helpers
CREATE INDEX IF NOT EXISTS idx_pois_category ON pois (category);
CREATE INDEX IF NOT EXISTS idx_pois_name_lower ON pois (lower(name));

-- Keep updated_at fresh on writes (relevant once the Unity sync tool upserts — T3.4-L2)
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_pois_updated_at ON pois;
CREATE TRIGGER trg_pois_updated_at
    BEFORE UPDATE ON pois
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- NOTE: no `distance`/`meter` column anywhere — that is a deliberate product
-- decision (ADR-007), not an omission. Distance is computed inside Unity after
-- localize, never served by the API.

-- Presence opt-out only (ADR-013 "tampil offline"). NOT the friend graph — that
-- (friends/requests tables) waits on stable identity from MyRSIy (ROADMAP T0.8),
-- per the Sprint 1 decision to cancel "Backend Fase 2" as unrealistic this sprint.
-- This table is scoped to just the one toggle already live in the WebView UI.
CREATE TABLE IF NOT EXISTS presence (
    user_id     text PRIMARY KEY,  -- window.__DARSI_USER__.userId (ADR-017), client-trusted for now
    invisible   boolean NOT NULL DEFAULT false,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
