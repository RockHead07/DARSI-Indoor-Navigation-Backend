# RAG Assistant Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bangun endpoint `POST /api/assistant/query` yang menjawab pertanyaan bahasa Indonesia seputar layanan RS memakai retrieval hybrid (pgvector untuk prosa, SQL untuk jadwal dokter) lalu Groq untuk menyusun jawabannya.

**Architecture:** Modul baru `app/assistant/` di service FastAPI yang sudah ada. Embedding dihitung lokal lewat ONNX (`fastembed`), model dimuat sekali saat startup. Retrieval dipecah dua jalur (vector untuk `knowledge_chunks`, SQL biasa untuk `doctor_schedules`), hasilnya digabung jadi satu konteks, baru dikirim ke Groq. Endpoint yang sudah ada tidak disentuh.

**Tech Stack:** Python 3.14, FastAPI, psycopg 3 (sync pool), PostgreSQL + pgvector 0.8.2, fastembed (ONNX), Groq API, pytest.

**Spec:** `docs/superpowers/specs/2026-08-20-rag-assistant-backend-design.md`

## Global Constraints

Nilai-nilai ini disalin persis dari spec. Berlaku untuk SEMUA task.

- **Model embedding:** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- **Dimensi vektor:** `384` (kalau ini berubah, seluruh tabel harus di-embed ulang)
- **Ekstensi DB:** `vector` v0.8.2, index **HNSW** `vector_cosine_ops`
- **Model Groq:** `openai/gpt-oss-20b` (sama dengan yang dipakai `OllamaConnector.cs`; `llama-3.1-8b-instant` sudah dihentikan Groq untuk free/dev tier per 2026-08-16)
- **`poi_id` TIDAK PERNAH dihasilkan LLM.** Selalu diturunkan dari kolom `poi_unity_id` milik chunk hasil retrieval. Melanggar ini = task ditolak.
- **Jadwal dokter TIDAK di-embed.** Selalu lewat query SQL.
- **`current_floor`/`building` hanya MEM-BIAS peringkat, TIDAK PERNAH mem-filter keras.** Info di lantai lain harus tetap bisa ditemukan.
- **Semua baris corpus awal `is_simulated = true`.** Response wajib membawa `contains_simulated_data`.
- **Nama dokter memakai pola "Fulan/Fulanah"** supaya jelas karangan. Dilarang menyerupai nama staf asli RS Islam A. Yani.
- **Gagal berisik di batas sistem.** Env var kosong atau model gagal dimuat = service gagal start dengan pesan jelas, bukan diam-diam jalan tanpa kemampuan retrieval.
- **Tidak menyentuh** `/api/poi/*`, `/api/presence/*`, atau `schema.sql` yang sudah ada.
- **Di luar lingkup:** avatar VRM, TTS/`audio_url`, `gesture`, `expression`, keputusan UI.

## Keputusan Penafsiran

Spec §8.2 bisa dibaca dua cara. **Yang dipakai plan ini:** `poi_id` diambil **hanya dari chunk peringkat 1**. Kalau chunk peringkat 1 tidak punya `poi_unity_id`, hasilnya `null`, walaupun chunk peringkat 2 punya.

Alasan: `poi_id` bermakna "inilah lokasi yang dibicarakan jawaban ini", dan itu jadi dasar tombol "mulai rute". Menyisir ke bawah bisa memasang target navigasi yang cuma disinggung sekilas, dan itu lebih membingungkan daripada tidak ada tombol sama sekali. Mudah dilonggarkan nanti kalau data evaluasi menunjukkan sebaliknya.

## Struktur Berkas

| Berkas | Tanggung jawab |
|---|---|
| `app/assistant/__init__.py` | penanda paket, kosong |
| `app/assistant/models.py` | bentuk request/response (pydantic) + `RetrievedChunk` |
| `app/assistant/embedding.py` | muat model ONNX sekali, hitung embedding |
| `app/assistant/retrieval.py` | vector search, lookup jadwal, penggabungan + bias lantai |
| `app/assistant/generation.py` | susun prompt, panggil Groq, penjaga "tanpa konteks" |
| `app/assistant/router.py` | endpoint `POST /api/assistant/query` |
| `app/main.py` | **dimodifikasi**: muat model di `lifespan`, daftarkan router |
| `schema_rag.sql` | DDL dua tabel + ekstensi + index (terpisah dari `schema.sql`) |
| `data/corpus_simulasi.py` | isi corpus simulasi sebagai data Python |
| `data/eval_retrieval.json` | 18 pasangan pertanyaan dan chunk yang seharusnya terambil |
| `scripts/ingest_corpus.py` | embed corpus lalu masukkan ke DB, idempoten |
| `scripts/eval_retrieval.py` | jalankan set evaluasi, cetak recall@3 |
| `tests/` | pytest |

---

### Task 1: Fondasi test, bentuk data, dan aturan `poi_id`

Task ini murni logika, tanpa DB dan tanpa jaringan, jadi bisa dites penuh dan cepat.

**Files:**
- Create: `app/assistant/__init__.py`
- Create: `app/assistant/models.py`
- Create: `tests/__init__.py`
- Create: `tests/test_models.py`
- Create: `pytest.ini`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `AssistantQueryRequest`, `AssistantQueryResponse`, `Source`, `RetrievedChunk`, `ScheduleRow`, `derive_poi(chunks) -> tuple[str | None, str | None]`

- [ ] **Step 1: Tambahkan pytest ke requirements**

Tambahkan baris berikut ke `requirements.txt` (jangan hapus yang sudah ada):

```
pytest>=8.0
httpx>=0.27
```

`httpx` dibutuhkan `fastapi.testclient.TestClient` di Task 7.

- [ ] **Step 2: Buat konfigurasi pytest**

Buat `pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -v
```

- [ ] **Step 3: Pasang dependensi**

Jalankan:

```bash
pip install -r requirements.txt
```

- [ ] **Step 4: Tulis test yang gagal**

Buat `tests/__init__.py` (kosong) dan `tests/test_models.py`:

```python
import pytest
from app.assistant.models import RetrievedChunk, derive_poi


def _chunk(title: str, poi_unity_id: str | None, poi_name: str | None = None,
           score: float = 0.9) -> RetrievedChunk:
    return RetrievedChunk(
        content="isi",
        title=title,
        doc_type="layanan",
        poi_unity_id=poi_unity_id,
        poi_name=poi_name,
        floor=None,
        is_simulated=True,
        score=score,
    )


def test_derive_poi_ambil_dari_chunk_peringkat_satu():
    chunks = [
        _chunk("Farmasi", "guid-farmasi", "Farmasi"),
        _chunk("IGD", "guid-igd", "IGD"),
    ]
    assert derive_poi(chunks) == ("guid-farmasi", "Farmasi")


def test_derive_poi_null_kalau_peringkat_satu_tanpa_poi():
    """Sengaja TIDAK menyisir ke peringkat 2 — lihat 'Keputusan Penafsiran' di plan."""
    chunks = [
        _chunk("Alur BPJS", None),
        _chunk("Farmasi", "guid-farmasi", "Farmasi"),
    ]
    assert derive_poi(chunks) == (None, None)


def test_derive_poi_daftar_kosong():
    assert derive_poi([]) == (None, None)
```

- [ ] **Step 5: Jalankan test, pastikan GAGAL**

Run: `pytest tests/test_models.py -v`
Expected: FAIL dengan `ModuleNotFoundError: No module named 'app.assistant'`

- [ ] **Step 6: Tulis implementasinya**

Buat `app/assistant/__init__.py` (kosong), lalu `app/assistant/models.py`:

