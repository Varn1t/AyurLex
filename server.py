"""FastAPI server for the AyurLex chat UI.

Sessions are in-process and ephemeral by design (the no-disk rule): a formulation
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


app = FastAPI(title="AyurLex", lifespan=lifespan)

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
    from compliance.loader import load_rules

    from rag.bhashini import status as bhashini_status

    r = load_retriever()
    rules = load_rules()
    st = ensure(autostart=False)
    bh = bhashini_status()
    return {
        "provisions": len(r.corpus.records),
        "rules": len(rules),
        "verified": sum(1 for x in rules if x.verification.value == "VERIFIED"),
        "backend": pick_backend().name,
        # Generation, retrieval, the rules and the compile are all on this
        # machine. Bhashini is the single exception and it is off unless
        # someone configured it, so `offline` reports the truth rather than
        # the intention -- a user must be able to see that their question can
        # leave the machine before they type one.
        "offline": not bh.enabled,
        "ollama": {
            "running": st.running,
            "model": st.model,
            "models": list(st.models),
            "detail": st.detail,
        },
        "bhashini": {
            "configured": bh.configured,
            "enabled": bh.enabled,
            "pipeline": bh.pipeline_id,
            "detail": bh.detail,
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
        from classification.classify import classification_payload

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


@app.get("/api/graph/stats")
def graph_stats() -> JSONResponse:
    """What the knowledge graph actually contains, and anything wrong with it.

    `problems` is served rather than hidden: a curated cross-instrument link
    whose anchor no longer matches the primary source is a defect, and a
    defect a reviewer cannot see is worse than one they can.
    """
    from graph.graph import load_graph

    return JSONResponse(load_graph().stats())


@app.get("/api/graph/path")
def graph_path(src: str, dst: str, max_hops: int = 6) -> JSONResponse:
    """Walk between two nodes. Deterministic; no model in this path."""
    from rag.stream import walk_payload
    from graph.graph import load_graph

    g = load_graph()
    a = g.resolve(src)
    b = g.resolve(dst)
    if not a or not b:
        missing = src if not a else dst
        return JSONResponse(
            {"error": f"{missing!r} does not resolve to a node in the graph"},
            status_code=404)
    walk = g.path(a[0].id, b[0].id, max_hops=max_hops)
    if walk is None:
        return JSONResponse({
            "found": False,
            "from": a[0].label, "to": b[0].label,
            "explain": [f"No path between {a[0].label} and {b[0].label} within "
                        f"{max_hops} hops. The corpus asserts no relationship "
                        f"between them."],
        })
    return JSONResponse({
        "found": True, "hops": walk.length,
        "explain": g.explain(walk),
        "walk": walk_payload(walk),
    })


@app.get("/api/graph/neighbours")
def graph_neighbours(node: str, hops: int = 1) -> JSONResponse:
    from graph.graph import load_graph

    g = load_graph()
    found = g.resolve(node)
    if not found:
        return JSONResponse({"error": f"{node!r} is not a node"},
                            status_code=404)
    nodes, edges = g.subgraph(found[0].id, hops=hops)
    return JSONResponse({
        "node": {"id": found[0].id, "kind": found[0].kind,
                 "label": found[0].label},
        "nodes": [{"id": n.id, "kind": n.kind, "label": n.label}
                  for n in nodes],
        "edges": [{"src": e.src, "dst": e.dst, "kind": e.kind, "note": e.note}
                  for e in edges],
    })


@app.get("/api/facilitators")
def facilitators() -> JSONResponse:
    """The escalation directory, with its verification state.

    Contact details are deployment configuration and ship unset; a prototype
    must not invent an office's phone number.
    """
    from escalation.escalate import load_registry

    reg = load_registry()
    return JSONResponse({
        "routes": [{
            "id": r.id, "label": r.label, "mandate": r.mandate,
            "citation": r.citation, "pdf": r.pdf, "page": r.page,
            "background": r.background, "uncited": r.uncited_authority,
            "site": r.site, "contact": r.contact, "handles": r.handles,
            "verified": r.ok,
        } for r in reg.routes],
        "problems": reg.problems,
    })


class Escalate(BaseModel):
    session_id: str | None = None
    redact: bool = False


@app.post("/api/escalate")
def escalate(req: Escalate) -> JSONResponse:
    """Assemble the referral packet for a session.

    Nothing is sent anywhere. The packet is returned to the caller, who is the
    person whose formulation it describes.
    """
    from escalation.escalate import assess, payload as referral_payload

    session = SESSIONS.get(req.session_id or "")
    if session is None:
        return JSONResponse(
            {"error": "no such session; escalation is assembled from what a "
                      "conversation established, so there has to be one"},
            status_code=404)
    last = session.last_answer
    ref = assess(
        compile_result=session.last_compile,
        answer=last if (last is not None and last.abstained) else None,
        classification=session.last_classification,
        user_asked=True, redact=req.redact,
    )
    return JSONResponse(referral_payload(ref))


class CompileReq(BaseModel):
    formulation: dict
    session_id: str | None = None


@app.post("/api/compile")
def compile_structured(req: CompileReq) -> JSONResponse:
    """Compile a formulation entered in the form, as structured data.

    The chat path has to pull ingredients out of a sentence with a regex; the
    form already has them as fields, so they go straight to the compiler and
    nothing is guessed. Same session store, so "apply the fixes" and the
    referral packet work afterwards in chat exactly as they would there.
    """
    from pydantic import ValidationError

    from core.schema import Formulation
    from rag.chat import Turn, compile_reply
    from rag.stream import compile_payload

    try:
        f = Formulation.model_validate(req.formulation)
    except ValidationError as e:
        return JSONResponse({"error": "invalid formulation",
                             "detail": e.errors(include_url=False)},
                            status_code=422)
    if not f.ingredients:
        return JSONResponse({"error": "add at least one ingredient"},
                            status_code=422)

    sid = req.session_id or uuid.uuid4().hex[:12]
    session = SESSIONS.setdefault(sid, Session(as_of=date.today()))
    reply = compile_reply(f, session)
    session.turns.append(Turn(role="assistant", text=reply.text,
                              intent=reply.intent))
    payload = {
        "session_id": sid, "intent": reply.intent, "text": reply.text,
        "citations": [], "abstained": False, "groundedness": None,
        "backend": "rule engine · no model", "concept": "", "taxa": [],
        "findings": [],
    }
    payload.update(compile_payload(reply.compile_result))
    if getattr(reply, "classification", None) is not None:
        from classification.classify import classification_payload

        payload["classification"] = classification_payload(reply.classification)
    return JSONResponse(payload)


@app.get("/api/sources")
def sources() -> JSONResponse:
    """Every instrument in the corpus, with how much of it was extracted."""
    from sources.index import load_corpus

    acts: dict[str, dict] = {}
    for r in load_corpus().records:
        a = acts.setdefault(r["act_id"], {
            "act_id": r["act_id"], "title": r["act_title"],
            "type": r["instrument_type"], "jurisdiction": r["jurisdiction"],
            "rank": r["authority_rank"], "citable": r.get("citable", True),
            "pdf": r["source_pdf"], "provisions": 0,
        })
        a["provisions"] += 1
    return JSONResponse(sorted(acts.values(),
                               key=lambda a: (a["rank"], a["title"])))


@app.get("/api/sources/{act_id}")
def source_provisions(act_id: str) -> JSONResponse:
    """The table of contents of one instrument, in document order."""
    from sources.index import load_corpus

    rows = [{"corpus_id": r["corpus_id"], "section": r["section"],
             "heading": r["heading"], "page": r["page_start"]}
            for r in load_corpus().records if r["act_id"] == act_id]
    if not rows:
        return JSONResponse({"error": "no such instrument"}, status_code=404)
    return JSONResponse(rows)


@app.get("/api/provision/{corpus_id:path}")
def provision(corpus_id: str) -> JSONResponse:
    """Click-to-source: the full provision behind any citation."""
    from sources.index import load_corpus

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
