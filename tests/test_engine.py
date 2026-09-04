"""Tests for the compiler core.

The important one is test_rule_declared_test_cases: every SUTRA rule declares
fixtures it must and must not fire on, and this test runs all of them. A rule
that ships without test cases is already refused at load time (it cannot reach
VERIFIED), so this closes the loop -- CI fails if a rule's behaviour drifts.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.compiler import apply_autofix, compile_formulation, diff_findings  # noqa: E402
from core.resolver import load_resolver  # noqa: E402
from core.schema import (  # noqa: E402
    Citation,
    CitationKind,
    Finding,
    Formulation,
    Jurisdiction,
    Severity,
)
from samhita.index import load_corpus  # noqa: E402
from sutra.loader import load_rules  # noqa: E402

AS_OF = date(2026, 8, 31)


@pytest.fixture(scope="session")
def corpus():
    return load_corpus()


@pytest.fixture(scope="session")
def rules(corpus):
    return load_rules(corpus=corpus)


def load_fixture(name: str) -> Formulation:
    return Formulation.model_validate_json(
        (ROOT / name).read_text(encoding="utf-8")
    )


# ------------------------------------------------------------- structure ---
def test_finding_without_citation_is_unserialisable():
    """The single structural guarantee of the whole system."""
    with pytest.raises(ValueError, match="zero citations"):
        Finding(
            id="F-TEST", severity=Severity.BLOCKER, rule_id="TEST",
            jurisdiction=Jurisdiction.IN, instrument="X", provision="Y",
            statement="A confident assertion with no authority behind it.",
            citations=[], as_of=AS_OF,
        )


def test_citation_requires_structured_corpus_id():
    with pytest.raises(ValueError, match="corpus_id"):
        Citation(kind=CitationKind.STATUTE, corpus_id="not-a-real-id",
                 instrument="X", provision="Y", quote="long enough quote text")


# ----------------------------------------------------------------- rules ---
def test_all_rules_verified_against_primary_sources(rules):
    unverified = [(r.id, r.verification_notes) for r in rules
                  if r.verification.value != "VERIFIED"]
    assert not unverified, f"rules not bound to primary sources: {unverified}"


def test_every_rule_declares_test_cases(rules):
    assert rules, "no rules loaded"
    for r in rules:
        assert r.test_cases, f"{r.id} ships without test cases"


def test_every_rule_anchor_is_verbatim_in_the_source(rules, corpus):
    """Re-read each anchor from the corpus. This is the check that catches a
    provision number that was right once and is wrong now."""
    import re

    def norm(s):
        return re.sub(r"\s+", " ", s).strip().lower()

    for r in rules:
        for c in r.citations:
            if c.from_fact:
                continue
            assert corpus.has(c.corpus_id), f"{r.id}: {c.corpus_id} missing"
            assert norm(c.anchor) in norm(corpus.get(c.corpus_id)["text"]), (
                f"{r.id}: anchor is not verbatim in {c.corpus_id}"
            )


def _cases(rules):
    for r in rules:
        for tc in r.test_cases:
            yield pytest.param(r.id, tc["fixture"], tc["expect_fires"],
                               id=f"{r.id}::{Path(tc['fixture']).stem}")


def test_rule_declared_test_cases(rules, corpus):
    failures = []
    for rule_id, fixture, expect in [(p.values[0], p.values[1], p.values[2])
                                     for p in _cases(rules)]:
        result = compile_formulation(load_fixture(fixture), as_of=AS_OF,
                                     rules=rules, corpus=corpus)
        fired = rule_id in result.fired
        if fired != expect:
            failures.append(
                f"{rule_id} on {fixture}: expected fires={expect}, got {fired}"
            )
    assert not failures, "\n".join(failures)


# ------------------------------------------------------------ as_of gate ---
def test_as_of_filters_rules_not_yet_in_force(rules, corpus):
    """s.3(p) was inserted w.e.f. 20-5-2003 -- the date is read from the
    amendment footnote in the shipped PDF, not from anyone's memory."""
    f = load_fixture("fixtures/triphala_classical.json")
    before = compile_formulation(f, as_of=date(2003, 5, 19), rules=rules,
                                 corpus=corpus)
    after = compile_formulation(f, as_of=date(2003, 5, 20), rules=rules,
                                corpus=corpus)
    assert "IN.PAT.S3P.TK_EXCLUSION" not in before.fired
    assert "IN.PAT.S3P.TK_EXCLUSION" in after.fired


def test_time_travel_diff_is_directional(rules, corpus):
    f = load_fixture("fixtures/foreign_first_no_permit.json")
    early = compile_formulation(f, as_of=date(2002, 1, 1), rules=rules, corpus=corpus)
    late = compile_formulation(f, as_of=AS_OF, rules=rules, corpus=corpus)
    d = diff_findings(early, late)
    assert "IN.PAT.S39.FOREIGN_FILING_PERMISSION" in d["introduced"]
    assert not d["cleared"]


# ------------------------------------------------------------- resolver ----
def test_resolver_lands_every_script_on_one_taxon():
    r = load_resolver()
    for name in ["गुडूची", "Giloy", "Amrutha", "guduchi", "Guḍūcī",
                 "Tinospora cordifolia", "gulvel"]:
        assert r.resolve(name).taxon == "Tinospora cordifolia", name