```python
"""Bentuk data untuk endpoint asisten.

RetrievedChunk dipakai lintas modul (retrieval -> generation -> router), jadi
ditaruh di sini, bukan di salah satu modul pemakainya.
"""

from dataclasses import dataclass

from pydantic import BaseModel, Field


class AssistantQueryRequest(BaseModel):
    user_text: str = Field(min_length=1, max_length=500)
    # Opsional, dan HANYA mem-bias peringkat retrieval (spec section 5).
    # Kosong sebelum VPS localize berhasil (ADR-007/ADR-011) dan itu normal.
    current_floor: str | None = None
    building: str | None = None


class Source(BaseModel):
    title: str
    doc_type: str
    is_simulated: bool


class AssistantQueryResponse(BaseModel):
    answer: str
    sources: list[Source]
    poi_id: str | None
    poi_name: str | None
    contains_simulated_data: bool


@dataclass
class RetrievedChunk:
    content: str
    title: str
    doc_type: str
    poi_unity_id: str | None
    poi_name: str | None
    floor: str | None
    is_simulated: bool
    score: float


@dataclass
class ScheduleRow:
    doctor_name: str
    specialty: str
    day_of_week: int          # 1 = Senin
    start_time: str           # "08:00"
    end_time: str             # "14:00"
    poi_unity_id: str | None
    is_simulated: bool


def derive_poi(chunks: list[RetrievedChunk]) -> tuple[str | None, str | None]:
    """Turunkan (poi_id, poi_name) dari chunk PERINGKAT SATU saja.

    LLM tidak pernah dimintai GUID: model bahasa tidak andal mereproduksi string
    identitas panjang, dan GUID salah satu karakter menggagalkan navigasi tanpa
    gejala yang jelas. Pola yang sama dengan ADR-021 di repo Unity: satu pemilik
    sah, sisanya diturunkan.

    Sengaja TIDAK menyisir ke peringkat berikutnya (lihat 'Keputusan Penafsiran'
    di plan): poi_id jadi dasar tombol "mulai rute", jadi lebih baik kosong
    daripada menunjuk lokasi yang cuma disinggung sekilas.
    """
    if not chunks:
        return None, None
    top = chunks[0]
    if top.poi_unity_id:
        return top.poi_unity_id, top.poi_name
    return None, None
```

- [ ] **Step 7: Jalankan test, pastikan LULUS**

Run: `pytest tests/test_models.py -v`
Expected: PASS, 3 test lulus

- [ ] **Step 8: Commit**

```bash
git add requirements.txt pytest.ini app/assistant tests
git commit -m "feat(assistant): bentuk data + aturan poi_id diturunkan dari metadata"
```

---

### Task 2: Skema DB (ekstensi, dua tabel, index)

**Files:**
- Create: `schema_rag.sql`
- Create: `tests/test_schema_rag.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: tabel `knowledge_chunks` dan `doctor_schedules` sesuai spec §6

- [ ] **Step 1: Tulis DDL**

Buat `schema_rag.sql`:

```sql
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
```

Catatan: fungsi `set_updated_at()` sudah ada, dibuat oleh `schema.sql`. Jalankan `schema.sql` lebih dulu kalau DB masih kosong.

- [ ] **Step 2: Tambahkan env var baru ke `.env.example`**

Tambahkan di akhir `.env.example`:

```
# Groq API key untuk endpoint asisten (POST /api/assistant/query). Dipanggil dari
# SERVER, bukan dari APK — ini yang menutup utang keamanan yang tercatat di
# OllamaConnector.cs (key ikut ter-bundle ke APK kalau dipanggil dari client).
GROQ_API_KEY=

# Opsional, hanya untuk menjalankan test yang butuh DB sungguhan.
# Kalau kosong, test tersebut di-skip (bukan gagal).
TEST_DATABASE_URL=
```

- [ ] **Step 3: Tulis test yang gagal**

Buat `tests/test_schema_rag.py`:

```python
"""Verifikasi skema RAG benar-benar terpasang di DB.

Di-skip kalau TEST_DATABASE_URL tidak diset, supaya `pytest` tetap hijau di mesin
yang belum menyalakan Postgres lokal.
"""

import os

import psycopg
import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL tidak diset"
)


@pytest.fixture
def conn():
    with psycopg.connect(TEST_DATABASE_URL) as c:
        yield c


def test_ekstensi_vector_aktif(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        assert cur.fetchone() is not None


def test_tabel_knowledge_chunks_ada_dengan_dimensi_384(conn):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT atttypmod FROM pg_attribute
               WHERE attrelid = 'knowledge_chunks'::regclass AND attname = 'embedding'"""
        )
        row = cur.fetchone()
        assert row is not None, "kolom embedding tidak ada"
        # pgvector menyimpan dimensi di atttypmod apa adanya
        assert row[0] == 384


def test_index_hnsw_terpasang(conn):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT indexdef FROM pg_indexes
               WHERE tablename = 'knowledge_chunks' AND indexname = 'idx_chunks_embedding'"""
        )
        row = cur.fetchone()
        assert row is not None, "index HNSW tidak ada"
        assert "hnsw" in row[0].lower()


def test_tabel_doctor_schedules_ada(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('doctor_schedules')")
        assert cur.fetchone()[0] is not None


def test_day_of_week_menolak_nilai_di_luar_1_sampai_7(conn):
    with conn.cursor() as cur:
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                """INSERT INTO doctor_schedules
                   (doctor_name, specialty, day_of_week, start_time, end_time)
                   VALUES ('dr. Uji', 'Uji', 8, '08:00', '09:00')"""
            )
        conn.rollback()
```

- [ ] **Step 4: Nyalakan Postgres lokal dan jalankan test, pastikan GAGAL**

```bash
docker run -d --name darsi-pg -e POSTGRES_PASSWORD=darsi -e POSTGRES_DB=darsi -p 5433:5432 pgvector/pgvector:pg16
export TEST_DATABASE_URL="postgresql://postgres:darsi@localhost:5433/darsi"
psql "$TEST_DATABASE_URL" -f schema.sql
pytest tests/test_schema_rag.py -v
```

Expected: FAIL, `UndefinedTable` untuk `knowledge_chunks`.

Catatan: image-nya `pgvector/pgvector:pg16`, bukan `postgres:16` seperti di README, karena `postgres:16` polos tidak membawa ekstensi `vector`.

- [ ] **Step 5: Terapkan skema**

```bash
psql "$TEST_DATABASE_URL" -f schema_rag.sql
```

- [ ] **Step 6: Jalankan test, pastikan LULUS**

Run: `pytest tests/test_schema_rag.py -v`
Expected: PASS, 5 test lulus

- [ ] **Step 7: Commit**

```bash
git add schema_rag.sql .env.example tests/test_schema_rag.py
git commit -m "feat(assistant): skema knowledge_chunks + doctor_schedules (pgvector HNSW)"
```

---

### Task 3: Modul embedding (ONNX, dimuat sekali)

**Files:**
- Create: `app/assistant/embedding.py`
- Create: `tests/test_embedding.py`
- Modify: `requirements.txt`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: konstanta dari Global Constraints
- Produces: `load_model()`, `embed(texts: list[str]) -> list[list[float]]`, `EMBEDDING_DIM = 384`, `MODEL_NAME`

- [ ] **Step 1: Tambahkan fastembed ke requirements**

Tambahkan ke `requirements.txt`:

```
fastembed>=0.4
```

Lalu pasang:

```bash
pip install -r requirements.txt
```

Unduhan pertama menarik bobot model 0.22 GB. Ini wajar, bukan tanda ada yang salah.

- [ ] **Step 2: Abaikan cache model di git**

Tambahkan ke `.gitignore`:

```
# Cache bobot model fastembed — jangan pernah ikut ke git (ratusan MB)
.fastembed_cache/
```

- [ ] **Step 3: Tulis test yang gagal**

Buat `tests/test_embedding.py`:

```python
"""Test ini memuat model sungguhan (0.22 GB), jadi lambat di jalannya yang pertama.
Sengaja tidak di-mock: yang perlu dibuktikan justru dimensi dan perilaku model asli,
karena dimensi yang meleset merusak skema DB.
"""

import pytest

from app.assistant import embedding


@pytest.fixture(scope="module", autouse=True)
def _load():
    embedding.load_model()


def test_dimensi_harus_384():
    """384 dikunci di skema DB (vector(384)). Kalau ini gagal, skema ikut salah."""
    vecs = embedding.embed(["poli anak di lantai berapa"])
    assert len(vecs) == 1
    assert len(vecs[0]) == embedding.EMBEDDING_DIM == 384


def test_embed_banyak_teks_sekaligus():
    vecs = embedding.embed(["farmasi", "instalasi gawat darurat", "toilet"])
    assert len(vecs) == 3
    assert all(len(v) == 384 for v in vecs)


def test_hasilnya_deterministik():
    a = embedding.embed(["alur pendaftaran bpjs"])[0]
    b = embedding.embed(["alur pendaftaran bpjs"])[0]
    assert a == pytest.approx(b)


