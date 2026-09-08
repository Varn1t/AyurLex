"""FastAPI server for the IP-SAKTI chat UI.

Sessions are in-process and ephemeral by design (KAVACH): a formulation
described in chat is never written to disk here. Restarting the server
forgets everything, which is the correct default for a product whose first
industry objection is "why would I upload my proprietary formulation?".
"""
from __future__ import annotations

import sys
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.schema import Severity  # noqa: E402
from rag.answer import pick_backend  # noqa: E402
from rag.chat import Session, respond  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bring Ollama up and page the model in before the first question.

    A local model pays roughly half a minute to load on its first call. Paying
    that during a demo's opening question is the difference between "thinking"
    and "broken", so it is paid at boot, on a thread, while the page still
    serves.
    """
    import threading

    def warm() -> None:
        try:
            from rag.llm import Ollama

            client = Ollama()
            took = client.warm()
            print(f"  ollama ready: {client.model} (warmed in {took:.0f}s)")
        except Exception as e:                    # environment dependent
            print(f"  ollama unavailable ({e}) — falling back to extractive")

    threading.Thread(target=warm, daemon=True).start()
    yield


app = FastAPI(title="IP-SAKTI Sahayak", lifespan=lifespan)

SESSIONS: dict[str, Session] = {}
UI = ROOT / "web" / "chat.html"


class Ask(BaseModel):
    message: str
    session_id: str | None = None
    as_of: str | None = None


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return UI.read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> dict:
    from rag.llm import ensure
    from rag.retriever import load_retriever
    from sutra.loader import load_rules

    r = load_retriever()
    rules = load_rules()
    st = ensure(autostart=False)
    return {
        "provisions": len(r.corpus.records),
        "rules": len(rules),
        "verified": sum(1 for x in rules if x.verification.value == "VERIFIED"),
        "backend": pick_backend().name,
        # Everything runs locally either way -- Ollama is on this machine.
        "offline": True,
        "ollama": {
            "running": st.running,
            "model": st.model,
            "models": list(st.models),
            "detail": st.detail,
        },
    }


@app.post("/api/chat/stream")
def chat_stream(req: Ask) -> StreamingResponse:
    """Tokens as they are generated, then the verified answer.

    See rag/stream.py for why citations are sent before any prose.
    """
    from rag.stream import events

    sid = req.session_id or uuid.uuid4().hex[:12]
    session = SESSIONS.get(sid)
    if session is None:
        session = Session(as_of=date.fromisoformat(req.as_of) if req.as_of
                          else date.today())
        SESSIONS[sid] = session

    return StreamingResponse(
        events(req.message, session, sid),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/chat")
def chat(req: Ask) -> JSONResponse:
    sid = req.session_id or uuid.uuid4().hex[:12]
    session = SESSIONS.get(sid)
    if session is None:
        session = Session(as_of=date.fromisoformat(req.as_of) if req.as_of
                          else date.today())
        SESSIONS[sid] = session

    reply = respond(req.message, session)

    payload: dict = {
        "session_id": sid,
        "intent": reply.intent,
        "text": reply.text,
        "citations": [],
        "abstained": False,
        "groundedness": None,
        "backend": "",
        "concept": "",
        "taxa": [],
        "findings": [],
    }

    if reply.answer:
        a = reply.answer
        payload.update(
            guard=a.guard,
            abstained=a.abstained,
            groundedness=a.groundedness,
            backend=a.backend,
            concept=a.concept_label,
            taxa=[{"input": i, "taxon": t} for i, t in a.taxa],
            citations=[
                {
                    "corpus_id": c.corpus_id,
                    "instrument": c.instrument,
                    "provision": c.provision,
                    "hierarchy": c.hierarchy_path,
                    "pdf": c.source_pdf,
                    "page": c.page,
                    "rank": c.authority_rank,
                    "quote": c.quote,
                    "jurisdiction": c.jurisdiction,
                    "force": c.force_note,
                }
                for c in a.citations
            ],
        )

    if getattr(reply, "classification", None) is not None:
        from vargikarana.classify import classification_payload

        payload["classification"] = classification_payload(reply.classification)

    if reply.compile_result is not None:
        cb = reply.compile_result.cbom
        payload["findings"] = [
            {
                "severity": f.severity.value,
                "lane": f.lane,
                "rule_id": f.rule_id,
                "instrument": f.instrument,
                "provision": f.provision,
                "statement": f.statement,
                "groundedness": f.groundedness,
                "citations": [
                    {
                        "corpus_id": c.corpus_id,
                        "instrument": c.instrument,
                        "provision": c.provision,
                        "hierarchy": c.hierarchy_path,
                        "pdf": c.source_pdf,
                        "page": c.page,
                        "quote": c.quote,
                    }
                    for c in f.citations
                ],
                "autofix": [
                    {"id": x.id, "description": x.description,
                     "available": x.available, "why": x.unavailable_reason}
                    for x in f.autofix
                ],
            }
            for f in cb.findings
        ]
        payload["resolution"] = cb.resolution_log
        payload["obligations"] = [
            {"provision": o.provision, "duty": o.duty,
             "discharged_by": o.discharged_by, "when": o.when}
            for o in cb.obligations
        ]
        payload["matrix"] = [
            {"jurisdiction": r.jurisdiction.value, "status": r.status.value,
             "patentability": r.patentability, "next_action": r.next_action,
             "citations": r.citation_count}
            for r in cb.jurisdiction_matrix
        ]
        payload["summary"] = {
            "blockers": sum(1 for f in cb.findings
                            if f.severity is Severity.BLOCKER),
            "warnings": sum(1 for f in cb.findings
                            if f.severity is Severity.WARNING),
            "opportunities": sum(1 for f in cb.findings
                                 if f.severity is Severity.OPPORTUNITY),
            "obligations": len(cb.obligations),
            "groundedness": cb.groundedness_score,
            "digest": cb.digest()[:16],
        }

    return JSONResponse(payload)


@app.get("/api/provision/{corpus_id:path}")
def provision(corpus_id: str) -> JSONResponse:
    """Click-to-source: the full provision behind any citation."""
    from samhita.index import load_corpus

    c = load_corpus()
    if not c.has(corpus_id):
        return JSONResponse({"error": "not found"}, status_code=404)
    r = c.get(corpus_id)
    return JSONResponse({
        "corpus_id": r["corpus_id"],
        "act_title": r["act_title"],
        "section": r["section"],
        "heading": r["heading"],
        "hierarchy": r["hierarchy_path"],
        "text": r["text"],
        "pdf": r["source_pdf"],
        "page_start": r["page_start"],
        "page_end": r["page_end"],
        "retrieved_on": r.get("retrieved_on", ""),
        "authority_rank": r["authority_rank"],
        "amendment_notes": r.get("amendment_notes", []),
    })


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
