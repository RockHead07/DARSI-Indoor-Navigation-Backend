-- DARSI backend — POI schema (T3.4.1)
-- Portable standard PostgreSQL — no Supabase-proprietary features, so migrating
-- to a self-hosted Postgres later is just pg_dump/pg_restore (ADR-001 / ADR-014).

CREATE TABLE IF NOT EXISTS pois (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
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
