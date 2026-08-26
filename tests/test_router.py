"""Test endpoint dengan retrieval dan Groq di-stub.

Yang diuji di sini perakitan dan bentuk response, bukan kualitas jawaban LLM.

TestClient SENGAJA dipakai tanpa with: bentuk context manager akan menjalankan
lifespan, yang membuka pool DB sungguhan dan mengunduh model 0.22 GB. Test unit
tidak boleh butuh keduanya. Pool diganti stub lewat app.state.pool.
"""

import contextlib

import pytest
from fastapi.testclient import TestClient

from app.assistant import router as router_mod
from app.assistant.models import RetrievedChunk, ScheduleRow


class _FakePool:
    """Cukup memenuhi with pool.connection() as conn. Isinya tidak dipakai karena
    search_chunks/find_schedules di-stub di tiap test."""

    @contextlib.contextmanager
    def connection(self):
        yield None


@pytest.fixture
def client(monkeypatch):
    from app import main

    main.app.state.pool = _FakePool()
    monkeypatch.setattr(router_mod, "generate_answer", lambda prompt: ("Jawaban uji.", "bifrost"))
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
                         "contains_simulated_data", "provider", "refused"}


def test_poi_id_diambil_dari_metadata_chunk(client, monkeypatch):
    monkeypatch.setattr(
        router_mod, "search_chunks",
        lambda *a, **k: [_chunk(poi_id="guid-farmasi", poi_name="Farmasi")],
    )
    monkeypatch.setattr(router_mod, "find_schedules", lambda *a, **k: [])
    body = client.post("/api/assistant/query", json={"user_text": "farmasi"}).json()
    assert body["poi_id"] == "guid-farmasi"
    assert body["poi_name"] == "Farmasi"


def test_penolakan_membuang_poi_dan_penandanya_tidak_bocor(client, monkeypatch):
    """Kasus terukur di produksi: "prakiraan cuaca" mengembalikan poi IGD."""
    monkeypatch.setattr(
        router_mod, "search_chunks",
        lambda *a, **k: [_chunk(poi_id="guid-igd", poi_name="IGD")],
    )
    monkeypatch.setattr(router_mod, "find_schedules", lambda *a, **k: [])
    monkeypatch.setattr(
        router_mod, "generate_answer",
        lambda prompt: ("Maaf, saya hanya melayani informasi RS. [TOLAK]", "bifrost"),
    )
    body = client.post("/api/assistant/query", json={"user_text": "cuaca besok"}).json()
    assert body["refused"] is True
    assert body["poi_id"] is None and body["poi_name"] is None
    assert "TOLAK" not in body["answer"]


def test_jawaban_sah_tidak_ikut_terbuang(client, monkeypatch):
    """Arah yang paling berbahaya: penanda salah menyala akan mematikan navigasi
    yang benar. Jawaban tanpa penanda WAJIB mempertahankan poi-nya."""
    monkeypatch.setattr(
        router_mod, "search_chunks",
        lambda *a, **k: [_chunk(poi_id="guid-igd", poi_name="IGD")],
    )
    monkeypatch.setattr(router_mod, "find_schedules", lambda *a, **k: [])
    monkeypatch.setattr(
        router_mod, "generate_answer",
        lambda prompt: ("Segera menuju IGD di Lantai 1.", "bifrost"),
    )
    body = client.post("/api/assistant/query", json={"user_text": "saya berdarah"}).json()
    assert body["refused"] is False
    assert body["poi_id"] == "guid-igd"


def test_tanpa_konteks_ditandai_menolak(client, monkeypatch):
    monkeypatch.setattr(router_mod, "search_chunks", lambda *a, **k: [])
    monkeypatch.setattr(router_mod, "find_schedules", lambda *a, **k: [])
    body = client.post("/api/assistant/query", json={"user_text": "tiket pesawat"}).json()
    assert body["refused"] is True


def test_provider_diteruskan_ke_response(client, monkeypatch):
    monkeypatch.setattr(router_mod, "search_chunks", lambda *a, **k: [_chunk()])
    monkeypatch.setattr(router_mod, "find_schedules", lambda *a, **k: [])
    monkeypatch.setattr(router_mod, "generate_answer", lambda prompt: ("Jawaban Groq.", "groq"))
    body = client.post("/api/assistant/query", json={"user_text": "farmasi"}).json()
    assert body["provider"] == "groq"


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
    assert body["provider"] is None
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
