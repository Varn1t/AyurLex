"""Tests for the RAG layer.

The load-bearing assertions here are about what the chatbot REFUSES to do:
answer outside its corpus, quote a provision it did not retrieve, or let a
generated sentence through without support. A chatbot that answers everything
is easy; one that knows the edge of its own authority is the product.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rag.answer import (  # noqa: E402
    ExtractiveAnswerer,
    answer,
    verify_against_spans,
)
from rag.chat import (  # noqa: E402
    Session,
    classify,
    formulation_from_text,
    parse_ingredients,
    respond,
)
from rag.concepts import load_concepts  # noqa: E402
from rag.retriever import load_retriever  # noqa: E402
from tests.eval_retrieval import evaluate  # noqa: E402

AS_OF = date(2026, 9, 1)


@pytest.fixture(scope="module")
def retriever():
    return load_retriever()


# ---------------------------------------------------------------- concepts --
def test_every_concept_resolves_against_the_corpus():
    """A concept naming a provision that does not exist would silently degrade
    retrieval. It fails loudly instead."""
    assert not load_concepts().problems


def test_concept_matches_lay_phrasing_not_just_literal_text():
    ci = load_concepts()
    # "file abroad" must match "file a patent abroad first".
    m = ci.match("I want to file a patent abroad first, is that allowed")
    assert m and m[0].concept.id == "FOREIGN_FILING"


def test_concept_does_not_match_across_a_whole_sentence():
    """The proximity window stops 'file' ... 40 words ... 'abroad' matching."""
    ci = load_concepts()
    text = ("I want to file a trade mark application and separately I am "
            "curious about how my cousin who lives abroad handles his taxes")
    ids = {m.concept.id for m in ci.match(text)}
    assert "FOREIGN_FILING" not in ids


# --------------------------------------------------------------- retrieval --
def test_retrieval_gold_set_holds(retriever):
    out = evaluate(verbose=False)
    assert out["recall@5"] >= 0.85, out["misses"]
    assert out["abstention_accuracy"] == 1.0, out["misses"]


def test_vernacular_query_reaches_the_statute(retriever):
    """A Hindi question must land on the Patents Act, not on Hindi prose."""
    res = retriever.search("क्या मैं गिलोय का पेटेंट करा सकता हूँ", k=5)
    assert ("गिलोय", "Tinospora cordifolia") in res.taxa_expansions
    assert res.hits[0].corpus_id.startswith("IN.PATENTS.1970::S3")


def test_repealed_or_future_law_is_filtered_before_scoring(retriever):
    """as_of is a pre-filter. Any hit returned must be in force on that date."""
    from samhita.index import in_force

    res = retriever.search("what are not inventions", k=8, as_of=date(2005, 1, 1))
    assert all(in_force(h.record, date(2005, 1, 1)) for h in res.hits)


def test_background_material_never_outranks_a_statute(retriever):
    """The TKDL and Ayurveda prose discuss 'traditional knowledge patent' on
    nearly every page. They must not be the answer to a legal question."""
    res = retriever.search("Can I patent a traditional ayurvedic formulation?",
                           k=5)
    assert res.hits[0].record["authority_rank"] == 1
    assert res.hits[0].record["citable"]


# ----------------------------------------------------------------- answers --
def test_abstains_outside_the_corpus(retriever):
    res = retriever.search("what is the US filing fee for a provisional application")
    a = answer("what is the US filing fee for a provisional application", res)
    assert a.abstained
    assert "US" in a.abstain_reason or "corpus" in a.abstain_reason
    assert not a.citations


def test_answer_quotes_the_pinned_clause(retriever):
    """A question about traditional knowledge must be answered with clause (p),
    not with a recitation of the whole of section 3."""
    res = retriever.search("Can I patent a traditional ayurvedic formulation?")
    a = answer("Can I patent a traditional ayurvedic formulation?", res,
               backend=ExtractiveAnswerer())
    assert "Section 3(p)" in a.text
    assert "in effect, is traditional knowledge" in a.text
    assert "frivolous" not in a.text          # clause (a) must not be dragged in


def test_extractive_answer_is_verbatim_from_the_corpus(retriever):
    """Every quoted span must appear in the cited provision, character for
    character. This is what makes the offline backend unable to hallucinate."""
    import re

    from samhita.index import load_corpus

    corpus = load_corpus()
    res = retriever.search("can I advertise that my product cures diabetes")
    a = answer("can I advertise that my product cures diabetes", res,
               backend=ExtractiveAnswerer())
    quotes = re.findall(r"“([^”]+)”", a.text)
    assert quotes
    for qt in quotes:
        found = any(
            re.sub(r"\s+", " ", qt).strip().lower()
            in re.sub(r"\s+", " ", corpus.get(c.corpus_id)["text"]).lower()
            for c in a.citations
        )
        assert found, f"quoted span is not verbatim in any cited provision: {qt[:80]}"


def test_generated_text_with_an_invented_number_is_stripped(retriever):
    """The gate applied to a generator's output, not just to compiler findings."""
    res = retriever.search("can I advertise that my product cures diabetes")
    drafted = ("An advertisement may not refer to a scheduled condition. "
               "The penalty is 47 years of imprisonment.")
    kept, grounded, dropped = verify_against_spans(drafted, res)
    assert "47" not in kept
    assert any("47" in d for d in dropped)


# -------------------------------------------------------------------- chat --
def test_ingredient_list_is_parsed_conservatively():
    items = parse_ingredients("my churna contains amla, haritaki and bibhitaki")
    assert items == ["amla", "haritaki", "bibhitaki"]
    # No list, no invention.
    assert parse_ingredients("can I patent something?") == []


def test_formulation_description_routes_to_the_compiler():
    s = Session(as_of=AS_OF)
    text = "my churna contains amla, haritaki and bibhitaki and I want to patent it"
    assert classify(text, s) == "COMPILE"
    f = formulation_from_text(text)
    assert f and len(f.ingredients) == 3


def test_question_routes_to_retrieval():
    s = Session(as_of=AS_OF)
    assert classify("Can I patent a traditional ayurvedic formulation?", s) == "ASK"


def test_compile_route_returns_findings_with_citations():
    s = Session(as_of=AS_OF)
    reply = respond("my churna contains amla, haritaki and bibhitaki "
                    "and I want to patent it", s)
    assert reply.intent == "COMPILE"
    cb = reply.compile_result.cbom
    assert cb.findings
    assert all(f.citations for f in cb.findings)
    assert s.formulation is not None


def test_autofix_over_chat_proves_the_blockers_clear():
    s = Session(as_of=AS_OF)
    respond("my churna contains amla, haritaki and bibhitaki "
            "and I want to patent it", s)
    reply = respond("apply the fixes", s)
    assert "cleared" in reply.text
    assert len(reply.compile_result.blockers) == 0


def test_autofix_without_a_formulation_asks_rather_than_guesses():
    s = Session(as_of=AS_OF)
    reply = respond("apply the fixes", s)
    assert "don't have a formulation" in reply.text


def test_follow_up_is_resolved_against_the_previous_turn():
    s = Session(as_of=AS_OF)
    respond("can I advertise that my product cures diabetes", s)
    reply = respond("why?", s)
    # The bare "why?" retrieves nothing on its own; carried context keeps it
    # on the advertising provisions.
    assert reply.intent == "FOLLOW"
    assert not (reply.answer and reply.answer.abstained)
