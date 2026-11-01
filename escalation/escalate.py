"""Escalation -- escalation to a human IP facilitator.

A path to escalate to a human IP facilitator. The
reason it belongs in a
citation-grounded assistant rather than beside it is the honest one: the
system's own limits are the best signal that a human is needed. It already
knows when it abstained, when a blocker has no available fix, when a taxon was
genuinely ambiguous, and when a category's governing instrument is not in the
corpus. Those are exactly the moments to hand over.

So escalation here is not a "contact us" button. It is:

  1. A DETERMINISTIC TRIGGER SET. No model decides whether to escalate. A
     trigger is a fact about the session -- a blocker exists, the answer
     abstained, the classifier is still undecided -- computed from the same
     objects the rest of the system produces.

  2. A ROUTING TABLE with a statutory basis. `data/facilitators.yaml` names
     institutional routes, each carrying the provision that establishes the
     office and a verbatim anchor, verified at load exactly like a compliance rule.
     A route whose anchor has drifted from the primary source is dropped and
     reported. Routes with no statute behind them -- the FSSAI Ayurveda Aahara
     regulations are not in the corpus, and a ministry facilitation desk is
     administrative rather than statutory -- say so in the answer instead of
     borrowing a loosely related citation.

  3. A REFERRAL PACKET, generated for the user to carry. It states what was
     asked, what the system determined and on what authority, what it could
     NOT determine and why, and what the facilitator should be asked for. It
     has a reference id that is a content digest, so the same session produces
     the same reference twice and a facilitator can tell two referrals apart.

PRIVACY IS THE DESIGN CONSTRAINT, NOT A FEATURE
-----------------------------------------------
Nothing here transmits anything. The packet is rendered for the user to copy
or export deliberately; there is no outbound call, no queue, no ticket, and
nothing is written to disk unless the user names a file. That is the same
promise the chat layer makes, and escalation is precisely where a careless
implementation would break it -- "we'll forward this to an expert for you" is
how a proprietary formulation leaves the building.

`redact=True` goes further and removes the ingredient names and proportions
while keeping the legal posture intact, so a founder can get a facilitator's
view on the Section 3(p) question without disclosing the formulation at all.
The redacted packet still carries the taxon count, the lanes, the findings and
the citations, because none of those disclose the recipe.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

from sources.index import Corpus, load_corpus

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "data" / "facilitators.yaml"

# The trigger vocabulary. Every one of these is a fact the system already
# computed for another purpose -- which is the point. An escalation trigger
# that needed its own inference would be a new way to be wrong.
TRIGGERS = {
    "BLOCKER_PRESENT":
        "the compile produced blockers that stop the filing or the claim as it "
        "stands",
    "NO_FIX_AVAILABLE":
        "a blocker has no autofix available on these facts, so clearing it "
        "requires a judgement the rule engine cannot make",
    "ABSTAINED":
        "the assistant had no authority in the ingested corpus for the question "
        "asked",
    "CLASSIFICATION_UNDECIDED":
        "the regulatory category is still open, and the category decides the "
        "whole IP posture",
    "CLASSIFICATION_UNCITED":
        "the category was decided, but the instrument that governs it is not in "
        "the corpus, so the requirements are stated without a citation",
    "AMBIGUOUS_TAXON":
        "an ingredient name resolves to more than one species and the system "
        "refuses to pick one",
    "TKDL_ADVERSE_OUTCOME":
        "the formulation resembles an application already refused, revoked or "
        "withdrawn after TKDL prior art was cited",
    "FOREIGN_JURISDICTION":
        "a target market is outside the ingested corpus, so its row in the "
        "jurisdiction matrix is an abstention",
    "FOREIGN_FILING":
        "filing outside India is intended, which engages Section 39 and the "
        "foreign-filing permit",
    "USER_REQUESTED":
        "you asked to be put in front of a person",
}

# Lane -> the route that owns it. These are ROUTING tags, not reasons: a lane
# says which office a finding belongs to, never why a human is needed. Keeping
# them out of `triggers` is what stops the referral explaining itself with
# "ACCESS_LANE" instead of a sentence a founder can read.
LANE_TRIGGER = {
    "PATENT": "PATENT_LANE",
    "ACCESS": "ACCESS_LANE",
    "BRAND": "BRAND_LANE",
    "REGULATORY": "REGULATORY_LANE",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


@dataclass
class Facilitator:
    id: str
    label: str
    mandate: str
    handles: list[str]
    ask_for: str = ""
    site: str = ""
    contact: str = "configure at deployment"
    basis: str = ""
    anchor: str = ""
    background: bool = False
    uncited_authority: str = ""
    # Filled at load.
    citation: str = ""
    page: int = 0
    pdf: str = ""
    instrument: str = ""
    provision: str = ""
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def cited(self) -> bool:
        return bool(self.basis) and not self.problems


class FacilitatorRegistry:
    """Loads and verifies the routes. Same gate as everywhere else: a route
    citing a provision that is not in the corpus, or an anchor that is not
    verbatim in it, is a defect and is reported rather than shipped."""

    def __init__(self, path: Path = REGISTRY, corpus: Corpus | None = None):
        corpus = corpus or load_corpus()
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        self.routes: list[Facilitator] = []
        for r in raw:
            f = Facilitator(
                id=r["id"], label=r["label"],
                mandate=str(r.get("mandate", "")).strip(),
                handles=list(r.get("handles", []) or []),
                ask_for=str(r.get("ask_for", "")).strip(),
                site=r.get("site", ""),
                contact=r.get("contact", "configure at deployment"),
                basis=r.get("basis", ""),
                anchor=str(r.get("anchor", "")).strip(),
                background=bool(r.get("background", False)),
                uncited_authority=str(r.get("uncited_authority", "")).strip(),
            )
            if f.basis:
                if not corpus.has(f.basis):
                    f.problems.append(f"{f.basis} is not in the corpus")
                else:
                    rec = corpus.get(f.basis)
                    if f.anchor and _norm(f.anchor) not in _norm(rec["text"]):
                        f.problems.append(
                            f"anchor is not verbatim in {f.basis}")
                    else:
                        # Prose sources are located by page, not by section.
                        # The rule lives in rag.answer and is imported rather
                        # than restated, so "Section p.1" cannot reappear here
                        # after being fixed there.
                        from rag.answer import _provision_label

                        f.instrument = rec["act_title"]
                        f.provision = _provision_label(rec)
                        f.citation = f"{f.instrument} — {f.provision}"
                        f.pdf = rec.get("source_pdf", "")
                        f.page = rec.get("page_start", 0)
            elif not f.uncited_authority:
                f.problems.append(
                    "no statutory basis and no uncited_authority note")
            self.routes.append(f)

    @property
    def problems(self) -> list[str]:
        return [f"{r.id}: {p}" for r in self.routes for p in r.problems]

    def by_id(self, rid: str) -> Facilitator | None:
        return next((r for r in self.routes if r.id == rid), None)

    def for_triggers(self, triggers: list[str]) -> list[Facilitator]:
        """Routes in registry order, so the ordering is reviewable data rather
        than a scoring function nobody can audit."""
        want = set(triggers)
        return [r for r in self.routes
                if r.ok and (want & set(r.handles))]


@lru_cache(maxsize=1)
def load_registry() -> FacilitatorRegistry:
    return FacilitatorRegistry()


# ------------------------------------------------------------- referral ----
@dataclass
class Referral:
    triggers: list[str]
    routes: list[Facilitator]
    subject: str
    routing: list[str] = field(default_factory=list)
    established: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    could_not_determine: list[str] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    obligations: list[str] = field(default_factory=list)
    redacted: bool = False
    as_of: date = field(default_factory=date.today)
    law_version: str = ""

    @property
    def needed(self) -> bool:
        return bool(self.triggers)

    def reference(self) -> str:
        """A content digest, not a counter. Two runs of the same session give
        the same reference, and any change to the substance gives a new one --
        the same property the C-BOM digest has, for the same reason."""
        blob = "\n".join([
            "|".join(sorted(self.triggers)),
            "|".join(r.id for r in self.routes),
            self.subject,
            "\n".join(self.established),
            "\n".join(self.open_questions),
            "\n".join(self.could_not_determine),
            "\n".join(sorted(c.get("corpus_id", "") for c in self.citations)),
            str(self.redacted),
        ])
        return "AYL-" + hashlib.sha256(blob.encode()).hexdigest()[:10].upper()


DISCLAIMER = (
    "This referral was generated from primary statutory sources by AyurLex. "
    "It is informational compliance analysis, not legal advice, and "
    "does not replace a registered patent agent or advocate. Every citation "
    "below can be opened at the page given."
)

PRIVACY_NOTE = (
    "Generated locally. Nothing in this referral has been transmitted "
    "anywhere; it exists only in this session until you copy or export it."
)


def _redact_taxa(names: list[str]) -> list[str]:
    return [f"Ingredient {i + 1} (name withheld)" for i in range(len(names))]


def _scrub(text: str, secrets: list[str]) -> str:
    """Remove the formulation's identifying names from a line of the packet.

    Redacting only the resolution log is not redaction. A rule statement
    interpolates the resolved taxa -- "the invention is based on biological
    resources obtained from India (Emblica officinalis, Terminalia
    bellirica...)" -- so the recipe walks straight back into the brief through
    the findings. Every string that identifies the product is removed from
    every line, not from the one line that obviously listed them.

    Longest first, so "Terminalia chebula" is removed before "Terminalia"
    would leave a dangling species epithet behind.
    """
    for s in sorted({s for s in secrets if s and len(s) > 3},
                    key=len, reverse=True):
        text = re.sub(re.escape(s), "[withheld]", text, flags=re.I)
    # Collapse the list punctuation the removals leave behind.
    text = re.sub(r"(?:\[withheld\])(?:[,;]\s*\[withheld\])+", "[withheld]",
                  text)
    return re.sub(r"\s+", " ", text).strip()


def assess(*, compile_result=None, answer=None, classification=None,
           session=None, user_asked: bool = False, redact: bool = False
           ) -> Referral:
    """Decide whether a human is needed, and assemble the brief if so.

    Every branch below reads a fact the system already produced. Nothing here
    infers, scores or estimates -- which is why the escalation is as auditable
    as the finding that caused it.
    """
    triggers: list[str] = []
    routing: list[str] = []
    established: list[str] = []
    open_q: list[str] = []
    cannot: list[str] = []
    citations: list[dict] = []
    obligations: list[str] = []
    subject = "IP and regulatory guidance for an Ayurvedic formulation"
    # Every string that identifies the product, collected as it is discovered
    # and applied to the whole packet at the end.
    secrets: list[str] = []

    if user_asked:
        triggers.append("USER_REQUESTED")

    # ---- from a compile -------------------------------------------------
    if compile_result is not None:
        cb = compile_result.cbom
        subject = ("Compliance review — formulation withheld" if redact
                   else f"Compliance review — {cb.formulation_name}")
        if redact:
            secrets.append(cb.formulation_name)
            secrets += [r["input"] for r in cb.resolution_log if r["input"]]
            secrets += [c for r in cb.resolution_log
                        for c in r.get("candidates", [])]
        taxa = [r["resolved_to"] for r in cb.resolution_log if r["resolved_to"]]
        if redact:
            secrets += taxa
        shown = _redact_taxa(taxa) if redact else taxa
        if shown:
            established.append("Resolved ingredients: " + ", ".join(shown))
        established.append(
            f"C-BOM digest {cb.digest()[:16]} · as of {cb.as_of} · "
            f"groundedness {cb.groundedness_score:.2f}")

        blockers = compile_result.blockers
        if blockers:
            triggers.append("BLOCKER_PRESENT")
        for f in cb.findings:
            lane_trigger = LANE_TRIGGER.get(f.lane)
            if lane_trigger and f.severity.value in ("BLOCKER", "WARNING"):
                if lane_trigger not in routing:
                    routing.append(lane_trigger)
            if f.severity.value == "BLOCKER":
                established.append(
                    f"[BLOCKER] {f.instrument} — {f.provision}: "
                    f"{_first_sentence(f.statement)}")
                if not any(a.available for a in f.autofix):
                    if "NO_FIX_AVAILABLE" not in triggers:
                        triggers.append("NO_FIX_AVAILABLE")
                    cannot.append(
                        f"No fix is available on these facts for "
                        f"{f.provision} ({f.instrument}). Clearing it is a "
                        f"judgement call for a person.")
            for c in f.citations:
                citations.append({
                    "corpus_id": c.corpus_id, "instrument": c.instrument,
                    "provision": c.provision, "pdf": c.source_pdf,
                    "page": c.page, "jurisdiction": c.jurisdiction,
                })
        for o in cb.obligations:
            obligations.append(
                f"{o.provision} — {o.duty.strip()} "
                f"(discharged by {o.discharged_by}; {o.when})")

        for r in cb.resolution_log:
            if not r["auto_accepted"]:
                if "AMBIGUOUS_TAXON" not in triggers:
                    triggers.append("AMBIGUOUS_TAXON")
                cands = " / ".join(r["candidates"]) or "no candidate"
                name = "an ingredient" if redact else r["input"]
                cannot.append(
                    f"{name} did not resolve to a single accepted taxon "
                    f"({cands}). Botanical synonymy is genuinely contested for "
                    f"several Ayurvedic drugs; a vaidya or a pharmacognosist "
                    f"should settle it, not a matcher.")

        for row in cb.jurisdiction_matrix:
            if "ABSTAIN" in row.patentability:
                if "FOREIGN_JURISDICTION" not in triggers:
                    triggers.append("FOREIGN_JURISDICTION")
                cannot.append(
                    f"{row.jurisdiction.value}: primary-source corpus for this "
                    f"jurisdiction is not ingested, so no position is stated. "
                    f"{row.next_action}")
        for note in cb.abstentions:
            cannot.append(note)
        if any("TKDL" in f.rule_id for f in cb.findings):
            triggers.append("TKDL_ADVERSE_OUTCOME")
        if compile_result.facts.as_dict().get("filing.intent") in (
                "FOREIGN_FIRST", "PCT"):
            triggers.append("FOREIGN_FILING")
        law_version = cb.law_version
    else:
        law_version = ""

    # ---- from a classification -----------------------------------------
    if classification is not None:
        if not classification.decided:
            triggers.append("CLASSIFICATION_UNDECIDED")
            open_q += list(classification.ask)
            cannot.append(
                "The regulatory category is still open. It decides the IP "
                "posture, so it has to be settled before the advice means "
                "anything.")
        else:
            cat = classification.category
            established.append(
                f"Regulatory category: {cat.label} — {classification.because}")
            if cat.uncited_authority:
                triggers.append("CLASSIFICATION_UNCITED")
                cannot.append(cat.uncited_authority.strip())
            if cat.id == "AHAARA" and "FOOD_POSITIONING" not in routing:
                routing.append("FOOD_POSITIONING")

    # ---- from a single answer ------------------------------------------
    if answer is not None:
        subject = answer.question or subject
        if answer.abstained:
            triggers.append("ABSTAINED")
            cannot.append(
                f"The assistant abstained on: “{answer.question}”. "
                f"{answer.abstain_reason}")
        else:
            established.append(
                f"Answered from the corpus at groundedness "
                f"{answer.groundedness:.2f}.")
            for c in answer.citations:
                citations.append({
                    "corpus_id": c.corpus_id, "instrument": c.instrument,
                    "provision": c.provision, "pdf": c.source_pdf,
                    "page": c.page, "jurisdiction": c.jurisdiction,
                })

    # De-duplicate while keeping first-seen order: the order is the order the
    # facts were established, which is the order a reader wants them in.
    triggers = list(dict.fromkeys(triggers))
    routing = list(dict.fromkeys(routing))
    seen_c: set[str] = set()
    uniq_c = []
    for c in citations:
        if c["corpus_id"] not in seen_c:
            seen_c.add(c["corpus_id"])
            uniq_c.append(c)

    # Redaction is applied LAST, to every free-text line at once. Doing it at
    # each source would mean remembering to do it at each new source, and the
    # one that got forgotten is the one that leaks.
    if redact and secrets:
        established = [_scrub(x, secrets) for x in established]
        cannot = [_scrub(x, secrets) for x in cannot]
        obligations = [_scrub(x, secrets) for x in obligations]
        open_q = [_scrub(x, secrets) for x in open_q]

    routes = load_registry().for_triggers(triggers + routing)
    return Referral(
        triggers=triggers, routes=routes, routing=routing, subject=subject,
        established=established, open_questions=open_q,
        could_not_determine=cannot, citations=uniq_c, obligations=obligations,
        redacted=redact, law_version=law_version,
    )


def _first_sentence(text: str, limit: int = 200) -> str:
    s = re.sub(r"\s+", " ", text).strip()
    m = re.search(r"(?<=[.;])\s", s)
    s = s[:m.start()] if m and m.start() < limit else s[:limit]
    return s.strip()


def render(ref: Referral) -> str:
    """The packet, as plain text the user can copy into an email.

    Plain text on purpose: it survives being pasted anywhere, it can be read on
    a phone, and it makes obvious that nothing was sent on the user's behalf.
    """
    if not ref.needed:
        return ("Nothing in this session needs a human yet: no blockers, no "
                "abstentions, and the regulatory category is settled. Ask for "
                "an escalation anyway and I will produce the packet.")

    L: list[str] = []
    L.append("REFERRAL TO A HUMAN IP FACILITATOR")
    L.append(f"Reference {ref.reference()} · generated {ref.as_of}")
    if ref.redacted:
        # Say precisely what redaction does and does not do. A privacy claim a
        # user over-reads is worse than one they can calibrate: the findings
        # still describe the formulation's legal characteristics, because a
        # brief with those removed would be no use to the facilitator.
        L.append("REDACTED — the product name, the ingredient names as you "
                 "typed them and their resolved botanical names have been "
                 "removed throughout. The findings still state the legal "
                 "characteristics of the formulation (for example that it "
                 "matches a documented classical combination), because a "
                 "referral without those is not actionable. Every citation "
                 "and the whole legal posture are unchanged.")
    L.append("")
    L.append(f"Subject: {ref.subject}")
    L.append("")

    L.append("WHY THIS IS BEING ESCALATED")
    for t in ref.triggers:
        L.append(f"  - {TRIGGERS[t]}")
    L.append("")

    if ref.routes:
        L.append("WHO TO TAKE IT TO")
        for r in ref.routes:
            L.append(f"  {r.label}")
            L.append(f"      {r.mandate}")
            if r.cited:
                L.append(f"      Established by: {r.citation}"
                         + (f"  [{r.pdf} p.{r.page}]" if r.pdf else "")
                         + ("  (background material, not law)"
                            if r.background else ""))
            elif r.uncited_authority:
                L.append(f"      No citation: {r.uncited_authority}")
            if r.site:
                L.append(f"      Official site: {r.site}")
            if r.contact and r.contact != "configure at deployment":
                L.append(f"      Contact: {r.contact}")
            if r.ask_for:
                L.append(f"      Take with you: {r.ask_for}")
            L.append("")

    if ref.established:
        L.append("WHAT THE SYSTEM DETERMINED")
        for e in ref.established:
            L.append(f"  - {e}")
        L.append("")

    if ref.obligations:
        L.append("OBLIGATIONS ALREADY IDENTIFIED")
        for o in ref.obligations:
            L.append(f"  - {o}")
        L.append("")

    if ref.could_not_determine:
        L.append("WHAT IT COULD NOT DETERMINE, AND WHY")
        for c in ref.could_not_determine:
            L.append(f"  - {c}")
        L.append("")

    if ref.open_questions:
        L.append("QUESTIONS STILL OPEN")
        for q in ref.open_questions:
            L.append(f"  - {q}")
        L.append("")

    if ref.citations:
        L.append("AUTHORITY RELIED ON")
        for c in ref.citations:
            tail = f"  [{c['pdf']} p.{c['page']}]" if c.get("pdf") else ""
            L.append(f"  - {c['instrument']} — {c['provision']} "
                     f"({c['jurisdiction']}){tail}")
        L.append("")

    if ref.law_version:
        L.append(f"Corpus: {ref.law_version}")
    L.append(PRIVACY_NOTE)
    L.append("")
    L.append(DISCLAIMER)
    return "\n".join(L)


def payload(ref: Referral) -> dict:
    """JSON shape for the web UI."""
    return {
        "needed": ref.needed,
        "reference": ref.reference() if ref.needed else "",
        "subject": ref.subject,
        "redacted": ref.redacted,
        "triggers": [{"id": t, "why": TRIGGERS[t]} for t in ref.triggers],
        "routing": list(ref.routing),
        "routes": [{
            "id": r.id, "label": r.label, "mandate": r.mandate,
            "citation": r.citation, "pdf": r.pdf, "page": r.page,
            "background": r.background, "site": r.site,
            "uncited": r.uncited_authority, "ask_for": r.ask_for,
            "contact": r.contact,
        } for r in ref.routes],
        "established": ref.established,
        "open_questions": ref.open_questions,
        "could_not_determine": ref.could_not_determine,
        "obligations": ref.obligations,
        "citations": ref.citations,
        "text": render(ref),
    }
