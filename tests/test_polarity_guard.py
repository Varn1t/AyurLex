"""The polarity guard.

A question like "do I need NBA approval before filing?" has an answer whose
entire content is its polarity, and the citation gate cannot check polarity: it
verifies that a sentence is carried by spans of the retrieved provision, and
"you do not need approval" is built from the same words as the provision that
requires it.

Measured on the local 1.5B model, three of four such questions came back
inverted -- including "No, you do not need approval from the National
Biodiversity Authority", against a section headed "Application for intellectual
property rights not to be made without approval". So the model is taken out of
this class of question and the provision is quoted instead.

These tests pin which questions the guard claims, which it leaves alone, and
that the quoted answer actually carries the operative words.
"""
from __future__ import annotations

import pytest

from rag.answer import ExtractiveAnswerer, turns_on_polarity
from rag.retriever import load_retriever


@pytest.mark.parametrize("question", [
    "do I need FDA approval to sell my ayurvedic churna in the US market",
    "Do I need approval from the National Biodiversity Authority before "
    "applying for a patent?",
    "Do I need permission before filing a patent application outside India?",
    "I am a vaidya, do I need to inform the state biodiversity board",
    "Must I disclose the source and geographical origin of biological material?",
    "What licence do I need to manufacture an ayurvedic drug?",
    "is prior approval required before filing",
    "do we have to share benefits",
    "am I required to give prior intimation",
])
def test_duty_questions_are_guarded(question):
    assert turns_on_polarity(question), question


@pytest.mark.parametrize("question", [
    # Asks what a duty contains, not whether it binds the asker. The model
    # answers these well and must keep them.
    "what does the Nagoya Protocol require for benefit sharing",
    "What does Section 7 of the Biological Diversity Act require?",
    # Permission questions are answered by a prohibition, which the model
    # handles correctly.
    "Can I patent a traditional ayurvedic formulation?",
    "Can I trademark the name of my ayurvedic churna?",
    "can I file a PCT application for my formulation",
    # Definitional and comparative.
    "What is Ayurveda?",
    "What's the difference between a patent, GI, and trademark?",
    "what is the EPO opposition period",
    "what is required under section 7",
])
def test_content_questions_are_not_guarded(question):
    assert not turns_on_polarity(question), question


@pytest.mark.parametrize("question,must_contain", [
    ("Do I need approval from the National Biodiversity Authority before "
     "applying for a patent on a biological resource?",
     "without obtaining the previous approval"),
    ("Do I need permission before filing a patent application outside India?",
     "No person resident in India shall"),
])
def test_the_quoted_answer_carries_the_operative_words(question, must_contain):
    """The guard is only worth having if what it quotes answers the question.

    Each of these previously came back from the model with the polarity
    inverted; the provision itself says the opposite, in these words.
    """
    res = load_retriever().search(question, k=6, citable_only=True)
    text = ExtractiveAnswerer().write(question, res)
    assert must_contain.lower() in text.lower(), text[:400]


def test_guarded_answers_are_not_abstentions():
    """Quoting the provision is a real answer, not a refusal dressed up."""
    question = ("Do I need approval from the National Biodiversity Authority "
                "before applying for a patent on a biological resource?")
    res = load_retriever().search(question, k=6, citable_only=True)
    assert not res.is_weak
    text = ExtractiveAnswerer().write(question, res)
    assert "don't have authority" not in text.lower()
    assert len(text) > 200
