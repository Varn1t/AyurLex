"""Conversation memory, and what the groundedness pill actually measures.

Two things pinned here, both of which were user-visible defects:

  * A follow-up carrying only a pronoun must reach back to the subject the
    conversation already established, instead of being retrieved cold and
    abstaining.
  * Groundedness must be a continuous measure of the text actually shown. The
    old formula counted only sentences clearing 0.55 over a denominator that
    also included dropped ones, so an answer the gate had decided to display
    could read 0.00 -- and the same question returned 0.750, 0.200 and 0.000
    across three runs of the same model.
"""
from __future__ import annotations

import pytest

from rag.chat import (
    CONTEXT_TURNS,
    Session,
    Turn,
    classify,
    followup_query,
    is_followup,
    subject_tokens,
)


def _seed(session: Session, *questions: str) -> Session:
    for q in questions:
        session.turns.append(Turn(role="user", text=q))
        session.turns.append(Turn(role="assistant", text="...", concepts=[]))
    return session


# ------------------------------------------------------- follow-up test ----
@pytest.mark.parametrize("text", [
    "what are their pros and cons",
    "compare them",
    "which one is cheapest",
    "and the fix?",
    "what about that",
    "pros and cons?",
    "how about these",
])
def test_anaphoric_messages_are_followups(text):
    s = _seed(Session(), "what is the difference between a patent and a GI")
    assert is_followup(text, s), text


def test_a_full_question_is_not_a_followup():
    """Same words, but it names its own subject and must be retrieved on its
    own terms rather than dragged back to the previous turn."""
    s = _seed(Session(), "can I patent a churna")
    long_q = ("What are the pros and cons of registering a geographical "
              "indication for a herbal product from Kerala and elsewhere")
    assert not is_followup(long_q, s)
    assert classify(long_q, s) == "ASK"


def test_nothing_is_a_followup_on_the_first_turn():
    assert not is_followup("what about that", Session())


def test_an_ordinary_question_containing_that_is_not_a_followup():
    """The regression this test exists for: 'can I advertise that my product
    cures diabetes' matches the anaphora pattern on the word "that" and is
    short enough, so it was read as a follow-up -- which meant it could never
    anchor the real follow-up that came next, and a bare "why?" then retrieved
    cold and abstained."""
    s = _seed(Session(), "what is a churna")
    q = "can I advertise that my product cures diabetes"
    assert not is_followup(q, s)
    assert subject_tokens(q) == ["advertise", "product", "cures", "diabetes"]


def test_a_bare_why_reaches_the_previous_subject():
    from rag.chat import respond

    s = Session()
    respond("can I advertise that my product cures diabetes", s)
    _, anchors = followup_query(s, "why?")
    assert anchors == ["can I advertise that my product cures diabetes"]


# --------------------------------------------------------- query build ----
def test_followup_query_carries_the_subject():
    s = _seed(Session(),
              "What's the difference between a patent, GI, and trademark "
              "for an Ayurvedic product?")
    q, anchors = followup_query(s, "what are their pros and cons")
    assert anchors
    assert "trademark" in q.lower()
    assert "pros and cons" in q.lower()


def test_followup_reaches_back_three_substantive_turns():
    s = _seed(Session(),
              "can I patent a traditional ayurvedic formulation",
              "what is benefit sharing under Section 21 of the Biological "
              "Diversity Act",
              "can I trademark the name of my ayurvedic churna",
              "what does the TKDL do")
    _, anchors = followup_query(s, "compare them")
    assert len(anchors) == CONTEXT_TURNS
    # Newest first: if the subject moved, the latest statement of it wins.
    assert anchors[0] == "what does the TKDL do"


def test_a_chain_of_followups_does_not_fill_the_window():
    """Otherwise three pronouns crowd out the one question that had a subject."""
    s = Session()
    s.turns.append(Turn(role="user", text="can I patent my churna"))
    s.turns.append(Turn(role="assistant", text="...", concepts=[]))
    for pronoun in ("what about that", "and them", "why is it so"):
        s.turns.append(Turn(role="user", text=pronoun))
        s.turns.append(Turn(role="assistant", text="...", concepts=[]))
    _, anchors = followup_query(s, "compare them")
    assert anchors == ["can I patent my churna"]


