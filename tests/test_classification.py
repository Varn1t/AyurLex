"""Classification: the regulatory classification layer.

The category decides the IP posture, so a wrong category is a wrong answer
about patentability. These tests pin the decision order, the refusal to guess
a missing fact, and the requirement that every category cite a provision that
actually exists.
"""
from __future__ import annotations

import pytest

from rag.chat import Session, answer_to_pending, respond
from classification.classify import (
    ClassIndex,
    Classification,
    classification_payload,
    facts_from_text,
    load_classes,
)


# --------------------------------------------------------------- the data ---
def test_every_category_resolves_against_the_corpus():
    """The same gate the compliance rules and RAG concepts pass. A category citing
    a provision that does not exist must fail the build, not cite nothing."""
    assert load_classes().problems == []


def test_every_category_states_all_three_postures():
    for c in load_classes().classes:
        assert c.requires, f"{c.id} has no regulatory consequence"
        assert c.ip, f"{c.id} has no IP posture"
        assert c.abs, f"{c.id} has no ABS posture"


def test_category_provisions_are_citable_with_real_quotes():
    """A category's citation must carry text from the ingested source."""
    idx = load_classes()
    for c in idx.classes:
        result = Classification(category=c, because="test")
        payload = classification_payload(result)
        assert payload["citations"], f"{c.id} produced no citations"
        for cite in payload["citations"]:
            assert cite["instrument"]
            assert cite["provision"]
            # A stub quote is what the pin-fallback exists to prevent.
            assert len(cite["quote"]) >= 150, (
                f"{c.id} cites {cite['provision']} with a {len(cite['quote'])}"
                f"-character stub")


def test_a_treaty_or_rule_is_never_cited_as_a_section():
    """Rule 158 of the Rules 1945 must not be cited as a "Section"."""
    idx = load_classes()
    for c in idx.classes:
        payload = classification_payload(Classification(category=c,
                                                        because="test"))
        for cite in payload["citations"]:
            if "Rules, 1945" in cite["instrument"]:
                assert cite["provision"].startswith("Rule"), cite


# ------------------------------------------------------------ the decision ---
def test_purified_fraction_is_a_phytopharmaceutical():
    f = facts_from_text(
        "a standardised extract with 5% withanolides, for treating arthritis")
    result = load_classes().classify(f)
    assert result.decided
    assert result.category.id == "PHYTOPHARMACEUTICAL"


def test_a_cosmetic_is_not_a_phytopharmaceutical():
    """Drug-or-not is decided before the fraction question.

    A standardised extract in a face cream making no disease claim is a
    cosmetic; a phytopharmaceutical is a species of drug. Deciding the
    fraction first would mis-classify it and waste a question.
    """
    f = facts_from_text(
        "a face cream with a standardised turmeric extract for beautifying "
        "skin, no disease claim")
    result = load_classes().classify(f)
    assert result.decided
    assert result.category.id == "COSMETIC"


def test_classical_text_formulation_is_classical():
    f = facts_from_text(
        "a classical formulation from the Ayurvedic Formulary of India for "
        "treating cough, prepared as a churna")
    result = load_classes().classify(f)
    assert result.decided
    assert result.category.id == "CLASSICAL"


def test_food_positioning_with_no_claim_is_ayurveda_aahara():
    f = facts_from_text(
        "sold as a health supplement drink, our own blend, no disease claim")
    result = load_classes().classify(f)
    assert result.decided
    assert result.category.id == "AYURVEDA_AAHARA"


def test_ayurveda_aahara_cites_its_own_governing_instrument():
    """This category used to declare its authority missing, and was right to.

    The FSS Act, 2006 and the Ayurveda Aahara Regulations, 2022 are now in the
    corpus, so the category cites them. The test is kept pointed at the same
    property from the other side: the category must never fall back to
    borrowing a loosely related provision, so what is asserted is that its
    citations are actually the food instruments, not that it has some.
    """
    cat = load_classes().by_id("AYURVEDA_AAHARA")
    assert not cat.uncited_authority
    assert not cat.problems
    acts = {p.split("::")[0] for p in cat.provisions}
    assert "IN.FSS_AAHARA.2022" in acts
    assert "IN.FSSA.2006" in acts


