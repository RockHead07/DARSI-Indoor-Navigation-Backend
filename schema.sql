-- DARSI backend — POI schema (T3.4.1)
-- Portable standard PostgreSQL — no Supabase-proprietary features, so migrating
-- to a self-hosted Postgres later is just pg_dump/pg_restore (ADR-001 / ADR-014).

CREATE TABLE IF NOT EXISTS pois (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- SATU-SATUNYA kunci identitas POI: POIData.poiId (GUID) dari Unity (T3.4-L1/L2).
    unity_id    text NOT NULL UNIQUE,
    -- Atribut TAMPILAN, bukan kunci — sengaja tidak unik (ADR-021). Satu gedung sah
    -- punya banyak "Lift"/"Toilet"/"Tangga", satu per lantai. Untuk membedakannya di
    -- UI, susun dari name + floor saat render — JANGAN jejalkan lantai ke dalam name.
    name        text NOT NULL,
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

-- Migrasi untuk DB yang tabelnya sudah ada: CREATE TABLE IF NOT EXISTS di atas
-- diam-diam skip tabel lama, jadi kolom yang ditambah belakangan TIDAK ikut
-- (unity_id sempat hilang di DB lokal karena ini). Baris ALTER idempoten di bawah
-- memastikan "jalankan ulang schema.sql" selalu = skema terkini, di DB manapun.
ALTER TABLE pois ADD COLUMN IF NOT EXISTS unity_id text UNIQUE;

-- ADR-021 (2026-07-19). Urutan tiga baris di bawah penting: buang constraint dulu,
-- baru bersihkan baris legacy, baru kunci NOT NULL.
--
-- 1. `name` UNIQUE adalah warisan masa sebelum POIData punya id sendiri. Data RSI asli
--    mematahkannya (dua "Lift", satu per lantai) — gejalanya 500 UniqueViolation saat sync.
ALTER TABLE pois DROP CONSTRAINT IF EXISTS pois_name_key;

-- 2. Buang sisa scene kampus (Perpustakaan, Lab Teori 202, Ruang Dosen, BAAK, ...).
--    unity_id hanya NULL kalau baris tidak pernah lewat POST /api/poi/sync, dan satu-
--    satunya jalur non-sync adalah seed.sql yang isinya kampus semua. Baris kampus yang
--    sudah diadopsi sync sebelumnya sudah punya unity_id, jadi TIDAK ikut terhapus.
--    RETURNING supaya yang hilang kelihatan, bukan menghapus dalam gelap.
DELETE FROM pois WHERE unity_id IS NULL RETURNING name;

-- 3. unity_id kini satu-satunya kunci sah — ini yang menggantikan perlindungan duplikat
--    yang tadinya (keliru) dipegang name UNIQUE.
ALTER TABLE pois ALTER COLUMN unity_id SET NOT NULL;

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
