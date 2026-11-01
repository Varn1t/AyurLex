"""SUTRA loader: YAML rules -> validated, corpus-bound Rule objects.

The load step is a gate, not a parse. A rule is admitted only if:
  * every citation it declares resolves to a real provision in the ingested
    corpus, and
  * every anchor phrase it declares is a verbatim substring of that provision.

A rule that fails either check is demoted to UNVERIFIED and the engine refuses
to let it emit. That is the mechanism that makes a hallucinated section number
structurally impossible rather than merely unlikely: there is no code path from
a rule file to a Finding that does not pass through the primary source text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from core.schema import CitationKind, Severity, VerificationStatus
from samhita.index import Corpus, load_corpus

ROOT = Path(__file__).resolve().parent.parent
RULES_DIR = ROOT / "sutra" / "rules"


def _norm(s: str) -> str:
    """Whitespace-insensitive comparison. PDF extraction inserts line breaks
    mid-sentence, so an anchor must match on words, not on layout."""
    return re.sub(r"\s+", " ", s).strip().lower()


@dataclass
class RuleCitation:
    kind: CitationKind
    corpus_id: str
    provision: str
    anchor: str
    clause: str | None = None
    from_fact: str | None = None
    # Filled during verification.
    verified: bool = False
    quote: str = ""
    problem: str = ""


@dataclass
class RuleAutofix:
    id: str
    description: str
    sets_facts: dict[str, Any] = field(default_factory=dict)
    preconditions: list[dict[str, Any]] = field(default_factory=list)
    expected_effect: str = ""
    emits_protocol: str | None = None


@dataclass
class Rule:
    id: str
    jurisdiction: str
    instrument: str
    provision: str
    severity: Severity
    lane: str
    when: dict[str, Any]
    statement_template: str
    citations: list[RuleCitation]
    autofix: list[RuleAutofix] = field(default_factory=list)
    obligation: dict[str, Any] | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    test_cases: list[dict[str, Any]] = field(default_factory=list)
    source_file: str = ""
    verification: VerificationStatus = VerificationStatus.UNVERIFIED
    verification_notes: list[str] = field(default_factory=list)

    def in_force(self, on: date) -> bool:
        if self.effective_from and on < self.effective_from:
            return False
        if self.effective_to and on >= self.effective_to:
            return False
        return True


class RuleLoadError(RuntimeError):
    pass


def _as_date(v: Any) -> date | None:
    if v in (None, "null", ""):
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


def parse_rule(raw: dict, source: str) -> Rule:
    required = ("id", "jurisdiction", "instrument", "provision", "severity",
                "when", "statement_template", "citations")
    missing = [k for k in required if k not in raw]
    if missing:
        raise RuleLoadError(f"{source}: rule {raw.get('id','?')} missing {missing}")

    cits = []
    for c in raw["citations"]:
        cits.append(
            RuleCitation(
                kind=CitationKind(c.get("kind", "STATUTE")),
                corpus_id=c["corpus_id"],
                provision=c.get("provision", raw["provision"]),
                anchor=c["anchor"],
                clause=c.get("clause"),
                from_fact=c.get("from_fact"),
            )
        )
    fixes = [
        RuleAutofix(
            id=a["id"],
            description=a["description"].strip(),
            sets_facts=a.get("sets_facts", {}) or {},
            preconditions=a.get("preconditions", []) or [],
            expected_effect=a.get("expected_effect", ""),
            emits_protocol=a.get("emits_protocol"),
        )
        for a in raw.get("autofix", []) or []
    ]
    return Rule(
        id=raw["id"],
        jurisdiction=raw["jurisdiction"],
        instrument=raw["instrument"],
        provision=raw["provision"],
        severity=Severity(raw["severity"]),
        lane=raw.get("lane", "OTHER"),
        when=raw["when"],
        statement_template=" ".join(raw["statement_template"].split()),
        citations=cits,
        autofix=fixes,
        obligation=raw.get("obligation"),
        effective_from=_as_date(raw.get("effective_from")),
        effective_to=_as_date(raw.get("effective_to")),
        test_cases=raw.get("test_cases", []) or [],
        source_file=source,
    )


def verify_rule(rule: Rule, corpus: Corpus) -> Rule:
    """Bind every declared citation to primary-source text."""
    ok = True
    for c in rule.citations:
        if c.from_fact:
            # Resolved at emit time from a fact (e.g. a prior-art hit). Its
            # authority is the fact's own provenance, checked by PRAMANA.
            c.verified = True
            continue
        if not corpus.has(c.corpus_id):
            c.problem = f"corpus_id {c.corpus_id} not in corpus"
            rule.verification_notes.append(c.problem)
            ok = False
            continue
        text = corpus.clause_text(c.corpus_id, c.clause)
        if _norm(c.anchor) not in _norm(text):
            whole = corpus.get(c.corpus_id)["text"]
            if _norm(c.anchor) in _norm(whole):
                # Anchor is in the section but not in the pin-cited clause.
                c.quote = c.anchor
                c.verified = True
                rule.verification_notes.append(
                    f"{c.corpus_id}: anchor found in section but not in "
                    f"clause ({c.clause}); pin-cite widened to the section"
                )
                c.clause = None
                continue
            c.problem = (
                f"anchor not found in {c.corpus_id}"
                f"{'(' + c.clause + ')' if c.clause else ''}: {c.anchor[:60]!r}"
            )
            rule.verification_notes.append(c.problem)
            ok = False
            continue
        c.quote = c.anchor
        c.verified = True

    if not rule.test_cases:
        rule.verification_notes.append("no test_cases declared")
        ok = False
    rule.verification = (
        VerificationStatus.VERIFIED if ok else VerificationStatus.UNVERIFIED
    )
    return rule


def load_rules(rules_dir: Path = RULES_DIR, corpus: Corpus | None = None
               ) -> list[Rule]:
    corpus = corpus or load_corpus()
    rules: list[Rule] = []
    seen: set[str] = set()
    for path in sorted(rules_dir.glob("*.yaml")):
        docs = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        if not isinstance(docs, list):
            raise RuleLoadError(f"{path.name}: expected a list of rules")
        for raw in docs:
            rule = verify_rule(parse_rule(raw, path.name), corpus)
            if rule.id in seen:
                raise RuleLoadError(f"duplicate rule id {rule.id}")
            seen.add(rule.id)
            rules.append(rule)
    return rules
