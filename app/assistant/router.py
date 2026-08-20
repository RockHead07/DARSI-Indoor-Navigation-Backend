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