def test_kalimat_indonesia_yang_mirip_makna_lebih_dekat_daripada_yang_beda():
    """Bukti kasar bahwa Bahasa Indonesia benar-benar dipahami model, bukan sekadar
    diproses. Kalau ini gagal, pilihan modelnya yang salah, bukan kodenya."""
    def cos(u, v):
        dot = sum(x * y for x, y in zip(u, v))
        nu = sum(x * x for x in u) ** 0.5
        nv = sum(y * y for y in v) ** 0.5
        return dot / (nu * nv)

    obat, apotek, parkir = embedding.embed(["tempat ambil obat", "apotek", "parkir mobil"])
    assert cos(obat, apotek) > cos(obat, parkir)


def test_embed_tanpa_load_model_gagal_berisik():
    embedding._model = None
    with pytest.raises(RuntimeError, match="belum dimuat"):
        embedding.embed(["apa saja"])
    embedding.load_model()  # pulihkan untuk test lain
```

- [ ] **Step 4: Jalankan test, pastikan GAGAL**

Run: `pytest tests/test_embedding.py -v`
Expected: FAIL dengan `ModuleNotFoundError: No module named 'app.assistant.embedding'`

- [ ] **Step 5: Tulis implementasinya**

Buat `app/assistant/embedding.py`:

```python
"""Embedding lokal lewat ONNX.

Dipilih ONNX, bukan sentence-transformers, karena sentence-transformers menarik
torch (~800MB-2GB terpasang) dan berisiko menabrak batas memori/image Railway di
service yang dependensinya masih sangat ringan. Sifatnya sama: lokal, tanpa API
key, portable.

Model dimuat SEKALI saat startup (dipanggil dari lifespan di main.py), bukan
per-request. Tanpa itu, request pertama akan lambat seperti gejala pre-warm Ollama
yang sudah dikenal di repo Unity.
"""

from fastembed import TextEmbedding

# Terverifikasi 2026-08-20: 384 dimensi, 0.22 GB, Bahasa Indonesia ada di daftar
# 50 bahasa yang didukung. Mengganti model = harus embed ulang seluruh tabel.
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384

_model: TextEmbedding | None = None


def load_model() -> None:
    """Muat bobot model ke memori. Idempoten."""
    global _model
    if _model is None:
        _model = TextEmbedding(model_name=MODEL_NAME, cache_dir=".fastembed_cache")


def embed(texts: list[str]) -> list[list[float]]:
    """Ubah daftar teks jadi daftar vektor 384 dimensi, urutannya terjaga."""
    if _model is None:
        raise RuntimeError(
            "Model embedding belum dimuat. Panggil load_model() saat startup."
        )
    return [vec.tolist() for vec in _model.embed(texts)]
```

- [ ] **Step 6: Jalankan test, pastikan LULUS**

Run: `pytest tests/test_embedding.py -v`
Expected: PASS, 5 test lulus (jalan pertama lambat karena mengunduh model)

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .gitignore app/assistant/embedding.py tests/test_embedding.py
git commit -m "feat(assistant): modul embedding ONNX 384-dim, dimuat sekali"
```

---

### Task 4: Corpus simulasi dan script ingest

**Files:**
- Create: `data/__init__.py`
- Create: `data/corpus_simulasi.py`
- Create: `scripts/ingest_corpus.py`
- Create: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `embedding.load_model()`, `embedding.embed()`
- Produces: `CHUNKS: list[dict]`, `SCHEDULES: list[dict]`, `ingest(conn) -> dict`

- [ ] **Step 1: Tulis corpus simulasi**

Buat `data/__init__.py` (kosong) dan `data/corpus_simulasi.py`:

```python
"""Corpus SIMULASI untuk RAG Assistant.

PERINGATAN: seluruh isi berkas ini KARANGAN. RS Islam A. Yani adalah rumah sakit
sungguhan, tapi belum memberikan data operasional dan izinnya belum ada. Nama
dokter memakai pola "Fulan/Fulanah" supaya jelas fiktif.

Semua baris masuk DB dengan is_simulated = true. Saat data asli tersedia:
    DELETE FROM knowledge_chunks WHERE is_simulated = true;
    DELETE FROM doctor_schedules  WHERE is_simulated = true;
lalu ingest ulang dengan is_simulated = false.
"""

# poi_unity_id sengaja None: GUID POI berasal dari Unity lewat POST /api/poi/sync,
# dan POI seperti "Poli Anak" belum ada di scene. Menebak GUID di sini justru
# melanggar aturan "satu pemilik data" (ADR-021). Isi belakangan setelah POI-nya
# benar-benar ada, atau biarkan None (jawaban tetap keluar, cuma tanpa tombol rute).
CHUNKS: list[dict] = [
    {
        "title": "Alur Pendaftaran BPJS Rawat Jalan",
        "doc_type": "sop",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#bpjs",
        "content": (
            "Alur pendaftaran pasien BPJS rawat jalan. Pasien BPJS membawa kartu BPJS "
            "aktif, KTP, dan surat rujukan dari Faskes 1 yang masih berlaku. Rujukan "
            "berlaku 90 hari sejak diterbitkan. Pendaftaran dilayani di loket "
            "Pendaftaran BPJS di Lantai 1 mulai pukul 07.00. Setelah mendapat nomor "
            "antrean, pasien menunggu panggilan di ruang tunggu poli tujuan."
        ),
    },
    {
        "title": "Alur Pasien IGD",
        "doc_type": "sop",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#igd",
        "content": (
            "Alur pasien IGD. Pasien gawat darurat langsung menuju IGD tanpa mendaftar "
            "lebih dulu. Pendaftaran administrasi diurus keluarga setelah pasien "
            "ditangani. IGD melayani 24 jam setiap hari termasuk hari libur."
        ),
    },
    {
        "title": "Alur Rawat Jalan Pasien Umum",
        "doc_type": "sop",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#umum",
        "content": (
            "Alur rawat jalan pasien umum non-BPJS. Pasien umum mendaftar langsung di "
            "loket Pendaftaran tanpa perlu surat rujukan. Pembayaran dilakukan di Kasir "
            "setelah pemeriksaan selesai. Pendaftaran rawat jalan dibuka pukul 07.00 "
            "sampai 15.00."
        ),
    },
    {
        "title": "Layanan Farmasi",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#farmasi",
        "content": (
            "Farmasi melayani penebusan resep pasien rawat jalan dan rawat inap. Jam "
            "layanan pukul 07.00 sampai 21.00. Resep BPJS dilayani di loket terpisah "
            "dari resep umum. Obat racikan membutuhkan waktu tunggu lebih lama."
        ),
    },
    {
        "title": "Layanan Radiologi",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#radiologi",
        "content": (
            "Radiologi melayani pemeriksaan rontgen, USG, dan CT scan. Pemeriksaan "
            "harus membawa surat pengantar dari dokter. Pemeriksaan USG perut "
            "mengharuskan pasien berpuasa 6 jam sebelumnya. Layanan buka pukul 08.00 "
            "sampai 20.00, dan 24 jam untuk kasus dari IGD."
        ),
    },
    {
        "title": "Layanan Laboratorium",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#lab",
        "content": (
            "Laboratorium melayani pemeriksaan darah, urine, dan sampel lain. "
            "Pengambilan sampel darah puasa dilayani pukul 07.00 sampai 09.00. Hasil "
            "pemeriksaan rutin keluar di hari yang sama."
        ),
    },
    {
        "title": "Poli Anak",
        "doc_type": "layanan",
        "floor": "Lantai 2",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#poli_anak",
        "content": (
            "Poli Anak berada di Lantai 2 dan melayani pemeriksaan kesehatan anak, "
            "imunisasi, serta konsultasi tumbuh kembang. Pasien anak dengan demam "
            "tinggi disarankan langsung ke IGD."
        ),
    },
    {
        "title": "Poli Penyakit Dalam",
        "doc_type": "layanan",
        "floor": "Lantai 2",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#poli_dalam",
        "content": (
            "Poli Penyakit Dalam berada di Lantai 2, melayani konsultasi penyakit "
            "kronis seperti diabetes, hipertensi, dan gangguan pencernaan."
        ),
    },
    {
        "title": "Musholla dan Fasilitas Ibadah",
        "doc_type": "layanan",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#musholla",
        "content": (
            "Musholla berada di Lantai 1 dekat area kantin, terbuka 24 jam, dilengkapi "
            "tempat wudhu terpisah untuk pria dan wanita. Tersedia mukena dan sajadah."
        ),
    },
    {
        "title": "FAQ: Berobat tanpa surat rujukan",
        "doc_type": "faq",
        "floor": None,
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#faq_rujukan",
        "content": (
            "Apakah bisa berobat tanpa rujukan? Pasien umum bisa langsung mendaftar "
            "tanpa rujukan. Pasien BPJS memerlukan rujukan dari Faskes 1, kecuali "
            "kasus gawat darurat yang ditangani IGD."
        ),
    },
    {
        "title": "FAQ: Jam besuk pasien rawat inap",
        "doc_type": "faq",
        "floor": None,
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#faq_besuk",
        "content": (
            "Jam besuk pasien rawat inap dibagi dua sesi: siang pukul 11.00 sampai "
            "13.00 dan sore pukul 17.00 sampai 19.00. Anak di bawah 12 tahun tidak "
            "disarankan ikut membesuk."
        ),
    },
    {
        "title": "FAQ: Cara mendapatkan salinan rekam medis",
        "doc_type": "faq",
        "floor": "Lantai 1",
        "building": "RS Islam Ahmad Yani",
        "poi_unity_id": None,
        "source_ref": "corpus_simulasi.py#faq_rekam_medis",
        "content": (
            "Permintaan salinan rekam medis diajukan di bagian Rekam Medis Lantai 1 "
            "dengan membawa KTP pasien. Permintaan oleh keluarga memerlukan surat kuasa. "
            "Berkas selesai dalam 3 hari kerja."
        ),
    },
]

SCHEDULES: list[dict] = [
    {"doctor_name": "dr. Fulan Hidayat, Sp.A", "specialty": "Anak",
     "day_of_week": 1, "start_time": "08:00", "end_time": "14:00", "poi_unity_id": None},
    {"doctor_name": "dr. Fulan Hidayat, Sp.A", "specialty": "Anak",
     "day_of_week": 3, "start_time": "08:00", "end_time": "14:00", "poi_unity_id": None},
    {"doctor_name": "dr. Fulanah Rahmawati, Sp.PD", "specialty": "Penyakit Dalam",
     "day_of_week": 2, "start_time": "09:00", "end_time": "15:00", "poi_unity_id": None},
    {"doctor_name": "dr. Fulanah Rahmawati, Sp.PD", "specialty": "Penyakit Dalam",
     "day_of_week": 4, "start_time": "09:00", "end_time": "15:00", "poi_unity_id": None},
    {"doctor_name": "dr. Fulan Santoso, Sp.OG", "specialty": "Kandungan",
     "day_of_week": 5, "start_time": "10:00", "end_time": "16:00", "poi_unity_id": None},
]
```

