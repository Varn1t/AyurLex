"""Planner -- agentic, multi-source orchestration.

Agentic, multi-source orchestration to deepen
multi-step reasoning. This module is that layer
-- built to a specific rule that is worth stating before any code:

    THE PLAN IS DETERMINISTIC. THE TOOLS ARE DETERMINISTIC. THE COMPOSITION IS
    DETERMINISTIC. The only place a model appears is inside a retrieval step,
    phrasing an answer over spans it was handed -- exactly where it already
    was, behind exactly the same citation gate.

That is an unusual shape for an "agent", and it is deliberate. The ordinary
agentic pattern hands a model a tool list and lets it decide what to call, in
what order, with what arguments, and then lets it write a summary over
everything it collected. Every one of those four freedoms is a new way to be
wrong, and the last one is the worst: a model summarising across steps can
blend authority from two jurisdictions into one confident sentence, which is
the single failure this whole system exists to prevent.

WHAT ORCHESTRATION ACTUALLY BUYS HERE
-------------------------------------
Not autonomy. Three concrete things a single-shot pipeline cannot do:

1. CROSS-LAYER QUESTIONS, ANSWERED WITHOUT CONFLATING THE LAYERS.
   "What does Nagoya require and what do I have to do in India?" is one
   question with two answers under two different authorities. Single-shot
   retrieval must pick one layer -- that is the pre-filter working as designed.
   The orchestrator runs the layers as SEPARATE steps, each independently
   retrieved, gated and cited, and presents them as separate sections with
   their own badges. The evidence is never pooled, so the composition cannot
   merge them.

2. DESCRIBE-AND-ASK IN ONE TURN. "My churna contains amla, haritaki and
   bibhitaki -- can I patent it and sell it in the US?" is a compile AND two
   legal questions. The compile runs first because its output (the resolved
   taxa, the category, the findings) is the context the questions need.

3. RELATIONSHIP QUESTIONS. "How does the Nagoya Protocol reach me?" is a graph
   walk, not a retrieval. The planner routes it to the knowledge graph.

EVERY RUN LEAVES A TRACE
------------------------
`Trace` records each step: the tool, why the planner chose it, the arguments,
how long it took, what it cited, and whether it abstained. An agent whose steps
cannot be audited afterwards is not deployable in a government department, and
the trace is what a reviewer reads instead of trusting the summary.

THE BUDGET IS A HARD CAP
------------------------
`MAX_STEPS` bounds the plan before anything runs. There is no loop that decides
whether to keep going, so there is no run that fails to terminate -- the plan is
finite the moment it is built, and can be printed before execution.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

# Hard bound on a plan. A plan is built in full before any step executes, so
# this is a cap on a list, not a stopping condition inside a loop.
MAX_STEPS = 6

# Sentence/clause boundaries a person actually uses when asking two things at
# once. Deliberately conservative: a false split turns one good question into
# two bad ones, and two bad retrievals are worse than one good one.
SPLIT = re.compile(
    r"\s*(?:\?|;|\band also\b|\balso,\b|\band separately\b|\bplus\b|\n)+\s*",
    re.I)

# A clause has to look like a question or a request before it becomes a step.
ASKS = re.compile(
    r"\b(can|may|must|should|do|does|is|are|what|which|who|how|why|when|where|"
    r"tell me|explain|need|require)\b", re.I)

# Named international instruments. Reused from the retriever's vocabulary
# rather than reinvented, so the planner and the layer pre-filter agree about
# what "international" means.
from rag.retriever import INTL_MARKER  # noqa: E402

# Indian statutory markers, for the mirror-image test.
IN_MARKER = re.compile(
    r"\b(India|Indian|Patents Act|Biological Diversity|Trade Marks Act|"
    r"Drugs and Cosmetics|Drugs and Magic Remedies|Geographical Indications|"
    r"Copyright Act|Designs Act|Plant Varieties|NBA|National Biodiversity|"
    r"State Biodiversity|Ayush|AYUSH|TKDL|ASU)\b")

# "How does X relate to Y" -- a walk, not a lookup.
RELATION = re.compile(
    r"\b(how (?:does|do|is|are)\b.{0,60}\b(?:relate|related|connect|connected|"
    r"reach|apply|linked)\b"
    r"|what (?:is the )?(?:link|connection|relationship)\b"
    r"|how (?:does|do) .{0,40}\b(?:give effect|implement)"
    r"|trace .{0,40}\bto\b"
    r"|路)", re.I)

ESCALATE_ASK = re.compile(
    r"\b(escalate|talk to (?:a|an) (?:human|person|expert|lawyer|agent)|"
    r"speak to (?:someone|a human)|refer me|referral|"
    r"who (?:do|should) i (?:contact|approach|talk to|see)|"
    r"human (?:help|facilitator|expert)|contact (?:a|an) (?:expert|agent|"
    r"facilitator))\b", re.I)


# ---------------------------------------------------------------- plan ----
@dataclass
class Step:
    tool: str
    query: str
    why: str
    args: dict = field(default_factory=dict)


@dataclass
class StepResult:
    step: Step
    ok: bool
    summary: str
    citations: list = field(default_factory=list)
    layer: str = ""
    groundedness: float | None = None
    abstained: bool = False
    elapsed: float = 0.0
    data: Any = None
    backend: str = ""


@dataclass
class Trace:
    question: str
    steps: list[Step]
    results: list[StepResult] = field(default_factory=list)
    started: date = field(default_factory=date.today)

    @property
    def elapsed(self) -> float:
        return sum(r.elapsed for r in self.results)

    def lines(self) -> list[str]:
        out = [f"PLAN — {len(self.steps)} step(s), cap {MAX_STEPS}"]
        for i, s in enumerate(self.steps, 1):
            out.append(f"  {i}. {s.tool}  ({s.why})")
            out.append(f"       query: {s.query[:110]}")
        if self.results:
            out.append("")
            out.append("TRACE")
            for i, r in enumerate(self.results, 1):
                mark = "abstained" if r.abstained else ("ok" if r.ok else "failed")
                g = f" g={r.groundedness:.2f}" if r.groundedness is not None else ""
                lay = f" [{r.layer}]" if r.layer else ""
                out.append(f"  {i}. {r.step.tool}{lay}  {mark}{g}  "
                           f"{r.elapsed:.2f}s  {len(r.citations)} citation(s)")
        return out


# Coordinators a person uses to join two questions into one sentence.
COORD = re.compile(r"\s+(?:and|but|while|whereas|,\s*and)\s+|\s+[—–-]{1,2}\s+",
                   re.I)


def split_layers(clause: str) -> tuple[str, str] | None:
    """Decompose a clause that names both an international and an Indian
    instrument into one question per layer.

    A REAL decomposition, not a nudge. The first version of this appended
    "under Indian law" to the same string and sent it twice, and both copies
    came back from the international layer -- because a matched concept
    already decides the layer and a suffix cannot outvote it. Two identical
    answers under two different badges is a worse failure than not splitting
    at all: it looks like the separation is working when it is not.

    So the clause is split at its own coordinator and each half is kept only
    if it independently names one layer and nothing of the other. Where that
    does not hold, this returns None and the caller asks the question once.
    """
    segments = [s.strip(" ,;") for s in COORD.split(clause) if s.strip(" ,;")]
    if len(segments) < 2:
        return None
    intl_parts, in_parts = [], []
    for seg in segments:
        has_intl = bool(INTL_MARKER.search(seg))
        has_in = bool(IN_MARKER.search(seg))
        if has_intl and not has_in:
            intl_parts.append(seg)
        elif has_in and not has_intl:
            in_parts.append(seg)
        # A segment naming both, or neither, is dropped: it cannot be assigned
        # to a layer without guessing, and guessing is the failure mode.
    if not intl_parts or not in_parts:
        return None
    intl_q = " ".join(intl_parts)
    in_q = " ".join(in_parts)
    if len(intl_q.split()) < 3 or len(in_q.split()) < 3:
        return None
    return intl_q, in_q


def plan(message: str, *, session=None) -> list[Step]:
    """Build the whole plan up front, from the text alone.

    Reading order matters and is the legal order, not a heuristic: a
    formulation is compiled before it is asked about, because the regulatory
    category decides what the answer to the question even is.
    """
    steps: list[Step] = []
    text = message.strip()

    # 1. A described formulation compiles first. Its output is the context
    #    every later step needs -- the resolved taxa, the category, the lanes.
    from rag.chat import INGREDIENT_LIST, formulation_from_text  # noqa: F401

    has_formulation = bool(INGREDIENT_LIST.search(text)) and \
        formulation_from_text(text) is not None
    if has_formulation:
        steps.append(Step(
            tool="compile", query=text,
            why="a formulation was described, and the category decides the "
                "posture, so it is compiled before anything is asked about it"))

    # 2. A relationship question is a walk, not a lookup -- but only when the
    #    graph can actually name both ends. RELATION is a pattern over the
    #    wording, and the wording is ambiguous in ways only the graph can
    #    settle: "how do I apply to the NBA under the 2024 Rules?" matches on
    #    "apply to" and is a procedure question. Planning the walk anyway cost
    #    the user a step that could only say it could not find two things,
    #    printed above the answer they actually asked for.
    if RELATION.search(text) and len(_graph_endpoints(text, _graph())) >= 2:
        steps.append(Step(
            tool="graph", query=text,
            why="the question asks how two things are connected, which is a "
                "path through the knowledge graph rather than a retrieval"))

    # 3. Split the remaining text into askable clauses.
    #
    #    When a formulation was described, the ingredient list is REMOVED from
    #    the text the questions are retrieved on. "my churna contains amla,
    #    haritaki and bibhitaki and can I patent it" retrieves badly as one
    #    string -- three plant names dominate the query and the patent question
    #    is drowned. The compile step already has the ingredients; the ask step
    #    needs the question.
    #    Removing the regex span is not enough -- INGREDIENT_LIST's list group
    #    is greedy and swallows the rest of the sentence. So the names that
    #    were actually PARSED are removed, which leaves the question intact.
    ask_text = text
    if has_formulation:
        parsed = formulation_from_text(text)
        stripped = text
        for ing in parsed.ingredients:
            stripped = re.sub(rf"\b{re.escape(ing.raw_name)}\b", " ",
                              stripped, flags=re.I)
        stripped = re.sub(
            r"\b(?:contains?|containing|made (?:of|from)|ingredients?(?: are)?|"
            r"consists? of)\b[:\s]*", " ", stripped, flags=re.I)
        stripped = re.sub(r"\s*(?:,\s*)+", " ", stripped)
        # Removing the names leaves their conjunctions behind ("my churna and
        # and I market it as..."). Collapse them, or the retriever scores a
        # query that reads like broken English.
        stripped = re.sub(r"\b(and|or)\b(\s+\b(?:and|or)\b)+", r"\1", stripped,
                          flags=re.I)
        stripped = re.sub(r"\s+", " ", stripped).strip(" ,;-")
        # Only accept the stripped form if a real question survives it. A
        # formulation described with no question attached must not become a
        # retrieval over the leftover connective words.
        if len(stripped.split()) >= 3 and ASKS.search(stripped):
            ask_text = stripped

    clauses = [c.strip() for c in SPLIT.split(ask_text) if c.strip()]
    clauses = [c for c in clauses if ASKS.search(c) and len(c.split()) >= 3]
    if not clauses and not steps:
        clauses = [ask_text]

    for clause in clauses:
        intl = bool(INTL_MARKER.search(clause))
        indian = bool(IN_MARKER.search(clause))
        if intl and indian:
            # The one case single-shot retrieval genuinely cannot serve: the
            # pre-filter must pick a layer, and this clause needs both. Two
            # separately-retrieved, separately-gated answers -- never one.
            halves = split_layers(clause)
            if halves:
                intl_q, in_q = halves
                steps.append(Step(
                    tool="ask", query=intl_q,
                    why="the question spans both layers; this half names the "
                        "international instrument and is retrieved there",
                    args={"prefer_layer": "INTL"}))
                steps.append(Step(
                    tool="ask", query=in_q,
                    why="and this half names the Indian instrument, so the two "
                        "authorities are never pooled into one answer",
                    args={"prefer_layer": "IN"}))
            else:
                # It spans both layers but will not decompose cleanly. Ask it
                # once and let the pre-filter pick, rather than sending the
                # same string twice and pretending the two answers came from
                # different layers -- which is what a suffix nudge actually
                # produces when a concept match already decided the layer.
                steps.append(Step(
                    tool="ask", query=clause,
                    why="spans both layers but does not decompose into two "
                        "self-contained halves, so it is answered once in "
                        "whichever layer retrieval resolves it to, and labelled"))
        else:
            steps.append(Step(
                tool="ask", query=clause,
                why="a legal question, answered from the corpus with citations"))
        if len(steps) >= MAX_STEPS - 1:
            break

    # 4. Escalation is assessed last, because it reads what the earlier steps
    #    found -- including what they could not answer.
    if ESCALATE_ASK.search(text) or has_formulation:
        steps.append(Step(
            tool="escalate", query=text,
            why="assessed from what the earlier steps established and failed "
                "to establish",
            args={"user_asked": bool(ESCALATE_ASK.search(text))}))

    return steps[:MAX_STEPS]


# --------------------------------------------------------------- tools ----
def _tool_ask(step: Step, ctx: dict) -> StepResult:
    from rag.answer import answer as write_answer
    from rag.retriever import load_retriever

    q = step.query
    want = step.args.get("prefer_layer")
    if want:
        # Steering, not filtering: the query is nudged toward the layer with
        # the layer's own vocabulary, and the retriever's pre-filter still
        # decides. If it lands on the other layer anyway, the result says so
        # rather than being relabelled -- a badge that can lie is worse than
        # no badge.
        q = (f"{q} under the treaty" if want == "INTL"
             else f"{q} under Indian law")
    res = load_retriever().search(q, k=6, as_of=ctx["as_of"], citable_only=True)
    a = write_answer(step.query, res, backend=ctx.get("backend"))
    note = ""
    if want and res.layer != want:
        note = (f"\n(Asked for the {want} layer; retrieval resolved this to "
                f"the {res.layer} layer, and the answer is labelled as what it "
                f"actually is.)")
    return StepResult(
        step=step, ok=not a.abstained, summary=a.text + note,
        citations=list(a.citations), layer=res.layer,
        groundedness=a.groundedness, abstained=a.abstained,
        data=a, backend=a.backend)


def _tool_compile(step: Step, ctx: dict) -> StepResult:
    from core.compiler import compile_formulation
    from rag.chat import formulation_from_text
    from classification.classify import facts_from_formulation, load_classes

    f = formulation_from_text(step.query)
    if f is None:
        return StepResult(step=step, ok=False,
                          summary="No formulation could be parsed from that.")
    result = compile_formulation(f, as_of=ctx["as_of"])
    ctx["compile_result"] = result
    cb = result.cbom
    # Classification runs on the same facts read off the same text, through the
    # same classification path the chat layer uses -- not a second implementation.
    cls = load_classes().classify(facts_from_formulation(f, step.query))
    ctx["classification"] = cls

    lines = []
    if cls is not None and cls.decided:
        lines.append(f"Regulatory category: {cls.category.label} — {cls.because}")
    elif cls is not None and cls.ask:
        lines.append(f"Category still open — {cls.ask[0]}")
    taxa = [r["resolved_to"] for r in cb.resolution_log if r["resolved_to"]]
    if taxa:
        lines.append("Resolved: " + ", ".join(taxa))
    counts = {}
    for x in cb.findings:
        counts[x.severity.value] = counts.get(x.severity.value, 0) + 1
    lines.append(", ".join(f"{v} {k.lower()}" for k, v in sorted(counts.items()))
                 + f", {len(cb.obligations)} obligation(s)")
    for x in cb.findings:
        if x.severity.value == "BLOCKER":
            lines.append(f"  [BLOCKER] {x.instrument} — {x.provision}")
    lines.append(f"C-BOM digest {cb.digest()[:16]}")
    cits = [c for x in cb.findings for c in x.citations]
    return StepResult(step=step, ok=True, summary="\n".join(lines),
                      citations=cits, layer="IN",
                      groundedness=cb.groundedness_score, data=result,
                      backend="compliance rule engine (deterministic)")


def _tool_graph(step: Step, ctx: dict) -> StepResult:
    from graph.graph import load_graph

    g = load_graph()
    ends = _graph_endpoints(step.query, g)
    if len(ends) < 2:
        return StepResult(
            step=step, ok=False,
            summary="I could not identify two things in that question to walk "
                    "between. Name them as they appear in the corpus — an "
                    "instrument, a provision id, or a concept.",
            backend="graph knowledge graph (deterministic)")
    a, b = ends[0], ends[1]
    p = g.path(a.id, b.id)
    if p is None:
        return StepResult(
            step=step, ok=False,
            summary=f"There is no path in the graph between {a.label} and "
                    f"{b.label}. That is a real answer: the corpus asserts no "
                    f"relationship between them.",
            backend="graph knowledge graph (deterministic)")
    return StepResult(step=step, ok=True, summary="\n".join(g.explain(p)),
                      layer=("INTL" if p.crosses_jurisdiction() else "IN"),
                      data=p, backend="graph knowledge graph (deterministic)")


def _graph():
    from graph.graph import load_graph

    return load_graph()


def _graph_endpoints(text: str, g) -> list:
    """Find the two things a relationship question is about.

    Exact-ish only. A fuzzy match here would walk from the wrong node and
    render a confident, well-cited path between two things the user never
    asked about, which is a worse failure than saying it could not tell.
    """
    out, seen = [], set()

    # Corpus ids and rule ids typed directly win outright -- if someone wrote
    # IN.BDA.2002::S6 they meant that provision and nothing else.
    for tok in re.findall(r"[A-Z][A-Z0-9_.]{2,}::[A-Za-z0-9()#]+", text):
        for n in g.resolve(tok)[:1]:
            if n.id not in seen:
                seen.add(n.id)
                out.append(n)

    # Otherwise: longest capitalised phrase that RESOLVES, scanning left to
    # right and skipping past whatever matched.
    #
    # Longest-that-resolves, not longest-looking. The first version took the
    # greedy capitalised span and "how does the Nagoya Protocol connect to the
    # Biological Diversity Act" produced one candidate running from "Nagoya"
    # to "Act", which resolves to nothing -- so a question that names two
    # instruments plainly found neither.
    words = text.split()
    kinds = ("provision", "instrument", "concept", "rule", "category", "taxon")
    i = 0
    while i < len(words):
        w = words[i].strip("“”\"'(),.?;:")
        if not w or not w[0].isupper() or w.lower() in _NOT_A_NAME:
            i += 1
            continue
        best = None
        for span in range(min(9, len(words) - i), 0, -1):
            cand = " ".join(words[i:i + span]).strip("“”\"'(),.?;:")
            if len(cand) < 4:
                continue
            hits = [n for n in g.resolve(cand)[:1] if n.kind in kinds]
            if hits:
                best = (hits[0], span)
                break
        if best and best[0].id not in seen:
            seen.add(best[0].id)
            out.append(best[0])
            i += best[1]
        else:
            i += 1
    return out


# Capitalised words that start a sentence rather than name a thing. Without
# this, "How" and "Does" are tried as node names on every question.
_NOT_A_NAME = {
    "how", "what", "which", "who", "why", "when", "where", "does", "do", "is",
    "are", "can", "may", "must", "should", "the", "a", "an", "i", "we", "my",
    "our", "and", "or", "to", "in", "under", "for", "of", "it", "this", "that",
}


def _tool_escalate(step: Step, ctx: dict) -> StepResult:
    from escalation.escalate import assess, render

    ref = assess(compile_result=ctx.get("compile_result"),
                 answer=ctx.get("last_abstained_answer"),
                 classification=ctx.get("classification"),
                 user_asked=bool(step.args.get("user_asked")),
                 redact=bool(ctx.get("redact")))
    return StepResult(step=step, ok=ref.needed, summary=render(ref),
                      data=ref, backend="escalation escalation (deterministic)")


TOOLS: dict[str, Callable[[Step, dict], StepResult]] = {
    "ask": _tool_ask,
    "compile": _tool_compile,
    "graph": _tool_graph,
    "escalate": _tool_escalate,
}


# -------------------------------------------------------------- runner ----
@dataclass
class Orchestrated:
    question: str
    trace: Trace
    text: str
    citations: list = field(default_factory=list)

    @property
    def steps(self) -> list[StepResult]:
        return self.trace.results


def run(message: str, *, as_of: date | None = None, backend=None,
        redact: bool = False, session=None) -> Orchestrated:
    steps = plan(message, session=session)
    trace = Trace(question=message, steps=steps)
    ctx: dict = {"as_of": as_of or date.today(), "backend": backend,
                 "redact": redact}

    for step in steps:
        fn = TOOLS.get(step.tool)
        if fn is None:
            continue
        t0 = time.perf_counter()
        try:
            r = fn(step, ctx)
        except Exception as exc:                      # pragma: no cover
            r = StepResult(step=step, ok=False,
                           summary=f"step failed: {type(exc).__name__}: {exc}")
        r.elapsed = time.perf_counter() - t0
        if r.abstained and r.data is not None:
            ctx["last_abstained_answer"] = r.data
        trace.results.append(r)

    return Orchestrated(question=message, trace=trace,
                        text=compose(trace), citations=_all_citations(trace))


def _all_citations(trace: Trace) -> list:
    out, seen = [], set()
    for r in trace.results:
        for c in r.citations:
            key = getattr(c, "corpus_id", None) or str(c)
            if key not in seen:
                seen.add(key)
                out.append(c)
    return out


HEADINGS = {
    "compile": "Compiled from your formulation",
    "ask": "Answer",
    "graph": "How these connect",
    "escalate": "Escalation to a human facilitator",
}

LAYER_LABEL = {"IN": "India layer — national law",
               "INTL": "International layer — treaty & foreign regulator"}


def compose(trace: Trace) -> str:
    """Assemble the step outputs into one reply.

    Assemble, not summarise. Each section is exactly what its step produced,
    under its own heading, with its own layer badge and its own citations. No
    sentence in the output spans two steps, which is the mechanical reason the
    orchestrator cannot merge two jurisdictions into one claim -- there is no
    code path that writes across sections.
    """
    if not trace.results:
        return "I could not build a plan for that."

    parts: list[str] = []
    multi = len(trace.results) > 1
    for i, r in enumerate(trace.results, 1):
        head = HEADINGS.get(r.step.tool, r.step.tool)
        if multi:
            badge = f"  ·  {LAYER_LABEL[r.layer]}" if r.layer in LAYER_LABEL else ""
            if r.groundedness is not None:
                badge += f"  ·  groundedness {r.groundedness:.2f}"
            parts.append(f"[{i}/{len(trace.results)}] {head}{badge}")
        body = r.summary.strip()
        if r.abstained:
            body = body or "No authority in the corpus for that."
        parts.append(body)
        # A section can survive the gate and still be thin: one sentence scored
        # above the drop threshold but below entailment. Saying so is the same
        # honesty the single-answer path already practises -- a confidence
        # indicator that only ever reads well is not a confidence indicator.
        if (r.step.tool == "ask" and not r.abstained
                and r.groundedness is not None and r.groundedness < 0.34):
            parts.append(
                "  (Thin: no sentence here cleared the entailment threshold. "
                "The citations below are real — read the provision itself "
                "rather than relying on this phrasing.)")
        if r.citations:
            parts.append("  sources:")
            for c in r.citations[:4]:
                inst = getattr(c, "instrument", "")
                prov = getattr(c, "provision", "")
                pdf = getattr(c, "source_pdf", "")
                page = getattr(c, "page", 0)
                tail = f"  [{pdf} p.{page}]" if pdf else ""
                parts.append(f"    - {inst} — {prov}{tail}")
        parts.append("")

    if multi:
        layers = {r.layer for r in trace.results if r.layer}
        if len(layers) > 1:
            parts.append(
                "The sections above are separate authorities and were "
                "retrieved separately. A treaty article binds India as a "
                "State; the Indian provision is what binds you. They are not "
                "combined into a single answer here, and should not be "
                "combined into one when you act on them.")
            parts.append("")
    parts.append(f"({len(trace.results)} step(s), {trace.elapsed:.1f}s — "
                 f"ask for 'the trace' to see the plan and what each step cited.)")
    return "\n".join(parts).strip()
