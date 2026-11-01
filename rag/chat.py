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
# A follow-up carries a pronoun or a comparative and no subject of its own.
#
# The list is wider than it looks because real follow-ups are short and vague
# by nature: "what are their pros and cons" has no noun a retriever can use,
# and without "their" in this pattern it went to the retriever cold and
# abstained on a question the previous turn had already established the
# subject of.
FOLLOW_HINT = re.compile(
    r"^\s*(and |what about|how about|why|so |then |ok |okay |but |which one|"
    r"compare|difference|pros|cons)|"
    r"\b(it|its|that|this|those|these|they|them|their|theirs|both|each|either|"
    r"the fix|the same|the former|the latter|pros and cons|advantages|"
    r"disadvantages|instead)\b", re.I
)

# How many earlier turns a follow-up may reach back through.
#
# Three, because that is roughly where a real conversation's subject stops
# being the same subject -- and because every prior question added to a query
# dilutes it. The anchors are the last three SUBSTANTIVE questions, not the
# last three messages: a chain of follow-ups would otherwise fill the window
# with pronouns and push the actual subject out of it.
CONTEXT_TURNS = 3

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

# Asking for a person. Kept here with the other intent patterns rather than
# inside the escalation module, because deciding WHICH route a message takes is the chat
# layer's job and the escalation module's job is to assemble the packet once
# that decision is made.
ESCALATE_HINT = re.compile(
    r"\b(escalate|refer me|referral|"
    r"talk to (?:a|an|some) ?(?:human|person|one|expert|lawyer|advocate|agent)|"
    r"speak to (?:someone|a human|a person|an expert)|"
    r"who (?:do|should|can) i (?:contact|approach|talk to|see|ask)|"
    r"human (?:help|review|facilitator|expert)|"
    r"contact (?:a|an) (?:expert|agent|facilitator|attorney))\b", re.I)

# Asking how two things connect -- a walk through the knowledge graph, not a retrieval.
GRAPH_HINT = re.compile(
    r"\b(how (?:does|do|is|are)\b[^?.]{0,70}\b(?:relate|related|connect|"
    r"connected|reach|linked|apply to)\b"
    r"|what (?:is the )?(?:link|connection|relationship) between"
    r"|how (?:does|do)\b[^?.]{0,50}\b(?:give effect|implement)"
    r"|trace\b[^?.]{0,50}\bto\b)", re.I)


@dataclass
class Turn:
    role: str
    text: str
    answer: Answer | None = None
    intent: str = ""
    citations: list = field(default_factory=list)
    # Concept ids the retriever matched on this turn. Carried so that a
    # follow-up can be expanded with the STATUTORY vocabulary of what was
    # already being discussed rather than only with the lay words the user
    # happened to type -- which is the same register bridge the concept
    # lexicon exists to provide, applied across turns instead of within one.
    concepts: list = field(default_factory=list)


@dataclass
class Session:
    as_of: date = field(default_factory=date.today)
    turns: list[Turn] = field(default_factory=list)
    formulation: Formulation | None = None
    backend_pref: str = "auto"
    # Regulatory classification state. The product is classified before it
    # is advised on, and the classification is built up over a turn
    # or two rather than demanded in one go, so the facts gathered so far and
    # the fact currently being asked about both live on the session.
    class_facts: dict = field(default_factory=dict)
    pending_fact: str | None = None
    # The last compile and the last classification, kept so that an escalation
    # can be assembled from what this conversation already established rather
    # than re-deriving it. In-process only, like everything else on Session:
    # nothing here reaches disk.
    last_compile: object | None = None
    last_classification: object | None = None

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


# Words that carry no subject a retriever can use: the anaphora themselves,
# plus the interrogative and auxiliary scaffolding every question is built
# from. What remains after removing these is what the message is ABOUT.
_NO_SUBJECT = {
    "what", "which", "who", "whom", "why", "how", "when", "where", "does",
    "do", "did", "is", "are", "was", "can", "could", "may", "might", "must",
    "should", "would", "will", "shall", "their", "theirs", "them", "they",
    "it", "its", "this", "that", "those", "these", "one", "ones", "both",
    "each", "either", "neither", "compare", "comparison", "pros", "cons",
    "about", "and", "or", "but", "the", "my", "our", "we", "us", "you",
    "your", "fix", "fixes", "same", "former", "latter", "instead", "also",
    "advantages", "disadvantages", "difference", "differences", "so", "then",
    "ok", "okay", "please", "tell", "me",
}