- [ ] **Step 2: Tulis test yang gagal**

Buat `tests/test_ingest.py`:

```python
import os

import psycopg
import pytest

from data import corpus_simulasi
from scripts.ingest_corpus import ingest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL tidak diset"
)


@pytest.fixture
def conn():
    with psycopg.connect(TEST_DATABASE_URL) as c:
        with c.cursor() as cur:
            cur.execute("DELETE FROM knowledge_chunks")
            cur.execute("DELETE FROM doctor_schedules")
        c.commit()
        yield c


def test_ingest_memasukkan_semua_baris(conn):
    hasil = ingest(conn)
    assert hasil["chunks"] == len(corpus_simulasi.CHUNKS)
    assert hasil["schedules"] == len(corpus_simulasi.SCHEDULES)


def test_semua_baris_ditandai_simulasi(conn):
    ingest(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM knowledge_chunks WHERE NOT is_simulated")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM doctor_schedules WHERE NOT is_simulated")
        assert cur.fetchone()[0] == 0


def test_ingest_idempoten(conn):
    """Jalankan dua kali tidak menggandakan baris."""
    ingest(conn)
    ingest(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM knowledge_chunks")
        assert cur.fetchone()[0] == len(corpus_simulasi.CHUNKS)


def test_embedding_tersimpan_dengan_dimensi_benar(conn):
    ingest(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT vector_dims(embedding) FROM knowledge_chunks LIMIT 1")
        assert cur.fetchone()[0] == 384


def test_nama_dokter_memakai_pola_fiktif(conn):
    """Aturan spec section 7.1: nama dokter wajib jelas karangan."""
    for s in corpus_simulasi.SCHEDULES:
        assert "Fulan" in s["doctor_name"]
```

- [ ] **Step 3: Jalankan test, pastikan GAGAL**

Run: `pytest tests/test_ingest.py -v`
Expected: FAIL dengan `ModuleNotFoundError: No module named 'scripts'`

- [ ] **Step 4: Tulis script ingest**

Buat `scripts/__init__.py` (kosong) dan `scripts/ingest_corpus.py`:

```python
"""Masukkan corpus simulasi ke DB, lengkap dengan embedding-nya.

Idempoten lewat ON CONFLICT: jalankan berkali-kali aman, baris tidak menggandakan.

Pakai:
    export DATABASE_URL=...
    python -m scripts.ingest_corpus
"""

import os
import sys

import psycopg

from app.assistant import embedding
from data import corpus_simulasi


def ingest(conn: psycopg.Connection, is_simulated: bool = True) -> dict:
    """Embed lalu upsert seluruh corpus. Mengembalikan jumlah baris per tabel."""
    embedding.load_model()

    chunks = corpus_simulasi.CHUNKS
    vectors = embedding.embed([c["content"] for c in chunks])

    with conn.cursor() as cur:
        for chunk, vec in zip(chunks, vectors):
            cur.execute(
                """INSERT INTO knowledge_chunks
                       (content, embedding, doc_type, title, poi_unity_id,
                        building, floor, is_simulated, source_ref)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (title, source_ref) DO UPDATE SET
                       content = EXCLUDED.content,
                       embedding = EXCLUDED.embedding,
                       doc_type = EXCLUDED.doc_type,
                       poi_unity_id = EXCLUDED.poi_unity_id,
                       building = EXCLUDED.building,
                       floor = EXCLUDED.floor,
                       is_simulated = EXCLUDED.is_simulated""",
                (chunk["content"], str(vec), chunk["doc_type"], chunk["title"],
                 chunk["poi_unity_id"], chunk["building"], chunk["floor"],
                 is_simulated, chunk["source_ref"]),
            )

        for s in corpus_simulasi.SCHEDULES:
            cur.execute(
                """INSERT INTO doctor_schedules
                       (doctor_name, specialty, poi_unity_id, day_of_week,
                        start_time, end_time, is_simulated)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (doctor_name, day_of_week, start_time) DO UPDATE SET
                       specialty = EXCLUDED.specialty,
                       poi_unity_id = EXCLUDED.poi_unity_id,
                       end_time = EXCLUDED.end_time,
                       is_simulated = EXCLUDED.is_simulated""",
                (s["doctor_name"], s["specialty"], s["poi_unity_id"], s["day_of_week"],
                 s["start_time"], s["end_time"], is_simulated),
            )
    conn.commit()
    return {"chunks": len(chunks), "schedules": len(corpus_simulasi.SCHEDULES)}


def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL kosong.", file=sys.stderr)
        return 1
    with psycopg.connect(url) as conn:
        hasil = ingest(conn)
    print(f"Selesai: {hasil['chunks']} chunk, {hasil['schedules']} jadwal (SIMULASI).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Jalankan test, pastikan LULUS**

Run: `pytest tests/test_ingest.py -v`
Expected: PASS, 5 test lulus

- [ ] **Step 6: Commit**

```bash
git add data scripts tests/test_ingest.py
git commit -m "feat(assistant): corpus simulasi + script ingest idempoten"
```

---

### Task 5: Retrieval hybrid (vector, jadwal, bias lantai)

**Files:**
- Create: `app/assistant/retrieval.py`
- Create: `tests/test_retrieval.py`

**Interfaces:**
- Consumes: `embedding.embed()`, `models.RetrievedChunk`, `models.ScheduleRow`
- Produces: `search_chunks(conn, query, current_floor, building, limit=5) -> list[RetrievedChunk]`, `find_schedules(conn, user_text, poi_unity_id) -> list[ScheduleRow]`, `FLOOR_BONUS`, `MIN_SCORE`

- [ ] **Step 1: Tulis test yang gagal**

Buat `tests/test_retrieval.py`:

```python
import os

