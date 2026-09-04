"""The chat layer: conversation state, intent routing, follow-ups.

Chat is the interface; the engine is still the product. Three intents:

  ASK      -- a legal question. Retrieve, answer, cite, or abstain.
  COMPILE  -- the user described a formulation. Route to the compiler and
              return findings, not prose. "Can I patent Triphala with amla,
              haritaki and bibhitaki?" is not a lookup, it is a compile.
  FOLLOW   -- a pronoun-bearing follow-up ("what about the EU?", "and the
              fix?"). Resolved against the last turn rather than retrieved cold.

The COMPILE route is why this is not an ordinary RAG bot. A retrieval chatbot
answers "what does section 3(p) say". This one answers "here is what section
3(p) does to YOUR formulation, and here is the minimum change that clears it",
because the deterministic engine is sitting underneath.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from core.localise import t as localised
from core.schema import (
    ClaimType,
    FilingIntent,
    Formulation,
    Ingredient,
    Severity,
)
from rag.answer import Answer, AnswerBackend, answer, pick_backend
from rag.retriever import load_retriever

# A formulation is being described, not a rule asked about.
COMPILE_HINT = re.compile(
    r"\b(my formulation|my product|my churna|my blend|i (?:make|sell|manufacture|"
    r"want to (?:patent|file|register))|we (?:make|sell|manufacture)|"
    r"compile|check my|analyse my|analyze my|assess my)\b", re.I
)
INGREDIENT_LIST = re.compile(
    r"\b(?:contains?|containing|made (?:of|from)|with|ingredients?(?: are)?|"
    r"consists? of)\b[:\s]+(?P<list>.{6,220})", re.I
)
FOLLOW_HINT = re.compile(
    r"^\s*(and |what about|how about|why|so |then |ok |okay |but )|"
    r"\b(it|that|this|those|the fix|the same)\b", re.I
)

# Asking what the product IS, in regulatory terms. Kept separate from the
# compile hint because the answer is a category and a question, not findings.
CLASSIFY_HINT = re.compile(
    r"\b(classify|classification|what category|which category|"
    r"is (?:it|my product|this) a (?:drug|cosmetic|food|classical|"
    r"proprietary|phytopharmaceutical)|"
    r"classical or proprietary|regulatory category|"
    r"what (?:kind|type) of (?:drug|product) is)\b", re.I
)

SPLIT_ITEMS = re.compile(r"\s*(?:,|;|\band\b|\+|/)\s*", re.I)
STOP_ITEM = {"", "etc", "etc.", "and", "some", "a", "an", "the", "my", "our"}


@dataclass
class Turn:
    role: str
    text: str
    answer: Answer | None = None
    intent: str = ""
    citations: list = field(default_factory=list)


@dataclass
class Session:
    as_of: date = field(default_factory=date.today)
    turns: list[Turn] = field(default_factory=list)
    formulation: Formulation | None = None
    backend_pref: str = "auto"
    # Regulatory classification state. SIH26045 wants the product classified
    # before it is advised on, and the classification is built up over a turn
    # or two rather than demanded in one go, so the facts gathered so far and
    # the fact currently being asked about both live on the session.
    class_facts: dict = field(default_factory=dict)
    pending_fact: str | None = None

    @property
    def last_user(self) -> str:
        for t in reversed(self.turns):
            if t.role == "user":
                return t.text
        return ""

    @property
    def last_answer(self) -> Answer | None:
        for t in reversed(self.turns):
            if t.role == "assistant" and t.answer:
                return t.answer
        return None


def classify(text: str, session: Session) -> str:
    if INGREDIENT_LIST.search(text) and COMPILE_HINT.search(text):
        return "COMPILE"
    if INGREDIENT_LIST.search(text) and len(parse_ingredients(text)) >= 2:
        return "COMPILE"
    if session.turns and FOLLOW_HINT.search(text) and len(text.split()) <= 12:
        return "FOLLOW"
    return "ASK"


def parse_ingredients(text: str) -> list[str]:
    """Pull the ingredient list out of a sentence.

    This is the one place an LLM would earn its keep -- messy free text into a
    typed schema is exactly job (a) it is allowed. The regex path is the
    offline fallback and is deliberately conservative: it would rather return
    nothing and ask than invent a constituent that was never mentioned.
    """
    m = INGREDIENT_LIST.search(text)
    if not m:
        return []
    raw = m.group("list")
    raw = re.split(r"\b(?:for|to treat|indicated|which|that)\b", raw, 1)[0]
    items = []
    for part in SPLIT_ITEMS.split(raw):
        p = part.strip(" .,:;\"'()")
        if p.lower() in STOP_ITEM or len(p) < 3 or len(p.split()) > 4:
            continue
        items.append(p)
    return items[:15]


def formulation_from_text(text: str, name: str = "Formulation from chat"
                          ) -> Formulation | None:
    items = parse_ingredients(text)
    if len(items) < 1:
        return None
    intent = FilingIntent.IN_FIRST
    if re.search(r"\b(abroad|outside india|us|europe|foreign)\b", text, re.I):
        intent = FilingIntent.FOREIGN_FIRST
    claims = re.findall(r"[\"“]([^\"”]{4,120})[\"”]", text)
    return Formulation(
        name=name,
        ingredients=[Ingredient(raw_name=i) for i in items],
        marketing_claims=claims,
        filing_intent=intent,
        claim_types=[ClaimType.COMPOSITION],
    )


# Only unambiguous affirmatives. "it is a churna" is an answer to a question
# about the dosage form, not a yes to whatever was asked, and reading it as
# a yes would silently record the wrong fact.
YES = re.compile(
    r"^\s*(yes|yeah|yep|yup|y|haan|haan ji|ji haan|correct|true|right|"
    r"it does|we do)\b", re.I)
NO = re.compile(
    r"^\s*(no|nope|n|nahi|not|false|it is not|we don't|we do not)\b",
    re.I)


def answer_to_pending(text: str) -> bool | None:
    """A bare yes/no reply to the clarifying question just asked."""
    if YES.search(text):
        return True
    if NO.search(text):
        return False
    return None


def classification_for(session: Session, text: str = ""):
    """Classify using everything known: the session's gathered facts, the
    formulation on the session, and whatever this sentence settles."""
    from vargikarana.classify import facts_from_formulation, load_classes

    facts = dict(session.class_facts)
    read = (facts_from_formulation(session.formulation, text)
            if session.formulation is not None else None)
    if read is None:
        from vargikarana.classify import facts_from_text

        read = facts_from_text(text)
    # Facts the user has stated explicitly win over facts inferred from prose.
    for k, v in read.items():
        if v is not None and k not in session.class_facts:
            facts[k] = v
    session.class_facts.update({k: v for k, v in facts.items() if v is not None})

    result = load_classes().classify(facts)
    session.pending_fact = _fact_for_question(result)
    return result


def _fact_for_question(result) -> str | None:
    from vargikarana.classify import QUESTIONS

    if result.decided or not result.ask:
        return None
    first = result.ask[0]
    return next((k for k, q in QUESTIONS.items() if q == first), None)


def classification_lines(result) -> list[str]:
    """The classification, rendered for the text transcript."""
    if not result.decided:
        lines = ["Before I can place this in a regulatory category, I need to "
                 "know:"]
        lines += [f"  - {q}" for q in result.ask]
        lines.append("")
        lines.append("The category decides the IP posture, so this is not a "
                     "formality: the same herbs are unpatentable traditional "
                     "knowledge as a classical churna and a defensible "
                     "invention as a standardised fraction.")
        return lines
    c = result.category
    lines = [f"Regulatory category: {c.label}",
             f"  because {result.because}.",
             "",
             f"  Requires: {c.requires}",
             f"  IP posture: {c.ip}",
             f"  ABS posture: {c.abs}"]
    if c.uncited_authority:
        lines += ["", f"  Note: {c.uncited_authority}"]
    return lines


@dataclass
class ChatReply:
    text: str
    intent: str
    answer: Answer | None = None
    compile_result: object | None = None
    classification: object | None = None
    citations: list = field(default_factory=list)
    offer: str = ""


SEV_ICON = {
    Severity.BLOCKER: "BLOCKER",
    Severity.WARNING: "WARNING",
    Severity.OPPORTUNITY: "OPPORTUNITY",
    Severity.INFO: "INFO",
}


def classify_reply(session: Session, text: str = "") -> ChatReply:
    """The classification on its own: either the category, or the one question
    still needed to reach it."""
    result = classification_for(session, text)
    lines = classification_lines(result)
    if result.decided and session.formulation is not None:
        lines += ["", "Say 'compile' and I will run the rules against this "
                      "formulation on that footing."]
    return ChatReply(text="\n".join(lines), intent="CLASSIFY",
                     classification=result)


def compile_reply(f: Formulation, session: Session, text: str = ""
                  ) -> ChatReply:
    from core.compiler import compile_formulation

    # SIH26045 puts the regulatory category before the advice, because the
    # category is what decides the advice: the same three herbs are
    # unpatentable traditional knowledge as a classical churna and a
    # defensible invention as a standardised fraction.
    session.formulation = f
    classification = classification_for(session, text)
    result = compile_formulation(f, as_of=session.as_of)
    cb = result.cbom
    counts = {s: sum(1 for x in cb.findings if x.severity is s) for s in Severity}

    lines = [
        f"I compiled that as a formulation rather than answering it as a "
        f"question, because you described {len(f.ingredients)} ingredient(s).",
        "",
    ]
    lines += classification_lines(classification)
    lines += [
        "",
        "Resolved:",
    ]
    for r in cb.resolution_log:
        mark = "  ok " if r["auto_accepted"] else "  ?? "
        target = r["resolved_to"] or " / ".join(r["candidates"]) or "unresolved"
        lines.append(f"{mark}{r['input']} → {target}")

    lines += [
        "",
        f"{counts[Severity.BLOCKER]} blocker(s), {counts[Severity.WARNING]} "
        f"warning(s), {counts[Severity.OPPORTUNITY]} opportunity, "
        f"{len(cb.obligations)} obligation(s):",
        "",
    ]
    for x in cb.findings:
        if x.severity in (Severity.BLOCKER, Severity.OPPORTUNITY):
            lines.append(f"  [{SEV_ICON[x.severity]}] {x.provision} — "
                         f"{x.instrument}")
            lines.append(f"      {x.statement[:220]}"
                         f"{'…' if len(x.statement) > 220 else ''}")

    fixes = [fx.id for x in result.blockers for fx in x.autofix if fx.available]
    offer = ""
    if fixes:
        offer = ("Ask me to 'apply the fixes' and I'll recompile to prove which "
                 "blockers actually clear.")
        lines += ["", offer]

    session.formulation = f
    return ChatReply(text="\n".join(lines), intent="COMPILE",
                     compile_result=result, offer=offer,
                     classification=classification)


def autofix_reply(session: Session) -> ChatReply:
    from core.compiler import apply_autofix, compile_formulation, diff_findings

    f = session.formulation
    if f is None:
        return ChatReply(
            text="I don't have a formulation in this conversation yet. "
                 "Describe one — for example: 'my churna contains amla, "
                 "haritaki and bibhitaki'.",
            intent="COMPILE",
        )
    before = compile_formulation(f, as_of=session.as_of)
    overrides: dict = {}
    current = before
    lines = ["Recompiling with each available fix applied:", ""]
    for finding in list(before.blockers):
        fix = next((x for x in finding.autofix if x.available), None)
        if not fix:
            lines.append(f"  {finding.provision}: no fix available on these facts")
            continue
        current, overrides = apply_autofix(f, fix, as_of=session.as_of,
                                           base_overrides=overrides)
        d = diff_findings(before, current)
        lines.append(f"  applied {fix.id}")
        for r in d["cleared"]:
            lines.append(f"      cleared  {r}")
    lines += ["", f"Blockers {len(before.blockers)} → {len(current.blockers)}. "
                  "That is a recompile, not a promise — the rules were re-run "
                  "against the patched facts."]
    return ChatReply(text="\n".join(lines), intent="COMPILE",
                     compile_result=current)


def respond(text: str, session: Session, *,
            backend: AnswerBackend | None = None) -> ChatReply:
    backend = backend or pick_backend(session.backend_pref)
    session.turns.append(Turn(role="user", text=text))

    # A bare yes/no while a classification question is outstanding is an
    # answer to that question, not a new query. Handling it first is what
    # makes the clarifying flow a conversation rather than a one-shot form.
    if session.pending_fact:
        said = answer_to_pending(text)
        if said is not None:
            session.class_facts[session.pending_fact] = said
            session.pending_fact = None
            reply = classify_reply(session)
            session.turns.append(Turn(role="assistant", text=reply.text,
                                      intent=reply.intent))
            return reply

    # Asking for the category directly, rather than describing a formulation.
    if CLASSIFY_HINT.search(text):
        reply = classify_reply(session, text)
        session.turns.append(Turn(role="assistant", text=reply.text,
                                  intent=reply.intent))
        return reply

    if re.search(r"\b(apply|run) (the )?(fix|fixes|autofix)\b", text, re.I):
        reply = autofix_reply(session)
        session.turns.append(Turn(role="assistant", text=reply.text,
                                  intent=reply.intent))
        return reply

    intent = classify(text, session)

    if intent == "COMPILE":
        f = formulation_from_text(text)
        if f:
            reply = compile_reply(f, session, text)
            session.turns.append(Turn(role="assistant", text=reply.text,
                                      intent=reply.intent))
            return reply
        intent = "ASK"

    # A short follow-up is resolved against the previous question rather than
    # retrieved cold -- "what about the fix?" retrieves nothing on its own.
    query = text
    if intent == "FOLLOW":
        prior = [t.text for t in session.turns[:-1] if t.role == "user"]
        if prior:
            query = f"{prior[-1]} {text}"

    res = load_retriever().search(query, k=6, as_of=session.as_of,
                                  citable_only=True)
    a = answer(text, res, backend=backend)

    body = a.text
    offer = ""
    if a.suggested_rules and not a.abstained:
        # In the user's language, like every other sentence the system says in
        # its own voice. This one is the handover into the COMPILE route, so a
        # user who cannot read it never discovers the half of this product
        # that is not a chatbot.
        offer = localised(a.language, "offer")
        body += f"\n\n{offer}"

    session.turns.append(Turn(role="assistant", text=body, answer=a,
                              intent=intent, citations=a.citations))
    return ChatReply(text=body, intent=intent, answer=a,
                     citations=a.citations, offer=offer)