# How much subject a message may carry and still be read as a follow-up.
MAX_FOLLOWUP_SUBJECT = 3


def subject_tokens(text: str) -> list[str]:
    """The words in a message that actually name what it is about."""
    from sources.index import tokenise

    return [t for t in tokenise(text) if t not in _NO_SUBJECT]


def is_followup(text: str, session: Session) -> bool:
    """A short, anaphoric message that names no subject of its own.

    All three conditions are load-bearing, and the third was added because the
    first two are not enough. "Can I advertise that my product cures diabetes"
    contains the word "that", matches the anaphora pattern, and is eight words
    long -- so on the pattern and the length alone it was read as a follow-up,
    which meant it could never be used as the ANCHOR for the real follow-up
    that came next ("why?"). The bare "why?" then retrieved cold and abstained
    on a question the previous turn had answered perfectly well.

    So the deciding test is whether the message names anything. "What are
    their pros and cons" names nothing; "can I advertise that my product cures
    diabetes" names advertising, a product, curing and diabetes, and belongs
    on the retriever's own terms.
    """
    if not session.turns or not FOLLOW_HINT.search(text):
        return False
    if len(text.split()) > 14:
        return False
    return len(subject_tokens(text)) <= MAX_FOLLOWUP_SUBJECT


def followup_query(session: Session, text: str) -> tuple[str, list[str]]:
    """Expand an anaphoric follow-up into something retrievable.

    "What are their pros and cons" has no noun in it. Retrieved cold it scores
    nothing and the assistant abstains -- on a question whose subject the
    previous turn established perfectly well.

    So the query is rebuilt from three things, in this order of weight:

      1. what the user just typed,
      2. the last few SUBSTANTIVE questions (not the follow-ups between them),
      3. the statutory vocabulary of the concepts those turns matched.

    (3) is the part that does the real work, and it is the same trick the
    concept lexicon already plays within a single turn: a user says "GI", the
    statute says "geographical indication", and carrying the statutory form
    across turns is what lets a follow-up land on the provisions the previous
    answer cited rather than on whatever the pronoun happens to lexically
    resemble.

    Returns the expanded query and the anchor questions used, because the
    assistant says out loud what it read the follow-up as. A system that
    silently guesses which earlier question you meant is one you cannot
    correct.
    """
    anchors: list[str] = []
    concept_ids: list[str] = []

    for turn in reversed(session.turns):
        if turn.role == "user":
            # Skip the follow-ups themselves: a chain of pronouns would fill
            # the window and push the actual subject out of it.
            if (turn is not session.turns[-1]
                    and not is_followup(turn.text, session)
                    and subject_tokens(turn.text)
                    and turn.text not in anchors):
                anchors.append(turn.text)
        elif turn.concepts:
            for cid in turn.concepts:
                if cid not in concept_ids:
                    concept_ids.append(cid)
        if len(anchors) >= CONTEXT_TURNS:
            break

    if not anchors:
        return text, []

    terms: list[str] = []
    if concept_ids:
        from rag.concepts import load_concepts

        by_id = {c.id: c for c in load_concepts().concepts}
        for cid in concept_ids[:CONTEXT_TURNS]:
            c = by_id.get(cid)
            if c:
                terms += c.statutory[:4]

    # Newest anchor first: if the subject changed two turns ago, the most
    # recent statement of it should dominate the scoring.
    parts = [text] + anchors + list(dict.fromkeys(terms))
    return " ".join(parts)[:600], anchors