import psycopg
import pytest

from app.assistant import retrieval
from scripts.ingest_corpus import ingest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL tidak diset"
)


@pytest.fixture(scope="module")
def conn():
    with psycopg.connect(TEST_DATABASE_URL) as c:
        with c.cursor() as cur:
            cur.execute("DELETE FROM knowledge_chunks")
            cur.execute("DELETE FROM doctor_schedules")
        c.commit()
        ingest(c)
        yield c


def test_pertanyaan_obat_menemukan_farmasi(conn):
    hasil = retrieval.search_chunks(conn, "mau nebus resep obat", None, None)
    assert hasil, "tidak ada hasil sama sekali"
    assert "Farmasi" in hasil[0].title


def test_pertanyaan_bpjs_menemukan_alur_bpjs(conn):
    """Tolok ukur project ini recall@3 (lihat scripts/eval_retrieval.py), jadi yang
    diuji "masuk 3 besar", bukan "peringkat 1". Menuntut peringkat 1 di sini akan
    lebih ketat daripada standar yang dipakai plan-nya sendiri.

    Terukur: untuk pertanyaan ini chunk BPJS dapat 0.344 dan kalah dari FAQ
    "Berobat tanpa surat rujukan" (0.408) yang isinya memang bersinggungan.
    """
    hasil = retrieval.search_chunks(conn, "syarat daftar pakai bpjs apa saja", None, None)
    assert any("BPJS" in c.title for c in hasil[:3])


def test_hasil_terurut_skor_menurun(conn):
    hasil = retrieval.search_chunks(conn, "poli anak", None, None)
    skor = [c.score for c in hasil]
    assert skor == sorted(skor, reverse=True)


def test_bias_lantai_menaikkan_peringkat_bukan_membuang(conn):
    """Aturan spec section 5: lantai MEM-BIAS, TIDAK mem-filter keras.
    User di Lantai 1 bertanya soal Poli Anak (Lantai 2) harus tetap ketemu."""
    hasil = retrieval.search_chunks(conn, "poli anak di mana", "Lantai 1", None)
    judul = [c.title for c in hasil]
    assert "Poli Anak" in judul, "info lantai lain hilang — ini filter keras, bukan bias"


def test_bias_lantai_benar_benar_berpengaruh(conn):
    """Dengan pertanyaan yang ambigu antar-lantai, chunk di lantai user naik."""
    tanpa = retrieval.search_chunks(conn, "jam layanan", None, None)
    dengan = retrieval.search_chunks(conn, "jam layanan", "Lantai 2", None)
    lantai2_tanpa = [i for i, c in enumerate(tanpa) if c.floor == "Lantai 2"]
    lantai2_dengan = [i for i, c in enumerate(dengan) if c.floor == "Lantai 2"]
    if lantai2_tanpa and lantai2_dengan:
        assert lantai2_dengan[0] <= lantai2_tanpa[0]


def test_pertanyaan_di_luar_cakupan_tidak_mengembalikan_apa_apa(conn):
    hasil = retrieval.search_chunks(conn, "harga tiket pesawat ke jakarta", None, None)
    assert hasil == []


def test_cari_jadwal_lewat_spesialisasi(conn):
    hasil = retrieval.find_schedules(conn, "dokter anak praktek kapan", None)
    assert hasil
    assert all(s.specialty == "Anak" for s in hasil)


def test_cari_jadwal_lewat_nama_dokter(conn):
    hasil = retrieval.find_schedules(conn, "jadwal dr. Rahmawati", None)
    assert hasil
    assert all("Rahmawati" in s.doctor_name for s in hasil)


def test_pertanyaan_tanpa_unsur_jadwal_tidak_mengembalikan_jadwal(conn):
    assert retrieval.find_schedules(conn, "toilet di mana", None) == []
```

- [ ] **Step 2: Jalankan test, pastikan GAGAL**

Run: `pytest tests/test_retrieval.py -v`
Expected: FAIL dengan `ModuleNotFoundError: No module named 'app.assistant.retrieval'`

- [ ] **Step 3: Tulis implementasinya**

Buat `app/assistant/retrieval.py`:

```python
"""Retrieval hybrid: prosa lewat pgvector, jadwal lewat SQL biasa.

Jadwal SENGAJA tidak di-embed. "dr. Fulan praktek jam berapa" itu lookup, bukan
pencarian makna. Vector search di data tabular mengembalikan baris yang mirip
bentuknya, bukan yang benar, dan jam praktek salah di RS bukan kesalahan kecil.
"""

import psycopg

from app.assistant import embedding
from app.assistant.models import RetrievedChunk, ScheduleRow

# ponytail: dua knob kalibrasi, bukan konstanta fisika. Angkanya ditetapkan lewat
# scripts/eval_retrieval.py, bukan ditebak. Kalau recall@3 jelek, ini yang disetel.
#
# 0.30, diturunkan dari 0.35 berdasar pengukuran: pertanyaan "syarat daftar pakai
# bpjs apa saja" memberi skor 0.344 pada chunk "Alur Pendaftaran BPJS Rawat Jalan",
# jadi ambang 0.35 membuang chunk yang justru jawabannya. Menaikkan lagi berarti
# menyembunyikan informasi yang relevan.
MIN_SCORE = 0.30     # di bawah ini dianggap tidak relevan (spec section 8.3)
FLOOR_BONUS = 0.05   # tambahan skor kalau chunk selantai dengan user
BUILDING_BONUS = 0.02

# Ambil lebih banyak dari yang dipakai, supaya bias lantai punya ruang menyusun
# ulang peringkat. Pembiasan dilakukan di Python, BUKAN di ORDER BY SQL: menaruh
# CASE di ORDER BY membuat index HNSW tidak terpakai dan query jadi seq scan.
_OVERFETCH = 20


def search_chunks(
    conn: psycopg.Connection,
    query: str,
    current_floor: str | None,
    building: str | None,
    limit: int = 5,
) -> list[RetrievedChunk]:
    """Cari chunk prosa paling relevan. Lantai/gedung hanya mem-bias peringkat."""
    vec = embedding.embed([query])[0]

    with conn.cursor() as cur:
        cur.execute(
            """SELECT k.content, k.title, k.doc_type, k.poi_unity_id, p.name AS poi_name,
                      k.floor, k.building, k.is_simulated,
                      1 - (k.embedding <=> %s::vector) AS score
               FROM knowledge_chunks k
               LEFT JOIN pois p ON p.unity_id = k.poi_unity_id
               ORDER BY k.embedding <=> %s::vector
               LIMIT %s""",
            (str(vec), str(vec), _OVERFETCH),
        )
        rows = cur.fetchall()

    hasil: list[RetrievedChunk] = []
    for r in rows:
        skor = float(r["score"])
        # Bias, bukan filter: chunk di lantai lain tetap ikut, cuma tidak dapat bonus.
        if current_floor and r["floor"] == current_floor:
            skor += FLOOR_BONUS
        if building and r["building"] == building:
            skor += BUILDING_BONUS
        if skor < MIN_SCORE:
            continue
        hasil.append(
            RetrievedChunk(
                content=r["content"],
                title=r["title"],
                doc_type=r["doc_type"],
                poi_unity_id=r["poi_unity_id"],
                poi_name=r["poi_name"],
                floor=r["floor"],
                is_simulated=r["is_simulated"],
                score=skor,
            )
        )

    hasil.sort(key=lambda c: c.score, reverse=True)
    return hasil[:limit]


