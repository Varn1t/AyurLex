"""Server-sent event stream for chat.

A local model on CPU takes tens of seconds to write an answer. Ninety seconds
of blank screen reads as broken, so the answer streams. But streaming a draft
conflicts with a gate that needs the whole text before it can judge it, and the
resolution matters: we never show an unverified sentence AS the answer.

The order of events is the design:

  citations  -- sent FIRST, before a single word of prose. The user can open
                the provision and read the authority while the model is still
                writing about it. If the model then says something the gate
                rejects, the authority was never in doubt.
  token      -- the draft, arriving live. Labelled as a draft in the UI.
  final      -- the verified text. The UI replaces the draft with this, and
                shows what was dropped and why.

If the whole draft fails the gate, `final` carries the extractive answer
instead: quotation of the retrieved provision. Degrading to something true and
duller beats shipping something fluent and unsupported.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Iterator


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def citation_payload(res) -> list[dict]:
    from rag.answer import to_citation

    hits = (res.hits[:3] if res.background_only
            else [h for h in res.hits[:3] if h.record["authority_rank"] < 6])
    out = []
    for h in hits:
        c = to_citation(h)
        out.append({
            "corpus_id": c.corpus_id, "instrument": c.instrument,
            "provision": c.provision, "hierarchy": c.hierarchy_path,
            "pdf": c.source_pdf, "page": c.page, "rank": c.authority_rank,
            "quote": c.quote, "jurisdiction": c.jurisdiction,
            "force": c.force_note,
        })
    return out


def events(message: str, session, sid: str) -> Iterator[str]:
    from core.language import detect
    from rag.answer import (
        NUM_PREDICT,
        OLLAMA_SYSTEM,
        POLARITY_GUARD_REASON,
        ExtractiveAnswerer,
        OllamaAnswerer,
        abstention_text,
        build_prompt,
        dedupe_sentences,
        localise,
        trim_incomplete,
        turns_on_polarity,
        verify_against_spans,
    )
    from rag.chat import Turn, classify, respond
    from rag.retriever import load_retriever

    yield sse("start", {"session_id": sid})

    lower = message.strip().lower()
    intent = classify(message, session)
    is_fix = lower.startswith(("apply the fix", "apply fixes", "run the fix"))

    # Classification is deterministic too, and a bare yes/no answering the
    # clarifying question just asked must reach the classifier rather than the
    # retriever -- "no" retrieves nothing and would abstain.
    from rag.chat import CLASSIFY_HINT, answer_to_pending

    is_classify = bool(CLASSIFY_HINT.search(message)) or bool(
        session.pending_fact and answer_to_pending(message) is not None)

    # A formulation compiles rather than streams: the answer is a set of
    # findings from the rule engine, produced in milliseconds, so there is
    # nothing to stream and everything to send at once.
    if intent == "COMPILE" or is_fix or is_classify:
        reply = respond(message, session)
        payload = {
            "session_id": sid, "intent": reply.intent, "text": reply.text,
            "citations": [], "abstained": False, "groundedness": None,
            "backend": ("vargikarana classifier (deterministic)"
                        if reply.intent == "CLASSIFY"
                        else "sutra rule engine (deterministic)"),
            "concept": "", "taxa": [], "findings": [],
        }
        if reply.compile_result is not None:
            payload.update(compile_payload(reply.compile_result))
        if getattr(reply, "classification", None) is not None:
            from vargikarana.classify import classification_payload

            payload["classification"] = classification_payload(
                reply.classification)
        yield sse("final", payload)
        return

    yield sse("status", {"stage": "retrieving"})
    res = load_retriever().search(message, k=6, as_of=session.as_of,
                                  citable_only=True)

    yield sse("citations", {
        "citations": citation_payload(res),
        "layer": res.layer,
        "concept": res.concepts[0].concept.label if res.concepts else "",
        "background": res.background_only,
        "translated": res.translated_query,
        "taxa": [{"input": i, "taxon": t} for i, t in res.taxa_expansions],
    })

    lang = detect(message)

    if res.is_weak:
        from core.localise import t as localised

        reason = res.out_of_corpus or localised(lang.code, "why_weak")
        yield sse("final", {
            "session_id": sid, "intent": intent,
            "text": abstention_text(lang, reason),
            "abstained": True, "citations": [], "groundedness": None,
            "backend": "", "concept": "", "taxa": [], "findings": [],
            "language": lang.code, "language_name": lang.name,
        })
        return

    # A question whose entire answer is a polarity ("do I need approval?") does
    # not reach the model at all -- the citation gate cannot check polarity, and
    # the local model inverts it. See POLARITY_GUARD_REASON in rag/answer.py.
    guard = POLARITY_GUARD_REASON if turns_on_polarity(message) else ""
    if guard:
        yield sse("status", {"stage": "polarity-guard", "detail": guard})

    try:
        backend = OllamaAnswerer()
    except Exception as e:
        backend = None
        yield sse("status", {"stage": "llm-unavailable", "detail": str(e)})

    draft = ""
    if backend is not None and not guard:
        yield sse("status", {"stage": "drafting", "model": backend.client.model,
                             "language": lang.name})
        try:
            for tok in backend.client.stream(
                    build_prompt(message, res, lang), OLLAMA_SYSTEM,
                    num_predict=NUM_PREDICT):
                draft += tok
                yield sse("token", {"t": tok})
        except Exception as e:
            yield sse("status", {"stage": "llm-failed", "detail": str(e)})
            draft = ""

    # The tail of a draft that hit the token cap is a half-written clause.
    # Streaming it was fine -- it arrived as it was written -- but it must not
    # reach the verifier or the final answer as though it were a sentence.
    draft = dedupe_sentences(trim_incomplete(draft))

    dropped: list[str] = []
    localised_ok = lang.is_english
    if draft.strip():
        yield sse("status", {"stage": "verifying"})
        verified, grounded, dropped = verify_against_spans(draft, res)
        if verified.strip():
            backend_name = backend.name
            # Verified in English, then rendered in the user's language. The
            # streamed draft the user just watched is English either way; the
            # UI labels it a draft and replaces it with this.
            if not lang.is_english:
                yield sse("status", {"stage": "localising",
                                     "language": lang.name})
            verified, localised_ok = localise(verified, lang)
        else:
            verified = ExtractiveAnswerer().write(message, res)
            grounded = 1.0
            localised_ok = True     # scaffolding is localised by construction
            backend_name = "extractive fallback — the draft failed the gate"
    else:
        verified = ExtractiveAnswerer().write(message, res)
        grounded = 1.0
        backend_name = ("quoted verbatim — polarity guard" if guard
                        else ExtractiveAnswerer.name)
        localised_ok = True

    session.turns.append(Turn(role="user", text=message))
    session.turns.append(Turn(role="assistant", text=verified, intent=intent))

    yield sse("final", {
        "session_id": sid, "intent": intent, "text": verified,
        "citations": citation_payload(res), "abstained": False,
        "layer": res.layer, "guard": guard,
        "groundedness": round(grounded, 3), "backend": backend_name,
        "concept": res.concepts[0].concept.label if res.concepts else "",
        "background": res.background_only,
        "language": lang.code, "language_name": lang.name,
        "localised": localised_ok,
        "dropped": dropped,
        "taxa": [{"input": i, "taxon": t} for i, t in res.taxa_expansions],
        "findings": [],
    })


def compile_payload(result) -> dict:
    from core.schema import Severity

    cb = result.cbom
    return {
        "findings": [
            {
                "severity": f.severity.value, "lane": f.lane,
                "rule_id": f.rule_id, "instrument": f.instrument,
                "provision": f.provision, "statement": f.statement,
                "groundedness": f.groundedness,
                "citations": [
                    {"corpus_id": c.corpus_id, "instrument": c.instrument,
                     "provision": c.provision, "hierarchy": c.hierarchy_path,
                     "pdf": c.source_pdf, "page": c.page, "quote": c.quote}
                    for c in f.citations
                ],
                "autofix": [
                    {"id": x.id, "description": x.description,
                     "available": x.available, "why": x.unavailable_reason}
                    for x in f.autofix
                ],
            }
            for f in cb.findings
        ],
        "resolution": cb.resolution_log,
        "obligations": [
            {"provision": o.provision, "duty": o.duty,
             "discharged_by": o.discharged_by, "when": o.when}
            for o in cb.obligations
        ],
        "matrix": [
            {"jurisdiction": r.jurisdiction.value, "status": r.status.value,
             "patentability": r.patentability, "next_action": r.next_action,
             "citations": r.citation_count}
            for r in cb.jurisdiction_matrix
        ],
        "summary": {
            "blockers": sum(1 for f in cb.findings
                            if f.severity is Severity.BLOCKER),
            "warnings": sum(1 for f in cb.findings
                            if f.severity is Severity.WARNING),
            "opportunities": sum(1 for f in cb.findings
                                 if f.severity is Severity.OPPORTUNITY),
            "obligations": len(cb.obligations),
            "groundedness": cb.groundedness_score,
            "digest": cb.digest()[:16],
        },
    }
