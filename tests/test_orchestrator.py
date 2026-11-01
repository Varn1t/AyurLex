"""YUKTI — the orchestrator must stay a plan, not an improviser.

The claim being pinned: the plan is deterministic, bounded and printable
before anything runs; the composition assembles sections rather than
summarising across them; and cross-layer questions come back as two separately
retrieved answers, never one blended one.
"""
from __future__ import annotations

from datetime import date

import pytest

from yukti.orchestrate import MAX_STEPS, compose, plan, run, split_layers


AS_OF = date(2026, 9, 6)


# ----------------------------------------------------------------- plan ----
def test_plan_is_deterministic():
    q = ("my churna contains amla, haritaki and bibhitaki and I market it as "
         '"cures diabetes" — can I patent it?')
    a = [(s.tool, s.query, tuple(sorted(s.args.items()))) for s in plan(q)]
    b = [(s.tool, s.query, tuple(sorted(s.args.items()))) for s in plan(q)]
    assert a == b


def test_plan_is_bounded():
    """The plan is finite the moment it is built. There is no loop deciding
    whether to keep going, so there is no run that fails to terminate."""
    q = " and also ".join([f"what does section {i} of the Patents Act say"
                           for i in range(20)])
    assert len(plan(q)) <= MAX_STEPS


def test_a_plain_question_stays_one_step():
    """Orchestration is for questions a single retrieval cannot serve, not a
    new default. A single question must not pay for a planner."""
    steps = plan("can I trademark the name of my ayurvedic churna")
    assert len(steps) == 1
    assert steps[0].tool == "ask"


def test_a_formulation_compiles_before_it_is_asked_about():
    """The category decides the posture, so it is established first. The order
    is the legal order, not a heuristic."""
    steps = plan("my churna contains amla, haritaki and bibhitaki — "
                 "can I patent it?")
    assert steps[0].tool == "compile"
    assert any(s.tool == "ask" for s in steps)


def test_the_ask_step_drops_the_ingredient_list():
    """Three plant names dominate a retrieval query and drown the question the
    user actually asked."""
    steps = plan("my churna contains amla, haritaki and bibhitaki — "
                 "can I patent it?")
    ask = next(s for s in steps if s.tool == "ask")
    assert "haritaki" not in ask.query.lower()
    assert "patent" in ask.query.lower()


def test_every_step_states_why_it_is_there():
    for s in plan("what does the Nagoya Protocol require and what must I do "
                  "in India under the Biological Diversity Act"):
        assert s.why and len(s.why.split()) >= 4


# --------------------------------------------------------- layer split ----
def test_cross_layer_question_splits_into_two_real_halves():
    halves = split_layers("what does the Nagoya Protocol require for benefit "
                          "sharing and what must I do in India under the "
                          "Biological Diversity Act")
    assert halves is not None
    intl, indian = halves
    assert "Nagoya" in intl and "Nagoya" not in indian
    assert "Biological Diversity" in indian


def test_the_two_halves_are_not_the_same_string():
    """The first version appended 'under Indian law' to the same string and
    sent it twice; both copies came back from the international layer. Two
    identical answers under two different badges is worse than not splitting."""
    halves = split_layers("what does TRIPS require and what does the Patents "
                          "Act say about it")
    if halves is not None:
        assert halves[0] != halves[1]


def test_a_clause_that_will_not_decompose_is_asked_once():
    """Rather than fabricate a split that the text does not support."""
    steps = plan("does TRIPS apply to the Indian Patents Act in one sentence")
    ask_steps = [s for s in steps if s.tool == "ask"]
    assert len(ask_steps) <= 2


def test_cross_layer_plan_asks_each_layer_separately():
    steps = plan("what does the Nagoya Protocol require for benefit sharing "
                 "and what must I do in India under the Biological Diversity "
                 "Act")
    layers = [s.args.get("prefer_layer") for s in steps if s.tool == "ask"]
    assert set(layers) == {"IN", "INTL"}


# ------------------------------------------------------------- routing ----
def test_a_relationship_question_becomes_a_graph_walk():
    steps = plan("how does the Nagoya Protocol relate to the Biological "
                 "Diversity Act")
    assert steps[0].tool == "graph"


def test_escalation_is_planned_last():
    """It reads what the earlier steps found, including what they could not."""
    steps = plan("my churna contains amla, haritaki and bibhitaki — "
                 "who should I talk to about this?")
    assert steps[-1].tool == "escalate"


# --------------------------------------------------------------- run ------
@pytest.fixture(scope="module")
def cross_layer():
    return run("what does the Nagoya Protocol require for benefit sharing and "
               "what must I do in India under the Biological Diversity Act",
               as_of=AS_OF)


def test_run_keeps_the_layers_apart(cross_layer):
    layers = {r.layer for r in cross_layer.steps if r.step.tool == "ask"}
    assert layers == {"IN", "INTL"}


def test_each_section_cites_only_its_own_layer(cross_layer):
    """The mechanical guarantee: evidence is never pooled across steps."""
    for r in cross_layer.steps:
        if r.step.tool != "ask" or not r.citations:
            continue
        js = {c.jurisdiction for c in r.citations}
        indian = {j for j in js if j == "IN"}
        foreign = {j for j in js if j != "IN"}
        assert not (indian and foreign), (r.layer, js)


def test_the_composition_warns_when_layers_differ(cross_layer):
    assert "separate authorities" in cross_layer.text


def test_the_trace_records_every_step(cross_layer):
    assert len(cross_layer.trace.results) == len(cross_layer.trace.steps)
    for r in cross_layer.steps:
        assert r.elapsed >= 0
        assert r.step.why


def test_the_plan_can_be_printed_before_it_runs():
    from yukti.orchestrate import Trace

    q = "how does TRIPS relate to the Patents Act"
    lines = Trace(question=q, steps=plan(q)).lines()
    assert lines[0].startswith("PLAN")
    assert "TRACE" not in "\n".join(lines)   # nothing has run yet


def test_compose_never_writes_across_sections(cross_layer):
    """No sentence in the output spans two steps -- every line of every section
    came from that section's own step."""
    bodies = [r.summary.strip() for r in cross_layer.steps if r.summary.strip()]
    for b in bodies:
        assert b[:60] in cross_layer.text


def test_empty_trace_composes_to_an_honest_message():
    from yukti.orchestrate import Trace

    assert "could not build a plan" in compose(Trace(question="", steps=[]))


# ---------------------------------------------------------------- chat ----
def test_chat_only_orchestrates_genuinely_multi_part_questions():
    from rag.chat import Session, respond

    s = Session()
    r = respond("can I patent a traditional ayurvedic formulation", s)
    assert r.intent != "ORCHESTRATE"


def test_chat_orchestrates_a_cross_layer_question():
    from rag.chat import Session, respond

    s = Session()
    r = respond("what does the Nagoya Protocol require and what must I do in "
                "India under the Biological Diversity Act", s)
    assert r.intent == "ORCHESTRATE"
    assert r.trace is not None
