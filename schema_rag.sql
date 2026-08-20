-- DARSI backend — skema RAG Assistant (spec 2026-08-20, section 6)
-- Terpisah dari schema.sql supaya skema POI yang sudah jalan tidak ikut terganggu.
-- pgvector adalah ekstensi PostgreSQL standar, bukan fitur proprietary Supabase,
-- jadi portabilitas ADR-001/ADR-014 tetap terjaga: migrasi = pg_dump/pg_restore
-- dengan syarat host tujuan mengaktifkan ekstensi ini.
CREATE EXTENSION IF NOT EXISTS vector;

-- Prosa: SOP, info layanan, FAQ, deskripsi ruangan. Inilah yang di-embed.
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    content       text NOT NULL,
    -- 384 = paraphrase-multilingual-MiniLM-L12-v2. Mengganti model = harus
    -- embed ulang SELURUH tabel; vektor dari dua model berbeda tidak sebanding.
    embedding     vector(384) NOT NULL,
    doc_type      text NOT NULL CHECK (doc_type IN ('sop', 'layanan', 'faq', 'poi_detail')),
    title         text NOT NULL,
    -- Sumber sah poi_id di response. ON DELETE SET NULL: kalau POI-nya hilang,
    -- isi pengetahuannya masih berguna, cuma kehilangan target navigasinya.
    poi_unity_id  text REFERENCES pois(unity_id) ON DELETE SET NULL,
    building      text,
    floor         text,
    -- Penanda siklus data (spec section 7). Ada di KOLOM, bukan cuma catatan di
    -- dokumen, supaya data simulasi tidak mungkin tercampur data asli diam-diam.
    is_simulated  boolean NOT NULL DEFAULT true,
    source_ref    text NOT NULL DEFAULT '',
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    -- Ingest idempoten: jalankan ulang script tidak menggandakan baris.
    UNIQUE (title, source_ref)
);

-- Terstruktur: SENGAJA tidak di-embed. "dr. Fulan praktek jam berapa" itu lookup,
-- bukan pencarian makna. Vector search di data tabular mengembalikan baris yang
-- mirip bentuknya, bukan yang benar, dan jam praktek salah di RS bukan hal kecil.
CREATE TABLE IF NOT EXISTS doctor_schedules (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    doctor_name   text NOT NULL,
    specialty     text NOT NULL,
    poi_unity_id  text REFERENCES pois(unity_id) ON DELETE SET NULL,
    day_of_week   smallint NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),  -- 1 = Senin
    start_time    time NOT NULL,
    end_time      time NOT NULL,
    is_simulated  boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (doctor_name, day_of_week, start_time)
);

CREATE INDEX IF NOT EXISTS idx_chunks_embedding
    ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_type ON knowledge_chunks (doc_type);
CREATE INDEX IF NOT EXISTS idx_chunks_floor    ON knowledge_chunks (floor);
CREATE INDEX IF NOT EXISTS idx_sched_specialty ON doctor_schedules (specialty);

DROP TRIGGER IF EXISTS trg_chunks_updated_at ON knowledge_chunks;
CREATE TRIGGER trg_chunks_updated_at
    BEFORE UPDATE ON knowledge_chunks
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_sched_updated_at ON doctor_schedules;
CREATE TRIGGER trg_sched_updated_at
    BEFORE UPDATE ON doctor_schedules
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── Lexical search (ditambahkan setelah pengukuran, lihat commit hybrid RRF) ──
-- Bukti yang memicunya: kata "igd" ada PERSIS di pertanyaan dan di judul chunk,
-- tapi model embedding gagal memberi bobot pada nama entitas. Itu justru pekerjaan
-- sepele bagi pencarian kata kunci. Vector saja tidak cukup.
--
-- Konfigurasi 'indonesian' bawaan PostgreSQL (stemming + stop word Bahasa
-- Indonesia). Judul diberi bobot 'A', isi 'B', supaya nama entitas di judul
-- ("Alur Pasien IGD") menang atas penyebutan sambil lalu di badan teks.
ALTER TABLE knowledge_chunks
    ADD COLUMN IF NOT EXISTS tsv tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('indonesian', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('indonesian', coalesce(content, '')), 'B')
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON knowledge_chunks USING gin (tsv);