def find_schedules(
    conn: psycopg.Connection,
    user_text: str,
    poi_unity_id: str | None,
) -> list[ScheduleRow]:
    """Lookup jadwal. Cocokkan spesialisasi atau nama dokter yang DISEBUT di pertanyaan.

    Arah pencocokannya sengaja terbalik dari pencarian biasa: nilai dari DB dicari
    KEBERADAANNYA di dalam teks pertanyaan, bukan sebaliknya.

    Nama dokter dipecah jadi token, BUKAN diambil per posisi kata. "dr. Fulanah
    Rahmawati, Sp.PD" harus ketemu baik lewat "Fulanah" maupun "Rahmawati", dan
    pendekatan posisi (split_part ke-2) diam-diam mengembalikan kosong untuk yang
    kedua. Kosong itu gejala paling berbahaya di sini: terlihat seperti "jadwal
    tidak ada", bukan seperti bug. Token >= 4 huruf membuang "dr" dan gelar pendek.

    poi_unity_id di-cast ::text karena Postgres tidak bisa menyimpulkan tipe
    parameter yang bernilai NULL (AmbiguousParameter). Tidak perlu penjaga
    "IS NOT NULL": `poi_unity_id = NULL` memang tidak pernah cocok.
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT doctor_name, specialty, day_of_week, start_time, end_time,
                      poi_unity_id, is_simulated
               FROM doctor_schedules
               WHERE %(teks)s ILIKE '%%' || specialty || '%%'
                  OR EXISTS (
                        SELECT 1
                        FROM unnest(string_to_array(
                                 regexp_replace(doctor_name, '[.,]', '', 'g'), ' ')) AS w
                        WHERE length(w) >= 4 AND %(teks)s ILIKE '%%' || w || '%%'
                     )
                  OR poi_unity_id = %(poi)s::text
               ORDER BY day_of_week, start_time""",
            {"teks": user_text, "poi": poi_unity_id},
        )
        rows = cur.fetchall()

    return [
        ScheduleRow(
            doctor_name=r["doctor_name"],
            specialty=r["specialty"],
            day_of_week=r["day_of_week"],
            start_time=r["start_time"].strftime("%H:%M"),
            end_time=r["end_time"].strftime("%H:%M"),
            poi_unity_id=r["poi_unity_id"],
            is_simulated=r["is_simulated"],
        )
        for r in rows
    ]
```

Catatan: query memakai `dict_row` seperti pola `app/main.py`. Pastikan koneksi test dibuat dengan `row_factory=dict_row`; kalau tidak, ubah fixture `conn` di test menjadi `psycopg.connect(TEST_DATABASE_URL, row_factory=dict_row)`.

- [ ] **Step 4: Sesuaikan fixture test agar memakai dict_row**

Di `tests/test_retrieval.py` dan `tests/test_ingest.py`, ubah pembuatan koneksi:

```python
from psycopg.rows import dict_row
...
with psycopg.connect(TEST_DATABASE_URL, row_factory=dict_row) as c:
```

- [ ] **Step 5: Jalankan test, pastikan LULUS**

Run: `pytest tests/test_retrieval.py -v`
Expected: PASS, 9 test lulus

- [ ] **Step 6: Commit**

```bash
git add app/assistant/retrieval.py tests/test_retrieval.py tests/test_ingest.py
git commit -m "feat(assistant): retrieval hybrid dengan bias lantai (bukan filter)"
```

---

### Task 6: Generation lewat Groq

**Files:**
- Create: `app/assistant/generation.py`
- Create: `tests/test_generation.py`

**Interfaces:**
- Consumes: `models.RetrievedChunk`, `models.ScheduleRow`
- Produces: `build_prompt(user_text, chunks, schedules) -> str`, `generate_answer(prompt) -> str`, `NO_CONTEXT_ANSWER`, `GROQ_MODEL`

- [ ] **Step 1: Tulis test yang gagal**

Buat `tests/test_generation.py`:

```python
import pytest

from app.assistant.generation import NO_CONTEXT_ANSWER, build_prompt
from app.assistant.models import RetrievedChunk, ScheduleRow


def _chunk(title="Layanan Farmasi", content="Farmasi buka 07.00 sampai 21.00."):
    return RetrievedChunk(
        content=content, title=title, doc_type="layanan", poi_unity_id=None,
        poi_name=None, floor="Lantai 1", is_simulated=True, score=0.8,
    )


def _sched():
    return ScheduleRow(
        doctor_name="dr. Fulan Hidayat, Sp.A", specialty="Anak", day_of_week=1,
        start_time="08:00", end_time="14:00", poi_unity_id=None, is_simulated=True,
    )


def test_prompt_memuat_isi_chunk():
    prompt = build_prompt("farmasi buka jam berapa", [_chunk()], [])
    assert "Farmasi buka 07.00 sampai 21.00." in prompt


def test_prompt_memuat_pertanyaan_user():
    prompt = build_prompt("farmasi buka jam berapa", [_chunk()], [])
    assert "farmasi buka jam berapa" in prompt


def test_prompt_memuat_jadwal_dalam_bentuk_terbaca():
    prompt = build_prompt("dokter anak kapan", [], [_sched()])
    assert "dr. Fulan Hidayat, Sp.A" in prompt
    assert "Senin" in prompt
    assert "08:00" in prompt


def test_prompt_melarang_mengarang():
    prompt = build_prompt("apa saja", [_chunk()], [])
    assert "jangan mengarang" in prompt.lower()


def test_prompt_tidak_pernah_memuat_guid():
    """poi_id diturunkan dari metadata, LLM tidak boleh diminta menghasilkannya."""
    c = _chunk()
    c.poi_unity_id = "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"
    prompt = build_prompt("di mana farmasi", [c], [])
    assert "9b1deb4d" not in prompt


def test_tanpa_konteks_sama_sekali_menolak_tanpa_memanggil_llm():
    with pytest.raises(ValueError, match="tanpa konteks"):
        build_prompt("pertanyaan di luar cakupan", [], [])


def test_pesan_penolakan_tersedia_dan_jujur():
    assert "tidak" in NO_CONTEXT_ANSWER.lower()
```

- [ ] **Step 2: Jalankan test, pastikan GAGAL**

Run: `pytest tests/test_generation.py -v`
Expected: FAIL dengan `ModuleNotFoundError: No module named 'app.assistant.generation'`

- [ ] **Step 3: Tulis implementasinya**

Buat `app/assistant/generation.py`:

```python
"""Susun prompt lalu panggil Groq.

Groq dipanggil dari SERVER, bukan dari APK. Ini menutup utang keamanan yang sudah
tercatat di Assets/Speech Recognition/OllamaConnector.cs di repo Unity: kalau
dipanggil dari client, groqApiKey ikut ter-bundle ke APK dan bisa diekstrak
siapa pun yang men-decompile-nya.
"""

import os

import httpx

from app.assistant.models import RetrievedChunk, ScheduleRow

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# Sama dengan yang dipakai OllamaConnector.cs. llama-3.1-8b-instant dihentikan Groq
# untuk free/developer tier per 2026-08-16 (balas 404 kalau dipakai).
GROQ_MODEL = "openai/gpt-oss-20b"
GROQ_TIMEOUT_SECONDS = 20

NO_CONTEXT_ANSWER = (
    "Maaf, saya tidak punya informasi soal itu. Silakan tanyakan ke petugas "
    "Informasi di Lantai 1."
)

_HARI = {1: "Senin", 2: "Selasa", 3: "Rabu", 4: "Kamis",
         5: "Jumat", 6: "Sabtu", 7: "Minggu"}

_SYSTEM_PROMPT = """Kamu asisten informasi RS Islam A. Yani.

Aturan:
- Jawab HANYA berdasarkan informasi di bawah. Jangan mengarang apa pun yang tidak ada di sana.
- Kalau informasinya tidak cukup, katakan terus terang dan arahkan ke petugas Informasi.
- Jawab ringkas dalam Bahasa Indonesia, maksimal 3 kalimat.
- Jangan menyebutkan kode, ID, atau istilah teknis apa pun kepada pengguna.
- Jangan memberi nasihat medis. Untuk keluhan kesehatan, arahkan ke dokter atau IGD."""


def build_prompt(
    user_text: str,
    chunks: list[RetrievedChunk],
    schedules: list[ScheduleRow],
) -> str:
    """Rakit prompt dari konteks hasil retrieval.

    Sengaja gagal kalau tidak ada konteks sama sekali: meneruskan pertanyaan ke LLM
    tanpa bahan justru mengundang jawaban karangan, dan di konteks RS itu berbahaya.
    GUID POI tidak pernah dimasukkan ke prompt (lihat models.derive_poi).
    """
    if not chunks and not schedules:
        raise ValueError("tidak boleh menyusun prompt tanpa konteks")

    bagian: list[str] = [_SYSTEM_PROMPT, "", "INFORMASI:"]

    for c in chunks:
        bagian.append(f"- [{c.title}] {c.content}")

    if schedules:
        bagian.append("")
        bagian.append("JADWAL PRAKTEK DOKTER:")
        for s in schedules:
            bagian.append(
                f"- {s.doctor_name} ({s.specialty}), "
                f"{_HARI[s.day_of_week]} {s.start_time}-{s.end_time}"
            )

    bagian.append("")
    bagian.append(f"PERTANYAAN: {user_text}")
    bagian.append("JAWABAN:")
    return "\n".join(bagian)