def test_ayurveda_aahara_leads_with_the_disease_claim_boundary():
    """Regulation 8 is what decides the category, so it is cited first.

    A product stops being Ayurveda Aahara the moment its label claims to
    prevent, treat or cure a disease -- at which point the drug regime and the
    Drugs and Magic Remedies Act, 1954 apply instead. Citing the licensing
    requirement first would answer a question the user did not ask and bury the
    one that changes the answer.
    """
    cat = load_classes().by_id("AYURVEDA_AAHARA")
    assert cat.provisions[0] == "IN.FSS_AAHARA.2022::R8"


@pytest.mark.parametrize("text,expected_fact", [
    ("my churna contains amla and haritaki", "classical_text_formulation"),
    ("my own blend of tulsi and giloy", "disease_claim"),
])
def test_a_missing_fact_is_asked_for_not_guessed(text, expected_fact):
    result = load_classes().classify(facts_from_text(text))
    assert not result.decided
    assert result.ask, "a missing fact must produce a question"
    assert result.facts.get(expected_fact) is None


def test_silence_is_not_read_as_absence_of_a_claim():
    """"No disease claim stated" and "no disease claim made" differ, and only
    one of them is safe to classify on."""
    f = facts_from_text("my churna contains amla, haritaki and bibhitaki")
    assert f["disease_claim"] is None


def test_an_explicit_denial_settles_the_claim_fact():
    f = facts_from_text("a tulsi drink, no disease claim")
    assert f["disease_claim"] is False


def test_treating_reads_as_a_disease_claim():
    """"treating" must match, or a plain therapeutic claim reads as no claim
    and the product is mis-classified as a cosmetic."""
    assert facts_from_text("for treating cough")["disease_claim"] is True
    assert facts_from_text("treatment of diabetes")["disease_claim"] is True


# --------------------------------------------------------- the conversation ---
@pytest.mark.parametrize("reply,expected", [
    ("yes", True), ("no", False), ("haan", True), ("nahi", False),
    ("nope", False), ("Yes it is", True),
    ("maybe", None), ("it is a churna", None),
])
def test_yes_no_reading(reply, expected):
    """"it is a churna" answers a question about the dosage form; reading it
    as a yes would silently record the wrong fact."""
    assert answer_to_pending(reply) is expected


def test_clarifying_question_is_answered_and_the_category_decided():
    session = Session()
    first = respond(
        'my churna contains amla, haritaki and bibhitaki and I market it as '
        '"cures diabetes"', session)
    assert first.intent == "COMPILE"
    assert session.pending_fact, "the compile should have asked something"

    # Not a classical formula, but the ingredients are in the authoritative
    # books: a patent-or-proprietary ASU medicine.
    respond("no", session)
    final = respond("yes", session)

    assert final.intent == "CLASSIFY"
    assert final.classification.decided
    assert final.classification.category.id == "PATENT_PROPRIETARY"
    assert session.pending_fact is None


def test_the_compile_still_compiles_while_classification_is_open():
    """An open classification question must not suppress the findings: the
    compile is the product, and the category is additional context."""
    session = Session()
    reply = respond(
        'my churna contains amla, haritaki and bibhitaki and I market it as '
        '"cures diabetes"', session)
    assert reply.compile_result is not None
    assert reply.compile_result.cbom.findings
    assert reply.classification is not None
    assert not reply.classification.decided


def test_facts_asserted_by_the_user_are_not_overwritten_by_prose():
    session = Session()
    session.class_facts["purified_fraction"] = True
    respond("my churna contains amla and haritaki", session)
    assert session.class_facts["purified_fraction"] is True


def test_structured_fields_settle_what_prose_only_suggests():
    """A formulation entered with is_classical_formulation / a standardised
    marker must not be asked those questions again. Both fields were once
    ignored by facts_from_formulation."""
    import json

    from classification.classify import facts_from_formulation
    from core.schema import Formulation

    f = Formulation.model_validate(
        json.load(open("fixtures/triphala_classical.json", encoding="utf-8")))
    assert facts_from_formulation(f)["classical_text_formulation"] is None
    f.is_classical_formulation = True
    assert facts_from_formulation(f)["classical_text_formulation"] is True
    f.process.standardised_marker = "5% withanolides"
    assert facts_from_formulation(f)["purified_fraction"] is True
