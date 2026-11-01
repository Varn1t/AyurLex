"""SUTRA engine: evaluate rules against facts, emit Findings.

The whole legal outcome surface of the product is this file plus the YAML. No
prompt decides whether a provision is triggered; a predicate does. That is what
makes the output auditable, reproducible and diffable -- and auditability is
the entire point.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from core.schema import (
    Autofix,
    Citation,
    CitationKind,
    Finding,
    Jurisdiction,
    Obligation,
    Severity,
    VerificationStatus,
)
from samhita.index import Corpus, load_corpus
from sutra.facts import FactTable
from sutra.loader import Rule, RuleAutofix, RuleCitation

_TEMPLATE = re.compile(r"\{\{\s*([a-zA-Z0-9_.\[\]]+)\s*\}\}")


class MissingFact(KeyError):
    """A template referenced a fact that was never established. This is a
    defect in the rule, and it fails loudly rather than rendering 'None'."""


# --------------------------------------------------------------- predicates --
def _resolve_path(facts: dict[str, Any], path: str) -> Any:
    if path in facts:
        return facts[path]
    # Support one level of drill-down into a dict-valued fact:
    # "prior_art.tkdl_top.application_no"
    for i in range(len(path), 0, -1):
        if path[:i] in facts and path[i : i + 1] == ".":
            obj = facts[path[:i]]
            for key in path[i + 1 :].split("."):
                if isinstance(obj, dict) and key in obj:
                    obj = obj[key]
                else:
                    raise MissingFact(path)
            return obj
    raise MissingFact(path)


def _test(cond: dict[str, Any], facts: dict[str, Any]) -> bool:
    if "all" in cond:
        return all(_test(c, facts) for c in cond["all"])
    if "any" in cond:
        return any(_test(c, facts) for c in cond["any"])
    if "not" in cond:
        return not _test(cond["not"], facts)

    path = cond["fact"]
    try:
        val = _resolve_path(facts, path)
    except MissingFact:
        # An unestablished fact cannot satisfy a condition. Abstain.
        return False

    if "eq" in cond:
        return val == cond["eq"]
    if "ne" in cond:
        return val != cond["ne"]
    if "in" in cond:
        return val in cond["in"]
    if "not_in" in cond:
        return val not in cond["not_in"]
    if "gte" in cond:
        return val is not None and val >= cond["gte"]
    if "lte" in cond:
        return val is not None and val <= cond["lte"]
    if "gt" in cond:
        return val is not None and val > cond["gt"]
    if "lt" in cond:
        return val is not None and val < cond["lt"]
    if "is_null" in cond:
        return (val is None) == bool(cond["is_null"])
    if "truthy" in cond:
        return bool(val) == bool(cond["truthy"])
    if "contains" in cond:
        return bool(val) and cond["contains"] in val
    raise ValueError(f"unsupported condition: {cond}")


# ----------------------------------------------------------------- render ---
def render(template: str, facts: dict[str, Any]) -> str:
    def sub(m: re.Match) -> str:
        path = m.group(1)
        val = _resolve_path(facts, path)          # raises if absent, by design
        if isinstance(val, list):
            return ", ".join(str(x) for x in val)
        return str(val)

    return re.sub(r"\s+", " ", _TEMPLATE.sub(sub, template)).strip()


# ------------------------------------------------------------- citations ----
def build_citation(rc: RuleCitation, facts: dict[str, Any],
                   corpus: Corpus) -> Citation | None:
    if rc.from_fact:
        obj = None
        try:
            obj = _resolve_path(facts, rc.from_fact)
        except MissingFact:
            return None
        if not isinstance(obj, dict):
            return None
        # A prior-art hit carries its own provenance back to the source PDF.
        return Citation(
            kind=CitationKind.PRIOR_ART,
            corpus_id=obj.get("id", "TKDL.OUT::unknown"),
            instrument="TKDL prior-art outcome record",
            provision=f"Application {obj.get('application_no','?')} "
                      f"({obj.get('outcome','?')})",
            quote=obj.get("title", "")[:400] or "untitled record",
            hierarchy_path="About TKDL > Annexure > "
                           f"{obj.get('outcome','record')}",
            source_pdf=obj.get("source_pdf", ""),
            page=obj.get("page", 0),
            authority_rank=obj.get("authority_rank", 4),
        )

    rec = corpus.get(rc.corpus_id)
    return Citation(
        kind=rc.kind,
        corpus_id=rc.corpus_id,
        instrument=rec["act_title"],
        provision=rc.provision,
        quote=corpus.clause_text(rc.corpus_id, rc.clause).strip(),
        hierarchy_path=rec["hierarchy_path"]
        + (f" > clause ({rc.clause})" if rc.clause else ""),
        source_pdf=rec["source_pdf"],
        page=rec["page_start"],
        retrieved_on=rec["retrieved_on"],
        authority_rank=rec["authority_rank"],
    )


def build_autofixes(rule: Rule, facts: dict[str, Any]) -> list[Autofix]:
    out = []
    for a in rule.autofix:
        ok, why = True, ""
        for pre in a.preconditions:
            if not _test(pre, facts):
                ok = False
                why = f"precondition not met: {pre.get('fact', pre)}"
                break
        out.append(
            Autofix(
                id=a.id,
                description=" ".join(a.description.split()),
                sets_facts=a.sets_facts,
                preconditions=a.preconditions,
                expected_effect=a.expected_effect,
                emits_protocol=a.emits_protocol,
                available=ok,
                unavailable_reason=why,
            )
        )
    return out


# -------------------------------------------------------------- evaluate ----
class EngineResult:
    def __init__(self) -> None:
        self.findings: list[Finding] = []
        self.obligations: list[Obligation] = []
        self.fired: list[str] = []
        self.suppressed: list[tuple[str, str]] = []
        self.abstentions: list[str] = []


def evaluate(
    rules: list[Rule],
    facts: FactTable,
    *,
    as_of: date,
    corpus: Corpus | None = None,
    allow_unverified: bool = False,
) -> EngineResult:
    corpus = corpus or load_corpus()
    fv = facts.as_dict()
    res = EngineResult()

    for rule in sorted(rules, key=lambda r: r.id):
        if not rule.in_force(as_of):
            continue
        if not _test(rule.when, fv):
            continue

        res.fired.append(rule.id)

        if rule.verification is VerificationStatus.UNVERIFIED and not allow_unverified:
            res.suppressed.append(
                (rule.id, "rule is UNVERIFIED: "
                          + "; ".join(rule.verification_notes[:2]))
            )
            res.abstentions.append(
                f"{rule.id} matched the facts but is not promoted to VERIFIED, "
                f"so no finding was emitted."
            )
            continue

        cits = [c for c in (build_citation(rc, fv, corpus)
                            for rc in rule.citations) if c is not None]
        if not cits:
            res.suppressed.append((rule.id, "no citation could be resolved"))
            res.abstentions.append(
                f"{rule.id} matched but its authority could not be resolved "
                f"against the corpus; suppressed rather than asserted."
            )
            continue

        try:
            statement = render(rule.statement_template, fv)
        except MissingFact as e:
            res.suppressed.append((rule.id, f"template referenced absent fact {e}"))
            continue

        finding = Finding(
            id=f"F-{rule.id}",
            severity=rule.severity,
            rule_id=rule.id,
            jurisdiction=Jurisdiction(rule.jurisdiction),
            instrument=rule.instrument,
            provision=rule.provision,
            statement=statement,
            citations=cits,
            autofix=build_autofixes(rule, fv),
            as_of=as_of,
            verification=rule.verification,
            lane=rule.lane,
        )
        res.findings.append(finding)

        if rule.obligation:
            o = rule.obligation
            res.obligations.append(
                Obligation(
                    id=f"O-{rule.id}",
                    jurisdiction=Jurisdiction(rule.jurisdiction),
                    instrument=rule.instrument,
                    provision=rule.provision,
                    duty=render(o["duty"], fv),
                    discharged_by=o.get("discharged_by", "See provision"),
                    when=o.get("when", "before filing"),
                    citations=cits,
                )
            )

    order = {Severity.BLOCKER: 0, Severity.WARNING: 1,
             Severity.OPPORTUNITY: 2, Severity.INFO: 3}
    res.findings.sort(key=lambda f: (order[f.severity], f.rule_id))
    return res
