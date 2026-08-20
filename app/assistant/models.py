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
