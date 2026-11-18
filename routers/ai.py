from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from config import settings
from services.ai_service import answer_patient_question, parse_voice_memory_proposal
from services.retrieval_service import retrieve_relevant_context

router = APIRouter(tags=["AI Companion, RAG Search & Backend Provider Config"])


@router.get("/api/knowledge-search")
def unified_knowledge_search(q: Optional[str] = Query(default="")):
    ctx = retrieve_relevant_context(q or "", max_per_table=10)
    m = ctx["matched"]
    total = sum(len(v) for v in m.values())
    return {
        "success": True,
        "query": q,
        "totalMatches": total,
        "sources": ctx["sources"],
        "ragContextPrompt": ctx["minimalContextPrompt"],
        "results": {
            "people": m["people"],
            "places": m["places"],
            "memories": m["memories"],
            "environmentGuides": m["environmentGuides"],
            "activities": m["activities"],
            "routines": m["routines"],
            "medications": m["medications"],
        },
    }


@router.post("/api/ai-assistant")
def handle_ai_assistant(body: dict):
    mode = body.get("mode", "ask")
    prompt = (body.get("prompt") or "").strip()
    language = body.get("language", "en-IN")
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt text is required")

    if mode == "parse":
        proposal = parse_voice_memory_proposal(prompt)
        return {"success": True, "mode": "parse", "proposal": proposal}

    result = answer_patient_question(prompt, language=language)
    return result


@router.get("/api/ai/config")
def get_public_ai_configuration():
    """Returns provider settings WITHOUT exposing any API keys."""
    return {"success": True, "config": settings.get_public_ai_config()}


@router.patch("/api/ai/config")
def update_backend_ai_configuration(body: dict):
    """Updates provider settings on the backend. Never echoes back the raw API key."""
    settings.update_settings(
        provider=body.get("provider"),
        model=body.get("model"),
        temperature=body.get("temperature"),
        max_tokens=body.get("maxTokens"),
        api_key=body.get("apiKey"),
    )
    return {"success": True, "config": settings.get_public_ai_config()}