def classify(text: str, session: Session) -> str:
    if INGREDIENT_LIST.search(text) and COMPILE_HINT.search(text):
        return "COMPILE"
    if INGREDIENT_LIST.search(text) and len(parse_ingredients(text)) >= 2:
        return "COMPILE"
    if is_followup(text, session):
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
    from classification.classify import facts_from_formulation, load_classes

    facts = dict(session.class_facts)
    read = (facts_from_formulation(session.formulation, text)
            if session.formulation is not None else None)
    if read is None:
        from classification.classify import facts_from_text

        read = facts_from_text(text)
    # Facts the user has stated explicitly win over facts inferred from prose.
    for k, v in read.items():
        if v is not None and k not in session.class_facts:
            facts[k] = v
    session.class_facts.update({k: v for k, v in facts.items() if v is not None})

    result = load_classes().classify(facts)
    session.pending_fact = _fact_for_question(result)
    session.last_classification = result
    return result


def _fact_for_question(result) -> str | None:
    from classification.classify import QUESTIONS

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
    referral: object | None = None
    path: object | None = None
    trace: object | None = None


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

    # The regulatory category comes before the advice, because the
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
    session.last_compile = result
    if result.blockers:
        lines += ["", "Or say 'escalate' and I will assemble a referral packet "
                      "for a registered patent agent and the regulators "
                      "involved, with every citation attached."]
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
    session.last_compile = current
    return ChatReply(text="\n".join(lines), intent="COMPILE",
                     compile_result=current)


def escalate_reply(session: Session, text: str = "") -> ChatReply:
    """Hand over to a person, with a brief they can act on.

    Everything in the packet was already established in this session, which is
    the point: the referral is assembled from the compile, the classification
    and the last answer, so it cannot contain a claim the system did not
    already have to cite. Nothing is transmitted -- the packet is rendered for
    the user to copy.
    """
    from escalation.escalate import assess, render

    last = session.last_answer
    ref = assess(
        compile_result=session.last_compile,
        answer=last if (last is not None and last.abstained) else None,
        classification=session.last_classification,
        user_asked=True,
        redact=bool(REDACT_HINT.search(text)),
    )
    body = render(ref)
    if ref.needed and not REDACT_HINT.search(text):
        body += ("\n\nSay 'escalate without the formulation' and I will "
                 "regenerate this with the ingredient names removed. The legal "
                 "posture and every citation stay; the recipe does not appear.")
    return ChatReply(text=body, intent="ESCALATE", referral=ref)


def is_graph_question(text: str) -> bool:
    """Whether this message should be answered by a walk rather than a lookup.

    Two conditions, and the second is the one that matters. GRAPH_HINT is a
    pattern over the wording, and the wording is ambiguous in ways only the
    graph can settle: "how do I apply to the NBA under the 2024 Rules?" reads
    as a relationship question because of "apply to", and is a procedure
    question whose real answer is Rule 13. Sending it to the walk produced a
    dead end -- "I could not pick two out of that sentence" -- for a question
    the retriever answers well.

    So a walk is chosen only when the graph can actually name both ends. Both
    the synchronous and the streaming path call this, because the streaming
    path decides the route before `respond` runs and a second copy of the rule
    would drift.
    """
    if not GRAPH_HINT.search(text):
        return False

    from graph.graph import load_graph
    from planner.orchestrate import _graph_endpoints

    return len(_graph_endpoints(text, load_graph())) >= 2


def graph_reply(session: Session, text: str) -> ChatReply:
    """Answer a relationship question by walking the graph.

    No model is in this path at all. Every line of the walk is an edge the
    system can already prove, and the rendering is fixed connective text over
    edge notes and provision headings.
    """
    from graph.graph import load_graph
    from planner.orchestrate import _graph_endpoints

    g = load_graph()
    ends = _graph_endpoints(text, g)
    if len(ends) < 2:
        # Unreachable through respond(), which gates on is_graph_question, but
        # kept because this stays callable on its own.
        return ChatReply(
            text="I can trace how two things in the corpus connect, but I "
                 "could not pick two out of that sentence. Name them as the "
                 "corpus does — for example: 'how does the Nagoya Protocol "
                 "connect to the Biological Diversity Act'.",
            intent="GRAPH")
    p = g.path(ends[0].id, ends[1].id)
    if p is None:
        return ChatReply(
            text=f"There is no path between {ends[0].label} and "
                 f"{ends[1].label} in the knowledge graph. That is a real "
                 f"answer rather than a failure: nothing in the ingested "
                 f"corpus asserts a relationship between them, and I will not "
                 f"invent one.",
            intent="GRAPH")
    return ChatReply(text="\n".join(g.explain(p)), intent="GRAPH", path=p)