def generate_answer(prompt: str) -> str:
    """Panggil Groq. Melempar RuntimeError kalau gagal, biar penanganannya di router."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY kosong")

    try:
        resp = httpx.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            },
            timeout=GROQ_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        raise RuntimeError(f"Groq gagal: {e}") from e
```

- [ ] **Step 4: Jalankan test, pastikan LULUS**

Run: `pytest tests/test_generation.py -v`
Expected: PASS, 7 test lulus

- [ ] **Step 5: Commit**

```bash
git add app/assistant/generation.py tests/test_generation.py
git commit -m "feat(assistant): prompt builder + Groq dari sisi server"
```

---

### Task 7: Endpoint dan perakitan di `main.py`

**Files:**
- Create: `app/assistant/router.py`
- Create: `tests/test_router.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: semua modul dari Task 1-6
- Produces: `router` (APIRouter), `POST /api/assistant/query`

- [ ] **Step 1: Tulis test yang gagal**

Buat `tests/test_router.py`:

```python
"""Test endpoint dengan retrieval dan Groq di-stub.

Yang diuji di sini perakitan dan bentuk response, bukan kualitas jawaban LLM.

TestClient SENGAJA dipakai tanpa `with`: bentuk context manager akan menjalankan
lifespan, yang membuka pool DB sungguhan dan mengunduh model 0.22 GB. Test unit
tidak boleh butuh keduanya. Pool diganti stub lewat app.state.pool.
"""

import contextlib

import pytest
from fastapi.testclient import TestClient

from app.assistant import router as router_mod
from app.assistant.models import RetrievedChunk, ScheduleRow


class _FakePool:
    """Cukup memenuhi `with pool.connection() as conn`. Isinya tidak dipakai karena
    search_chunks/find_schedules di-stub di tiap test."""

    @contextlib.contextmanager
    def connection(self):
        yield None


@pytest.fixture
def client(monkeypatch):
    from app import main

    main.app.state.pool = _FakePool()
    monkeypatch.setattr(router_mod, "generate_answer", lambda prompt: "Jawaban uji.")
    return TestClient(main.app)


def _chunk(poi_id=None, poi_name=None, is_simulated=True):
    return RetrievedChunk(
        content="Farmasi buka 07.00-21.00.", title="Layanan Farmasi",
        doc_type="layanan", poi_unity_id=poi_id, poi_name=poi_name,
        floor="Lantai 1", is_simulated=is_simulated, score=0.8,
    )


def test_response_memuat_semua_field_kontrak(client, monkeypatch):
    monkeypatch.setattr(router_mod, "search_chunks", lambda *a, **k: [_chunk()])
    monkeypatch.setattr(router_mod, "find_schedules", lambda *a, **k: [])
    r = client.post("/api/assistant/query", json={"user_text": "farmasi buka jam berapa"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"answer", "sources", "poi_id", "poi_name",
                         "contains_simulated_data"}


def test_poi_id_diambil_dari_metadata_chunk(client, monkeypatch):
    monkeypatch.setattr(
        router_mod, "search_chunks",
        lambda *a, **k: [_chunk(poi_id="guid-farmasi", poi_name="Farmasi")],
    )
    monkeypatch.setattr(router_mod, "find_schedules", lambda *a, **k: [])
    body = client.post("/api/assistant/query", json={"user_text": "farmasi"}).json()
    assert body["poi_id"] == "guid-farmasi"
    assert body["poi_name"] == "Farmasi"


def test_flag_simulasi_menyala_kalau_ada_sumber_simulasi(client, monkeypatch):
    monkeypatch.setattr(router_mod, "search_chunks", lambda *a, **k: [_chunk()])
    monkeypatch.setattr(router_mod, "find_schedules", lambda *a, **k: [])
    body = client.post("/api/assistant/query", json={"user_text": "farmasi"}).json()
    assert body["contains_simulated_data"] is True


def test_flag_simulasi_mati_kalau_semua_sumber_asli(client, monkeypatch):
    monkeypatch.setattr(
        router_mod, "search_chunks", lambda *a, **k: [_chunk(is_simulated=False)]
    )
    monkeypatch.setattr(router_mod, "find_schedules", lambda *a, **k: [])
    body = client.post("/api/assistant/query", json={"user_text": "farmasi"}).json()
    assert body["contains_simulated_data"] is False


def test_tanpa_hasil_retrieval_menjawab_jujur_tanpa_memanggil_llm(client, monkeypatch):
    monkeypatch.setattr(router_mod, "search_chunks", lambda *a, **k: [])
    monkeypatch.setattr(router_mod, "find_schedules", lambda *a, **k: [])

    def _jangan_dipanggil(prompt):
        raise AssertionError("LLM tidak boleh dipanggil tanpa konteks")

    monkeypatch.setattr(router_mod, "generate_answer", _jangan_dipanggil)
    body = client.post("/api/assistant/query", json={"user_text": "tiket pesawat"}).json()
    assert body["sources"] == []
    assert body["poi_id"] is None
    assert "tidak" in body["answer"].lower()


def test_groq_gagal_membalas_503(client, monkeypatch):
    monkeypatch.setattr(router_mod, "search_chunks", lambda *a, **k: [_chunk()])
    monkeypatch.setattr(router_mod, "find_schedules", lambda *a, **k: [])

    def _gagal(prompt):
        raise RuntimeError("Groq gagal: timeout")

    monkeypatch.setattr(router_mod, "generate_answer", _gagal)
    r = client.post("/api/assistant/query", json={"user_text": "farmasi"})
    assert r.status_code == 503


def test_user_text_kosong_ditolak_422(client):
    r = client.post("/api/assistant/query", json={"user_text": ""})
    assert r.status_code == 422


def test_field_lantai_opsional(client, monkeypatch):
    monkeypatch.setattr(router_mod, "search_chunks", lambda *a, **k: [_chunk()])
    monkeypatch.setattr(router_mod, "find_schedules", lambda *a, **k: [])
    r = client.post("/api/assistant/query", json={"user_text": "farmasi"})
    assert r.status_code == 200
```

- [ ] **Step 2: Jalankan test, pastikan GAGAL**

Run: `pytest tests/test_router.py -v`
Expected: FAIL dengan `ModuleNotFoundError: No module named 'app.assistant.router'`

- [ ] **Step 3: Tulis router**

Buat `app/assistant/router.py`:

```python
"""Endpoint POST /api/assistant/query."""

from fastapi import APIRouter, HTTPException, Request

from app.assistant.generation import NO_CONTEXT_ANSWER, build_prompt, generate_answer
from app.assistant.models import (
    AssistantQueryRequest,
    AssistantQueryResponse,
    Source,
    derive_poi,
)
from app.assistant.retrieval import find_schedules, search_chunks

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.post("/query", response_model=AssistantQueryResponse)
def query(payload: AssistantQueryRequest, request: Request) -> AssistantQueryResponse:
    pool = request.app.state.pool

    with pool.connection() as conn:
        chunks = search_chunks(
            conn, payload.user_text, payload.current_floor, payload.building
        )
        poi_id, poi_name = derive_poi(chunks)
        schedules = find_schedules(conn, payload.user_text, poi_id)

    # Tanpa konteks, JANGAN teruskan ke LLM: itu mengundang jawaban karangan,
    # dan di konteks rumah sakit jawaban karangan berbahaya (spec section 8.3).
    if not chunks and not schedules:
        return AssistantQueryResponse(
            answer=NO_CONTEXT_ANSWER,
            sources=[],
            poi_id=None,
            poi_name=None,
            contains_simulated_data=False,
        )

    try:
        answer = generate_answer(build_prompt(payload.user_text, chunks, schedules))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    sources = [
        Source(title=c.title, doc_type=c.doc_type, is_simulated=c.is_simulated)
        for c in chunks
    ]
    if schedules:
        sources.append(
            Source(
                title="Jadwal praktek",
                doc_type="schedule",
                is_simulated=any(s.is_simulated for s in schedules),
            )
        )

    return AssistantQueryResponse(
        answer=answer,
        sources=sources,
        poi_id=poi_id,
        poi_name=poi_name,
        contains_simulated_data=any(s.is_simulated for s in sources),
    )
```

- [ ] **Step 4: Rakit di `app/main.py`**

Di `app/main.py`, tambahkan import di bagian atas berkas:

```python
from app.assistant import embedding
from app.assistant.router import router as assistant_router
```

Di dalam fungsi `lifespan`, tepat setelah baris `app.state.pool.open()`, tambahkan:

```python
    # Gagal berisik di startup, bukan diam-diam jalan lalu error saat request
    # pertama masuk (spec section 8.3).
    if not os.environ.get("GROQ_API_KEY", ""):
        raise RuntimeError(
            "GROQ_API_KEY kosong. Endpoint /api/assistant/query tidak bisa berfungsi."
        )

    # Muat model embedding sekali di startup, bukan per-request. Tanpa ini request
    # pertama akan lambat seperti gejala pre-warm Ollama di repo Unity. Kalau bobot
    # model gagal dimuat, exception di sini menggagalkan startup — itu memang yang
    # diinginkan, daripada service hidup tanpa kemampuan retrieval.
    embedding.load_model()
```

`os` sudah di-import di `app/main.py`, tidak perlu ditambah.

Setelah blok `app.add_middleware(...)`, tambahkan:

```python
app.include_router(assistant_router)
```

Terakhir, tambahkan `"POST"` ke `allow_methods` di CORS middleware supaya WebView bisa memanggil endpoint ini:

```python
    allow_methods=["GET", "PUT", "POST"],
```

- [ ] **Step 5: Jalankan seluruh test, pastikan LULUS**

Run: `pytest -v`
Expected: PASS semua (test yang butuh DB di-skip kalau `TEST_DATABASE_URL` kosong)

- [ ] **Step 6: Commit**

```bash
git add app/assistant/router.py app/main.py tests/test_router.py
git commit -m "feat(assistant): endpoint POST /api/assistant/query + muat model di startup"
```

---

### Task 8: Set evaluasi, penyetelan ambang, dan dokumentasi

**Files:**
- Create: `data/eval_retrieval.json`
- Create: `scripts/eval_retrieval.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `retrieval.search_chunks()`
- Produces: laporan recall@3 di stdout

- [ ] **Step 1: Tulis set evaluasi**

Buat `data/eval_retrieval.json` (18 pasangan):

```json
[
  {"q": "mau nebus resep obat di mana", "expect": "Layanan Farmasi"},
  {"q": "apotek buka jam berapa", "expect": "Layanan Farmasi"},
  {"q": "syarat daftar pakai bpjs apa saja", "expect": "Alur Pendaftaran BPJS Rawat Jalan"},
  {"q": "rujukan bpjs berlaku berapa lama", "expect": "Alur Pendaftaran BPJS Rawat Jalan"},
  {"q": "kalau kecelakaan harus ke mana", "expect": "Alur Pasien IGD"},
  {"q": "igd buka 24 jam tidak", "expect": "Alur Pasien IGD"},
  {"q": "saya pasien umum cara daftarnya gimana", "expect": "Alur Rawat Jalan Pasien Umum"},
  {"q": "bayar di mana setelah periksa", "expect": "Alur Rawat Jalan Pasien Umum"},
  {"q": "mau rontgen prosedurnya bagaimana", "expect": "Layanan Radiologi"},
  {"q": "usg perut perlu puasa tidak", "expect": "Layanan Radiologi"},
  {"q": "cek darah jam berapa", "expect": "Layanan Laboratorium"},
  {"q": "poli anak ada di lantai berapa", "expect": "Poli Anak"},
  {"q": "imunisasi anak di mana", "expect": "Poli Anak"},
  {"q": "konsultasi diabetes ke poli apa", "expect": "Poli Penyakit Dalam"},
  {"q": "mau sholat di mana", "expect": "Musholla dan Fasilitas Ibadah"},
  {"q": "bisa berobat tanpa rujukan tidak", "expect": "FAQ: Berobat tanpa surat rujukan"},
  {"q": "jam besuk kapan", "expect": "FAQ: Jam besuk pasien rawat inap"},
  {"q": "cara minta salinan rekam medis", "expect": "FAQ: Cara mendapatkan salinan rekam medis"}
]
```

- [ ] **Step 2: Tulis script evaluasi**

Buat `scripts/eval_retrieval.py`:

```python
"""Ukur kualitas retrieval: berapa persen pertanyaan yang chunk benarnya masuk 3 besar.