def test_resolver_refuses_to_guess_a_contested_name():
    """Brahmi denotes Bacopa in some regions and Centella in others. Guessing
    would be worse than abstaining."""
    res = load_resolver().resolve("Brahmi")
    assert res.taxon is None
    assert res.path == "AMBIGUOUS"
    assert set(res.candidates) == {"Bacopa monnieri", "Centella asiatica"}


def test_fuzzy_match_is_proposed_not_accepted():
    res = load_resolver().resolve("Ashwagndha")
    assert res.path == "FUZZY_PROPOSED"
    assert res.taxon is None
    assert not res.is_accepted
    assert "Withania somnifera" in res.candidates


# -------------------------------------------------------------- pramana ----
def test_pramana_strips_an_untraceable_number(corpus):
    from pramana.verify import verify_finding

    rec = corpus.get("IN.PATENTS.1970::S3")
    f = Finding(
        id="F-X", severity=Severity.BLOCKER, rule_id="X",
        jurisdiction=Jurisdiction.IN, instrument="The Patents Act, 1970",
        provision="Section 3(p)",
        statement=(
            "Traditional knowledge is not an invention. "
            "The applicant must pay a fee within 47 days of the notice."
        ),
        citations=[Citation(
            kind=CitationKind.STATUTE, corpus_id="IN.PATENTS.1970::S3",
            instrument="The Patents Act, 1970", provision="Section 3(p)",
            quote=rec["clauses"]["p"],
        )],
        as_of=AS_OF,
    )
    rep = verify_finding(f)
    labels = {v.label for v in rep.verdicts}
    assert "CONTRADICTED_NUMERIC" in labels
    assert "47 days" not in f.statement


def test_citation_integrity_holds_end_to_end(rules, corpus):
    result = compile_formulation(
        load_fixture("fixtures/triphala_classical.json"),
        as_of=AS_OF, rules=rules, corpus=corpus,
    )
    assert not result.integrity_problems
    assert result.cbom.findings
    for f in result.cbom.findings:
        assert f.citations, f"{f.rule_id} emitted with no citation"


# ------------------------------------------------------- the core thesis ---
def test_same_provision_is_blocker_and_opportunity(rules, corpus):
    """The product thesis, as an assertion: one citation, two lanes, opposite
    consequences. If this test ever fails the pitch is gone."""
    result = compile_formulation(
        load_fixture("fixtures/triphala_classical.json"),
        as_of=AS_OF, rules=rules, corpus=corpus,
    )
    by_rule = {f.rule_id: f for f in result.cbom.findings}
    blocker = by_rule["IN.PAT.S3P.TK_EXCLUSION"]
    opportunity = by_rule["REG.TRADITIONAL_USE_ASSET"]

    assert blocker.severity is Severity.BLOCKER
    assert opportunity.severity is Severity.OPPORTUNITY
    assert blocker.lane == "PATENT" and opportunity.lane == "REGULATORY"
    assert {c.corpus_id for c in blocker.citations} == {
        c.corpus_id for c in opportunity.citations
    }


# -------------------------------------------------------------- autofix ----
def test_autofix_recompilation_actually_clears_the_blocker(rules, corpus):
    f = load_fixture("fixtures/triphala_classical.json")
    before = compile_formulation(f, as_of=AS_OF, rules=rules, corpus=corpus)
    blocker = next(x for x in before.blockers
                   if x.rule_id == "IN.PAT.S3E.MERE_ADMIXTURE")
    fix = next(x for x in blocker.autofix if x.available)
    after, _ = apply_autofix(f, fix, as_of=AS_OF, rules=rules, corpus=corpus)
    assert "IN.PAT.S3E.MERE_ADMIXTURE" in diff_findings(before, after)["cleared"]


def test_autofix_precondition_blocks_an_inapplicable_fix(rules, corpus):
    """PIVOT_TO_PROCESS_CLAIM must not be offered when there is no non-obvious
    process step to pivot to."""
    before = compile_formulation(
        load_fixture("fixtures/triphala_classical.json"),
        as_of=AS_OF, rules=rules, corpus=corpus,
    )
    tk = next(x for x in before.blockers if x.rule_id == "IN.PAT.S3P.TK_EXCLUSION")
    pivot = next(x for x in tk.autofix if x.id == "PIVOT_TO_PROCESS_CLAIM")
    assert not pivot.available


# --------------------------------------------------------- reproducible ----
def test_cbom_is_byte_identical_across_ten_runs(rules, corpus):
    f = load_fixture("fixtures/triphala_classical.json")
    digests = {
        compile_formulation(f, as_of=AS_OF, rules=rules, corpus=corpus).cbom.digest()
        for _ in range(10)
    }
    assert len(digests) == 1, "a compiler must produce a reproducible build"


def test_abstains_on_a_jurisdiction_it_has_no_corpus_for(rules, corpus):
    result = compile_formulation(
        load_fixture("fixtures/triphala_classical.json"),
        as_of=AS_OF, rules=rules, corpus=corpus,
    )
    rows = {r.jurisdiction.value: r for r in result.cbom.jurisdiction_matrix}
    assert "ABSTAIN" in rows["US"].patentability
    assert rows["US"].citation_count == 0
    assert rows["IN"].citation_count > 0
