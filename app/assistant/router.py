import os

from fastapi import APIRouter, HTTPException, Request

from app.assistant.generation import (
    NO_CONTEXT_ANSWER,
    build_prompt,
    generate_answer,
    split_refusal,
)
from app.assistant.models import (
    AssistantQueryRequest,
    AssistantQueryResponse,
    AssistantTTSRequest,
    AssistantTTSResponse,
    KataTiming,
    Source,
    derive_poi,
)
from app.assistant.retrieval import find_schedules, search_chunks
from app.assistant.tts import DEFAULT_VOICE, STATIC_TTS_DIR, synthesize_speech

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
            refused=True,
        )

    try:
        answer, provider = generate_answer(build_prompt(payload.user_text, chunks, schedules))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    # Retrieval tetap mengembalikan chunk peringkat 1 walau jawabannya menolak,
    # jadi poi_id ikut terisi untuk pertanyaan yang sama sekali di luar cakupan
    # (terukur di produksi: "prakiraan cuaca" -> IGD, "harga tiket pesawat" ->
    # Resepsionis). Jawaban adalah pemilik sah maksud pengguna, bukan peringkat
    # kemiripan, jadi kalau jawabannya menolak, poi-nya dibuang.
    answer, refused = split_refusal(answer)
    if refused:
        poi_id = poi_name = None

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
        provider=provider,
        refused=refused,
    )


@router.post("/tts", response_model=AssistantTTSResponse)
async def tts(payload: AssistantTTSRequest, request: Request) -> AssistantTTSResponse:
    """Endpoint sintesis suara TTS (ADR-033).

    Menerima teks dan voice opsional (kosong = DEFAULT_VOICE). Mengembalikan
    audio_url, engine_used ('edge-tts' atau 'sherpa-onnx'), dan words berisi batas
    waktu per kata untuk lip-sync (Amandemen 033-B).

    words KOSONG saat engine_used == 'sherpa-onnx' -- itu kondisi normal, bukan error.
    """
    try:
        filename, engine_used, words = await synthesize_speech(
            text=payload.text,
            voice=payload.voice or DEFAULT_VOICE,
            output_dir=STATIC_TTS_DIR,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    base = os.environ.get("TTS_BASE_URL", "").rstrip("/") or str(request.base_url).rstrip("/")
    audio_url = f"{base}/static/tts/{filename}"

    return AssistantTTSResponse(
        audio_url=audio_url,
        engine_used=engine_used,
        words=[KataTiming(**w) for w in words],
    )