Ini yang membuat "RAG-nya bagus" jadi angka, bukan perasaan. Dipakai juga untuk
menyetel MIN_SCORE dan FLOOR_BONUS di app/assistant/retrieval.py.

CATATAN JUJUR: evaluasi ini berjalan di atas corpus SIMULASI. Yang diukur adalah
kualitas mekanisme retrieval, BUKAN kesiapan sistem terhadap pertanyaan pasien
sungguhan. Sebutkan batasan ini kalau angkanya dilaporkan.

Pakai:
    export DATABASE_URL=...
    python -m scripts.eval_retrieval
"""

import json
import os
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app.assistant import embedding, retrieval

EVAL_PATH = Path(__file__).resolve().parent.parent / "data" / "eval_retrieval.json"
TOP_K = 3


def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL kosong.", file=sys.stderr)
        return 1

    cases = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    embedding.load_model()

    lolos, gagal = 0, []
    with psycopg.connect(url, row_factory=dict_row) as conn:
        for case in cases:
            hasil = retrieval.search_chunks(conn, case["q"], None, None, limit=TOP_K)
            judul = [c.title for c in hasil]
            if case["expect"] in judul:
                lolos += 1
            else:
                gagal.append((case["q"], case["expect"], judul))

    total = len(cases)
    print(f"\nrecall@{TOP_K}: {lolos}/{total} = {lolos / total:.1%}")
    print(f"MIN_SCORE={retrieval.MIN_SCORE}  FLOOR_BONUS={retrieval.FLOOR_BONUS}")

    if gagal:
        print(f"\n{len(gagal)} pertanyaan meleset:")
        for q, expect, dapat in gagal:
            print(f"  - \"{q}\"\n      harusnya: {expect}\n      dapatnya: {dapat}")

    print("\nCATATAN: angka ini diukur di atas corpus SIMULASI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Jalankan evaluasi dan catat angkanya**

```bash
export DATABASE_URL="$TEST_DATABASE_URL"
python -m scripts.ingest_corpus
python -m scripts.eval_retrieval
```

Expected: tercetak angka `recall@3`. **Target minimal 80% (15 dari 18).**

- [ ] **Step 4: Setel ambang kalau target belum tercapai**

Kalau recall@3 di bawah 80%, setel `MIN_SCORE` di `app/assistant/retrieval.py` lalu jalankan ulang `python -m scripts.eval_retrieval`. Turunkan `MIN_SCORE` kalau banyak pertanyaan tidak dapat hasil sama sekali; naikkan kalau banyak hasil tidak relevan ikut terbawa.

Catat nilai akhir yang dipakai beserta angka recall@3-nya di pesan commit.

- [ ] **Step 5: Dokumentasikan di README**

Tambahkan bagian berikut di `README.md`, setelah bagian `## Endpoints`:

```markdown
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
```

- [ ] **Step 6: Jalankan seluruh test terakhir kali**

Run: `pytest -v`
Expected: PASS semua

- [ ] **Step 7: Commit**

```bash
git add data/eval_retrieval.json scripts/eval_retrieval.py README.md app/assistant/retrieval.py
git commit -m "feat(assistant): set evaluasi retrieval + dokumentasi (recall@3 = <isi angkanya>)"
```

---

## Setelah Semua Task Selesai

Tiga hal yang belum tercakup plan ini dan perlu keputusan pemilik project:

1. **Menerapkan skema ke Supabase produksi.** `CREATE EXTENSION vector;` belum pernah dijalankan di sana (terverifikasi 2026-08-20: tersedia v0.8.2, `installed_version: null`). Ini menyentuh DB produksi, jadi butuh persetujuan eksplisit.
2. **Mengisi `GROQ_API_KEY` di Railway** dan mengukur pemakaian memori sesungguhnya setelah model dimuat.
3. **Keputusan UI**: di mana jawaban ini muncul (WebView pra-AR, panel Unity, atau tombol mic yang sudah ada). Sengaja di luar lingkup, dibahas setelah mekanisme retrieval terbukti jalan.
