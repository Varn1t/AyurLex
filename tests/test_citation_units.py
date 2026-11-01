"""Citation units across the whole corpus.

A wrong citation is the one output this system may never emit, and the unit is
part of the citation: "Section 27 of TRIPS" and "Section 154 of the Drugs and
Cosmetics Rules" are both wrong, and both were being emitted. These are corpus
invariants rather than unit tests -- they check the ingested result, so they
catch a Source registered without its `unit` as well as a regression in the
ingester.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "provisions.jsonl"


@pytest.fixture(scope="module")
def records() -> list[dict]:
    if not CORPUS.exists():
        pytest.skip("corpus not built; run python sources/ingest.py")
    return [json.loads(line) for line in CORPUS.open(encoding="utf-8")]


def test_an_instrument_titled_rules_numbers_rules(records):
    bad = sorted({
        (r["act_title"], r["unit"]) for r in records
        if "Rules" in r["act_title"] and "Act" not in r["act_title"]
        and r["unit"] != "Rule"
    })
    assert not bad, f"instruments titled Rules citing something else: {bad}"


def test_a_treaty_numbers_articles(records):
    bad = sorted({
        (r["act_title"][:40], r["unit"]) for r in records
        if r["instrument_type"] == "TREATY" and r["unit"] != "Article"
    })
    assert not bad, f"treaty provisions not cited as Articles: {bad}"


def test_an_indian_statute_numbers_sections(records):
    bad = sorted({
        (r["act_title"][:40], r["unit"]) for r in records
        if r["instrument_type"] == "ACT" and r["unit"] != "Section"
    })
    assert not bad, f"Act provisions not cited as Sections: {bad}"


def test_every_instrument_uses_exactly_one_unit(records):
    """A sub-chunked provision inherits its parent's unit; a mixture means the
    inheritance broke and some parts are mislabelled."""
    units = defaultdict(set)
    for r in records:
        units[r["act_id"]].add(r["unit"])
    mixed = {k: sorted(v) for k, v in units.items() if len(v) > 1}
    assert not mixed, f"instruments with mixed units: {mixed}"


def test_the_corpus_id_prefix_matches_the_label_shown(records):
    """S3 / R154 / A27 / P12 -- the id prefix is the initial of the label the
    reader is shown, so a mismatch means the id and the citation disagree.

    Page-chunked prose material is the case worth stating: its ids are P<page>
    and it is cited as "page 12", not by any numbered unit.
    """
    bad = []
    for r in records:
        tail = r["corpus_id"].split("::", 1)[1]
        sec = str(r["section"])
        expected = "page" if sec.startswith("p.") else r["unit"]
        if not tail.lower().startswith(expected[0].lower()):
            bad.append((r["corpus_id"], expected))
    assert not bad, f"id prefix disagrees with the label shown: {bad[:5]}"


def test_the_drugs_and_cosmetics_act_and_rules_are_separate(records):
    """One India Code PDF holds both, and numbering restarts at the boundary.
    Ingesting it as a single instrument buried the Act's definitions in a
    record labelled "Section 38"."""
    acts = {r["act_id"] for r in records}
    assert "IN.DCA.1940" in acts
    assert "IN.DC_RULES.1945" in acts

    by_id = {r["corpus_id"]: r for r in records}
    s3 = by_id.get("IN.DCA.1940::S3")
    assert s3 is not None, "the Act's definitions section is missing"
    assert "Definitions" in s3["heading"]
    # The definitions the formulation classifier depends on.
    for clause in ("a", "h", "aaa"):
        assert clause in s3["clauses"], f"s.3({clause}) is not pin-citable"


def test_no_provision_is_cited_as_a_section_of_an_instrument_titled_rules(records):
    """The reader-facing version of the same invariant: build the label the UI
    would show and check it never says Section for a set of Rules."""
    for r in records:
        sec = str(r["section"])
        label = (f"page {sec[2:]}" if sec.startswith("p.")
                 else f"{r['unit']} {sec}")
        shown = f"{r['act_title']} — {label}"
        if "Rules," in r["act_title"] and "Act," not in r["act_title"]:
            assert " — Section" not in shown, shown
