"""SAMPARK — escalation must stay deterministic, cited, and private.

Three properties are load-bearing and each is pinned here:

  * the directory's statutory bases are verified against the primary sources,
  * escalation fires on facts the system already established, never on a guess,
  * nothing is transmitted, and the redacted packet really does drop the recipe.
"""
from __future__ import annotations

from datetime import date

import pytest

from core.compiler import compile_formulation
from core.schema import Formulation
from sampark.escalate import (
    TRIGGERS,
    assess,
    load_registry,
    payload,
    render,
)


@pytest.fixture(scope="module")
def registry():
    return load_registry()


@pytest.fixture(scope="module")
def compiled():
    f = Formulation.model_validate_json(
        open("fixtures/triphala_classical.json", encoding="utf-8").read())
    return compile_formulation(f, as_of=date(2026, 9, 5))


# ------------------------------------------------------------- registry ----
def test_every_route_verifies(registry):
    assert registry.problems == [], registry.problems


def test_every_route_has_a_basis_or_says_it_has_none(registry):
    """A route with no statute behind it must say so rather than borrow a
    loosely related citation -- the same rule the classifier follows."""
    for r in registry.routes:
        assert r.citation or r.uncited_authority, r.id


def test_uncited_routes_are_the_expected_ones(registry):
    """If a route silently loses its citation, this test names it.

    FSSAI was on this list until the Food Safety and Standards Act, 2006 was
    ingested; it now cites Section 4, the provision that establishes the
    authority. Only the Ministry of Ayush facilitation desk remains, and it is
    genuinely uncited: it is an administrative route, not a statutory one, and
    no amount of corpus would give it a section number.
    """
    uncited = {r.id for r in registry.routes if not r.citation}
    assert uncited == {"AYUSH_IP_FACILITATION"}, uncited


def test_fssai_route_cites_the_authority_that_establishes_it(registry):
    fssai = registry.by_id("FSSAI")
    assert fssai.ok and not fssai.uncited_authority
    assert "Food Safety and Standards Act, 2006" in fssai.citation


def test_background_routes_are_marked(registry):
    """TKDL is reference material, not law, and must be labelled as such."""
    tkdl = registry.by_id("TKDL_ACCESS")
    assert tkdl.background is True


def test_no_route_ships_an_invented_contact(registry):
    """A prototype must not invent an office's phone number or desk."""
    for r in registry.routes:
        assert r.contact == "configure at deployment", r.id


# ------------------------------------------------------------- triggers ----
def test_no_escalation_when_nothing_is_wrong():
    ref = assess()
    assert not ref.needed
    assert "Nothing in this session needs a human yet" in render(ref)


def test_blockers_trigger_escalation(compiled):
    ref = assess(compile_result=compiled)
    assert "BLOCKER_PRESENT" in ref.triggers
    assert ref.needed


def test_abstention_triggers_escalation():
    from rag.answer import Answer

    a = Answer(question="what is the EPO opposition period", text="",
               abstained=True, abstain_reason="the question is about EPO law")
    ref = assess(answer=a)
    assert "ABSTAINED" in ref.triggers
    assert any("EPO" in c for c in ref.could_not_determine)


def test_every_trigger_has_a_readable_reason(compiled):
    """The referral explains itself to a founder, not with an enum name."""
    ref = assess(compile_result=compiled, user_asked=True)
    for t in ref.triggers:
        assert t in TRIGGERS, f"{t} has no sentence"
    assert not any(t.endswith("_LANE") for t in ref.triggers)


def test_lane_tags_route_but_do_not_explain(compiled):
    """A lane says which office a finding belongs to, never why a human is
    needed. Mixing the two put 'ACCESS_LANE' in front of the user."""
    ref = assess(compile_result=compiled)
    assert any(t.endswith("_LANE") for t in ref.routing)
    ids = {r.id for r in ref.routes}
    assert "NBA" in ids


def test_routes_are_relevant_not_everything(compiled):
    ref = assess(compile_result=compiled)
    ids = {r.id for r in ref.routes}
    assert "PATENT_AGENT" in ids
    # A pure patent/ABS/advertising compile has no reason to route to the
    # plant-variety authority.
    assert "PPVFR_AUTHORITY" not in ids


# -------------------------------------------------------------- packet ----
def test_reference_is_a_content_digest(compiled):
    """Same session, same reference. Change the substance, change it."""
    a = assess(compile_result=compiled, user_asked=True)
    b = assess(compile_result=compiled, user_asked=True)
    assert a.reference() == b.reference()
    assert a.reference() != assess(compile_result=compiled).reference()


def test_redaction_removes_the_recipe_and_keeps_the_law(compiled):
    full = render(assess(compile_result=compiled))
    red = render(assess(compile_result=compiled, redact=True))
    assert "Emblica officinalis" in full
    assert "Emblica officinalis" not in red
    assert "Terminalia chebula" not in red
    # The legal posture survives redaction -- that is the whole point.
    assert "Section 6(1)" in red
    assert "Registered patent agent" in red
    assert "REDACTED" in red


def test_packet_states_that_nothing_was_sent(compiled):
    text = render(assess(compile_result=compiled))
    assert "has been transmitted" in text
    assert "not legal advice" in text


def test_packet_carries_its_authority(compiled):
    text = render(assess(compile_result=compiled))
    assert "AUTHORITY RELIED ON" in text
    assert "The_Biological_Diversity_Act_2002.pdf" in text


def test_payload_shape_is_serialisable(compiled):
    import json

    json.dumps(payload(assess(compile_result=compiled, user_asked=True)))


# ---------------------------------------------------------------- chat ----
def test_chat_routes_an_escalation_request():
    from rag.chat import Session, respond

    s = Session()
    r = respond("who should I contact about this", s)
    assert r.intent == "ESCALATE"


def test_chat_escalation_uses_what_the_session_established():
    from rag.chat import Session, respond

    s = Session()
    respond("my churna contains amla, haritaki and bibhitaki", s)
    r = respond("escalate", s)
    assert r.intent == "ESCALATE"
    assert r.referral.needed
    assert "BLOCKER_PRESENT" in r.referral.triggers


def test_chat_honours_the_redaction_request():
    from rag.chat import Session, respond

    s = Session()
    respond("my churna contains amla, haritaki and bibhitaki", s)
    r = respond("escalate without the formulation", s)
    assert r.referral.redacted
    assert "Emblica officinalis" not in r.text
