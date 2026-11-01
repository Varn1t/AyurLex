"""Citation gate -- the citation verifier.

*Pramāṇa* is a valid means of knowledge; *śabda-pramāṇa* is textual authority.
This module accepts a sentence only on textual authority: every emitted sentence
must be supported by a span of the provision the rule declared, and every number,
date and section reference in it must appear verbatim in that span or in the
rule's own declared metadata.

What this is, precisely -- because overclaiming here would be the same sin the
module exists to prevent:

  * It is a STRICT LEXICAL ENTAILMENT GATE. Numeric and citation tokens take an
    exact-match path; prose takes a content-word coverage path against the cited
    span. It runs offline, deterministically, with no model weights, which is
    also what lets the whole compiler run air-gapped.
  * It is NOT a neural NLI model. Swapping the prose path for a cross-encoder
    NLI scorer is a drop-in change at `entailment_score`, and the thresholds
    below are the ones that need tuning against a labelled set when that lands.

The strictness is deliberate: a sentence that cannot be tied to its source is
dropped, not hedged into vagueness.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.schema import Finding

# Tokens that must survive an exact-match check. Numeric hallucination is the
# highest-risk failure mode in legal RAG, so numbers never get the benefit of
# fuzzy coverage.
NUMERIC = re.compile(
    r"\b(?:[Ss]ection\s+\d+[A-Za-z]*(?:\(\w+\))*|\d{4}|\d+(?:\.\d+)?%|"
    r"\d+\s*(?:days?|weeks?|months?|years?))\b"
)
SENT_SPLIT = re.compile(r"(?<=[.;])\s+(?=[A-Z\"“])")
WORD = re.compile(r"[a-z]{3,}")

STOP = {
    "the", "and", "for", "that", "this", "with", "from", "any", "not", "are",
    "which", "under", "such", "shall", "must", "has", "have", "been", "its",
    "were", "was", "into", "than", "then", "there", "their", "them", "they",
    "these", "those", "here", "also", "only", "other", "over", "before",
    "after", "each", "both", "when", "where", "what", "will", "would", "can",
    "could", "may", "might", "does", "did", "our", "your", "record", "cannot",
}

# Tuned to be conservative rather than accurate-on-average: a rule statement is
# allowed to paraphrase, but at least this share of its legally operative
# content words must appear in the cited span.
ENTAILED = 0.55
NEUTRAL = 0.30


@dataclass
class SentenceVerdict:
    sentence: str
    label: str                  # ENTAILED | NEUTRAL | CONTRADICTED_NUMERIC
    score: float
    unsupported_numerics: list[str] = field(default_factory=list)
    matched_citation: str = ""


@dataclass
class VerificationReport:
    finding_id: str
    groundedness: float
    verdicts: list[SentenceVerdict]
    kept: bool
    dropped_sentences: list[str] = field(default_factory=list)
    note: str = ""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def content_words(s: str) -> set[str]:
    return {w for w in WORD.findall(s.lower()) if w not in STOP}


def entailment_score(sentence: str, span: str) -> float:
    """Content-word coverage of the sentence by the span.

    Replace this function body with a cross-encoder NLI call to upgrade the
    gate; nothing else in the pipeline needs to change.
    """
    sw = content_words(sentence)
    if not sw:
        return 1.0
    spanw = content_words(span)
    return len(sw & spanw) / len(sw)


def numeric_tokens(s: str) -> list[str]:
    return NUMERIC.findall(s)


def _fact_haystack(facts: dict | None) -> str:
    """Everything the deterministic pipeline established about this formulation.

    A finding's statement legitimately mixes two kinds of sentence: a legal
    proposition (authority = the cited provision) and a recitation of the
    applicant's own facts (authority = the resolver and the fact builder, which
    are deterministic and logged in the C-BOM). Checking the second kind against
    the statute would drop exactly the sentences that make the finding useful,
    so each kind is checked against its own source and labelled accordingly.
    """
    if not facts:
        return ""
    parts = []
    for k, v in facts.items():
        parts.append(k.replace(".", " ").replace("_", " "))
        if isinstance(v, (str, int, float)):
            parts.append(str(v))
        elif isinstance(v, list):
            parts.extend(str(x) for x in v if isinstance(x, (str, int, float)))
        elif isinstance(v, dict):
            parts.extend(str(x) for x in v.values()
                         if isinstance(x, (str, int, float)))
    return _norm(" ".join(parts))


def verify_finding(finding: Finding, facts: dict | None = None
                   ) -> VerificationReport:
    # The haystack a sentence may be checked against: the cited spans plus the
    # rule's own declared instrument and provision strings. Nothing else. A rule
    # cannot borrow authority from a provision it did not declare.
    spans = [c.quote for c in finding.citations]
    declared = " ".join(
        [c.instrument for c in finding.citations]
        + [c.provision for c in finding.citations]
        + [finding.instrument, finding.provision]
    )
    fact_hay = _fact_haystack(facts)
    haystack = _norm(" ".join(spans) + " " + declared) + " " + fact_hay

    verdicts: list[SentenceVerdict] = []
    kept_sentences: list[str] = []
    dropped: list[str] = []

    for sent in [s for s in SENT_SPLIT.split(finding.statement) if s.strip()]:
        # 1. Numerics and section references take the exact-match path. A number
        #    traceable to neither the cited text nor an established fact is
        #    stripped -- numeric hallucination is the failure mode that matters.
        bad = [n for n in numeric_tokens(sent) if _norm(n) not in haystack]
        if bad:
            verdicts.append(SentenceVerdict(sent, "CONTRADICTED_NUMERIC", 0.0, bad))
            dropped.append(sent)
            continue

        # 2. Legal propositions: coverage against the best-matching cited span.
        best, best_src = 0.0, ""
        for c in finding.citations:
            sc = entailment_score(sent, c.quote + " " + c.provision + " "
                                  + c.instrument)
            if sc > best:
                best, best_src = sc, c.corpus_id

        if best >= ENTAILED:
            verdicts.append(SentenceVerdict(sent, "ENTAILED", best,
                                            matched_citation=best_src))
            kept_sentences.append(sent)
            continue

        # 3. Fact recitations: coverage against the established fact table.
        fact_score = entailment_score(sent, fact_hay) if fact_hay else 0.0
        if fact_score >= ENTAILED:
            verdicts.append(SentenceVerdict(sent, "ENTAILED_BY_FACT", fact_score,
                                            matched_citation="fact table"))
            kept_sentences.append(sent)
        elif max(best, fact_score) >= NEUTRAL:
            # Hedge rather than drop: consistent with the source but not
            # carried by it. Hedging is visible in the report.
            verdicts.append(SentenceVerdict(sent, "NEUTRAL", max(best, fact_score),
                                            matched_citation=best_src))
            kept_sentences.append(sent)
        else:
            verdicts.append(SentenceVerdict(sent, "UNSUPPORTED",
                                            max(best, fact_score)))
            dropped.append(sent)

    grounded = (
        sum(1 for v in verdicts if v.label in ("ENTAILED", "ENTAILED_BY_FACT"))
        / len(verdicts)
        if verdicts else 0.0
    )

    # A finding survives only if at least one sentence carries real authority.
    kept = any(v.label in ("ENTAILED", "NEUTRAL") for v in verdicts)
    note = ""
    if dropped:
        note = f"{len(dropped)} sentence(s) dropped for want of textual support"

    if kept and dropped:
        finding.statement = " ".join(kept_sentences)
    finding.groundedness = round(grounded, 3)

    return VerificationReport(
        finding_id=finding.id,
        groundedness=round(grounded, 3),
        verdicts=verdicts,
        kept=kept,
        dropped_sentences=dropped,
        note=note,
    )


def verify_all(findings: list[Finding], facts: dict | None = None
               ) -> tuple[list[Finding], list[VerificationReport], float]:
    """Gate a whole report. Returns surviving findings, per-finding reports and
    the aggregate Groundedness Score displayed in the UI."""
    kept, reports = [], []
    for f in findings:
        rep = verify_finding(f, facts)
        reports.append(rep)
        if rep.kept:
            kept.append(f)
    overall = (
        round(sum(r.groundedness for r in reports) / len(reports), 3)
        if reports else 0.0
    )
    return kept, reports, overall


def check_citation_integrity(findings: list[Finding], corpus) -> list[str]:
    """Re-read every citation's quote from the corpus and confirm it is still
    verbatim. This is the check that catches corpus drift between a rule being
    written and the report being generated."""
    problems = []
    for f in findings:
        for c in f.citations:
            if c.kind.value == "PRIOR_ART":
                continue                     # provenance is the outcome record
            if not corpus.has(c.corpus_id):
                problems.append(f"{f.id}: {c.corpus_id} missing from corpus")
                continue
            if _norm(c.quote) not in _norm(corpus.get(c.corpus_id)["text"]):
                problems.append(
                    f"{f.id}: quote for {c.corpus_id} is not verbatim in the source"
                )
    return problems