def test_followup_query_is_a_noop_with_no_history():
    q, anchors = followup_query(Session(), "what about that")
    assert q == "what about that"
    assert anchors == []


def test_concept_vocabulary_is_carried_across_turns():
    """The register bridge the lexicon provides within one turn, applied
    across turns: the user says 'GI', the statute says 'geographical
    indication'."""
    s = Session()
    s.turns.append(Turn(role="user", text="can I register a GI"))
    s.turns.append(Turn(role="assistant", text="...",
                        concepts=["GI_PROTECTION"]))
    q, _ = followup_query(s, "what are its pros and cons")
    from rag.concepts import load_concepts

    gi = next(c for c in load_concepts().concepts if c.id == "GI_PROTECTION")
    assert any(term.lower() in q.lower() for term in gi.statutory[:4])


# ---------------------------------------------------------- end to end ----
def test_followup_answers_from_the_earlier_subject():
    from rag.chat import respond

    s = Session()
    respond("What's the difference between a patent, GI, and trademark for "
            "an Ayurvedic product?", s)
    r = respond("what are their pros and cons", s)
    assert r.intent == "FOLLOW"
    assert not r.answer.abstained
    # It must reach the three regimes, not just whichever one the pronoun
    # happened to resemble.
    instruments = " ".join(c.instrument for c in r.citations)
    assert "Trade Marks" in instruments or "Geographical" in instruments


def test_the_assumption_is_stated_not_silent():
    """Resolving a pronoun is a guess. A guess the user cannot see is one they
    cannot correct."""
    from rag.chat import respond

    s = Session()
    respond("can I trademark the name of my ayurvedic churna", s)
    r = respond("what are its pros and cons", s)
    if not r.answer.abstained:
        assert "follow-up to" in r.text


# -------------------------------------------------------- groundedness ----
def test_groundedness_is_not_zero_for_displayed_text():
    """The defect: the gate shows a sentence at 0.34 but the old score only
    counted it at 0.55, so displayed text could read 0.00."""
    from rag.answer import verify_against_spans
    from rag.retriever import load_retriever

    res = load_retriever().search("what does Section 7 of the Biological "
                                  "Diversity Act require",
                                  k=6, citable_only=True)
    span = res.hits[0].record["text"]
    # A sentence built from the provision's own words, so it is genuinely
    # carried by it -- but paraphrased, so it need not clear 0.55.
    words = [w for w in span.split() if len(w) > 4][:14]
    draft = " ".join(words) + "."
    text, grounded, dropped = verify_against_spans(draft, res)
    if text.strip():
        assert grounded > 0.0, "shown text scored zero"


def test_groundedness_is_the_mean_of_what_is_shown():
    from rag.answer import verify_against_spans
    from rag.retriever import load_retriever
    from citations.verify import entailment_score

    res = load_retriever().search("what does Section 7 of the Biological "
                                  "Diversity Act require",
                                  k=6, citable_only=True)
    span = res.hits[0].record["text"]
    draft = " ".join(w for w in span.split()[:22]) + "."
    text, grounded, _ = verify_against_spans(draft, res)
    if text.strip():
        spans = " ".join(h.record["text"] for h in res.hits[:3])
        meta = " ".join(f"{h.record['act_title']} Section {h.record['section']} "
                        f"{h.record['heading']}" for h in res.hits[:3])
        direct = entailment_score(text, spans + " " + meta)
        assert abs(grounded - direct) < 0.35


def test_groundedness_stays_in_range():
    from rag.answer import verify_against_spans
    from rag.retriever import load_retriever

    res = load_retriever().search("can I patent a traditional ayurvedic "
                                  "formulation", k=6, citable_only=True)
    for draft in ["", "Purple monkey dishwasher deadline 1997.",
                  res.hits[0].record["text"][:300]]:
        _, g, _ = verify_against_spans(draft, res)
        assert 0.0 <= g <= 1.0


def test_entailed_fraction_is_still_available():
    """The strict measure is kept, just no longer averaged into one number
    that meant neither thing."""
    from rag.answer import entailed_fraction

    assert entailed_fraction([]) == 0.0
    assert entailed_fraction([0.9, 0.9]) == 1.0
    assert entailed_fraction([0.4, 0.9]) == 0.5
