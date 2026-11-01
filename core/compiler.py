"""The compiler: Formulation -> C-BOM.

Pipeline, in order, with the LLM appearing nowhere in it:

    resolve -> facts -> SUTRA rules -> PRAMANA gate -> SETU matrix -> C-BOM

Recompilation with an autofix applied runs the identical pipeline over a
patched fact table, so "this fix clears the blocker" is a claim the compiler
proves rather than asserts.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from core.resolver import Resolution, load_resolver
from core.schema import (
    CBOM,
    Autofix,
    Finding,
    Formulation,
    Obligation,
    Severity,
)
from pramana.verify import VerificationReport, check_citation_integrity, verify_all
from samhita.index import Corpus, load_corpus
from setu.matrix import build_matrix
from sutra.engine import evaluate
from sutra.facts import FactTable, build_facts
from sutra.loader import Rule, load_rules

LAW_VERSION = "corpus/provisions.jsonl @ ingest"


@dataclass
class CompileResult:
    cbom: CBOM
    facts: FactTable
    resolutions: list[Resolution]
    reports: list[VerificationReport] = field(default_factory=list)
    fired: list[str] = field(default_factory=list)
    suppressed: list[tuple[str, str]] = field(default_factory=list)
    integrity_problems: list[str] = field(default_factory=list)

    @property
    def blockers(self) -> list[Finding]:
        return [f for f in self.cbom.findings if f.severity is Severity.BLOCKER]


def resolve_ingredients(f: Formulation) -> list[Resolution]:
    r = load_resolver()
    out = []
    for ing in f.ingredients:
        res = r.resolve(ing.raw_name)
        # Write the resolution back onto the ingredient so the C-BOM carries it.
        ing.canonical_taxon = res.taxon
        ing.resolution_path = res.path
        ing.resolution_confidence = res.confidence
        ing.candidates = res.candidates
        if res.record:
            ing.schedule_flags = res.record.get("schedule_flags", [])
            ing.synonyms = res.record.get("translit", [])[:5]
            if ing.is_from_indian_bioresource is None:
                ing.is_from_indian_bioresource = res.record.get(
                    "indian_bioresource", False
                )
        out.append(res)
    return out


def resolution_log(resolutions: list[Resolution]) -> list[dict[str, Any]]:
    return [
        {
            "input": r.raw_name,
            "resolved_to": r.taxon,
            "path": r.path,
            "confidence": r.confidence,
            "matched_alias": r.matched_alias,
            "candidates": r.candidates,
            "auto_accepted": r.is_accepted,
        }
        for r in resolutions
    ]


def compile_formulation(
    formulation: Formulation,
    *,
    as_of: date,
    rules: list[Rule] | None = None,
    corpus: Corpus | None = None,
    fact_overrides: dict[str, Any] | None = None,
    allow_unverified: bool = False,
) -> CompileResult:
    corpus = corpus or load_corpus()
    rules = rules if rules is not None else load_rules(corpus=corpus)

    f = formulation.model_copy(deep=True)
    resolutions = resolve_ingredients(f)
    facts = build_facts(f, resolutions)

    # Autofix recompilation patches facts rather than re-deriving them, so the
    # before/after diff isolates exactly what the fix changed.
    if fact_overrides:
        for k, v in fact_overrides.items():
            facts.set(k, v, why="applied by autofix")

    engine = evaluate(rules, facts, as_of=as_of, corpus=corpus,
                      allow_unverified=allow_unverified)

    kept, reports, groundedness = verify_all(engine.findings, facts.as_dict())
    suppressed = list(engine.suppressed)
    for f_, rep in zip(engine.findings, reports):
        if not rep.kept:
            suppressed.append((f_.rule_id, "PRAMANA: no sentence survived the gate"))

    kept_ids = {k.rule_id for k in kept}
    obligations: list[Obligation] = [
        o for o in engine.obligations if o.id.removeprefix("O-") in kept_ids
    ]

    problems = check_citation_integrity(kept, corpus)

    cbom = CBOM(
        formulation_name=f.name,
        formulation_fingerprint=f.fingerprint(),
        as_of=as_of,
        law_version=LAW_VERSION,
        resolution_log=resolution_log(resolutions),
        findings=kept,
        obligations=obligations,
        jurisdiction_matrix=build_matrix(f, kept, facts),
        groundedness_score=groundedness,
        suppressed_count=len(suppressed),
        abstentions=engine.abstentions,
    )
    return CompileResult(
        cbom=cbom, facts=facts, resolutions=resolutions, reports=reports,
        fired=engine.fired, suppressed=suppressed, integrity_problems=problems,
    )


def apply_autofix(
    formulation: Formulation,
    fix: Autofix,
    *,
    as_of: date,
    base_overrides: dict[str, Any] | None = None,
    **kw: Any,
) -> tuple[CompileResult, dict[str, Any]]:
    """Recompile with a fix applied. Returns the new result and the merged
    override set, so a chain of fixes can be applied one after another."""
    overrides = dict(base_overrides or {})
    overrides.update(fix.sets_facts)
    return compile_formulation(formulation, as_of=as_of,
                               fact_overrides=overrides, **kw), overrides


def diff_findings(before: CompileResult, after: CompileResult) -> dict[str, list[str]]:
    b = {f.rule_id for f in before.cbom.findings}
    a = {f.rule_id for f in after.cbom.findings}
    return {
        "cleared": sorted(b - a),
        "introduced": sorted(a - b),
        "unchanged": sorted(a & b),
    }