def orchestrate_reply(session: Session, text: str, *,
                      backend: AnswerBackend | None = None) -> ChatReply:
    """Multi-part question: plan it, run the steps, present them separately."""
    from planner.orchestrate import run as run_plan

    o = run_plan(text, as_of=session.as_of, backend=backend, session=session)
    for r in o.trace.results:
        if r.step.tool == "compile" and r.data is not None:
            session.last_compile = r.data
            session.formulation = getattr(r.data, "formulation", session.formulation)
    return ChatReply(text=o.text, intent="ORCHESTRATE",
                     citations=list(o.citations), trace=o.trace)


REDACT_HINT = re.compile(
    r"\b(without the formulation|redact|redacted|anonymis|anonymiz|"
    r"without (?:my )?ingredients|hide the (?:recipe|ingredients))\b", re.I)


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

    # Asking for a person. Checked before retrieval, because the answer is
    # assembled from this session rather than looked up -- retrieving "who
    # should I contact" would return some section about the Controller.
    if ESCALATE_HINT.search(text):
        reply = escalate_reply(session, text)
        session.turns.append(Turn(role="assistant", text=reply.text,
                                  intent=reply.intent))
        return reply

    # Asking how two things connect. A walk, not a lookup -- but only if the
    # graph can actually name both ends; otherwise this falls through to
    # retrieval below.
    if is_graph_question(text):
        reply = graph_reply(session, text)
        session.turns.append(Turn(role="assistant", text=reply.text,
                                  intent=reply.intent))
        return reply

    intent = classify(text, session)

    # A genuinely multi-part question goes to the orchestrator, which runs the
    # parts as separate steps and keeps their evidence separate. The test is
    # deliberately narrow -- two or more retrieval/graph steps in the plan --
    # so an ordinary single question, a compile, or a follow-up keeps the
    # simpler path it already had. Orchestration is for questions that a
    # single retrieval cannot serve, not a new default.
    if intent == "ASK":
        from planner.orchestrate import plan as build_plan

        steps = build_plan(text, session=session)
        if len([s for s in steps if s.tool in ("ask", "graph")]) >= 2:
            reply = orchestrate_reply(session, text, backend=backend)
            session.turns.append(Turn(role="assistant", text=reply.text,
                                      intent=reply.intent,
                                      citations=reply.citations))
            return reply

    if intent == "COMPILE":
        f = formulation_from_text(text)
        if f:
            reply = compile_reply(f, session, text)
            session.turns.append(Turn(role="assistant", text=reply.text,
                                      intent=reply.intent))
            return reply
        intent = "ASK"

    # A short follow-up is resolved against the last few turns rather than
    # retrieved cold -- "what are their pros and cons" retrieves nothing on
    # its own, and the subject it refers to was established two turns ago.
    query, anchors = (followup_query(session, text) if intent == "FOLLOW"
                      else (text, []))

    res = load_retriever().search(query, k=6, as_of=session.as_of,
                                  citable_only=True)
    a = answer(text, res, backend=backend)

    body = a.text
    # Say what the follow-up was read as. The system resolved a pronoun to a
    # question the user asked earlier, and that is a guess the user has to be
    # able to see and correct -- silently answering the wrong earlier question
    # is exactly the failure a confident chatbot makes.
    if anchors and not a.abstained:
        body = (f"Reading that as a follow-up to: “{anchors[0].strip()}”\n\n"
                + body)

    offer = ""
    if a.suggested_rules and not a.abstained:
        # In the user's language, like every other sentence the system says in
        # its own voice. This one is the handover into the COMPILE route, so a
        # user who cannot read it never discovers the half of this product
        # that is not a chatbot.
        offer = localised(a.language, "offer")
        body += f"\n\n{offer}"

    session.turns.append(Turn(role="assistant", text=body, answer=a,
                              intent=intent, citations=a.citations,
                              concepts=[m.concept.id for m in res.concepts]))
    return ChatReply(text=body, intent=intent, answer=a,
                     citations=a.citations, offer=offer)
