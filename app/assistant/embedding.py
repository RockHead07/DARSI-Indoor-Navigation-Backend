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
