"""Tests for the non-English path, end to end.

Every test here is a regression: each one names a bug that shipped, and the
four of them together are one failure with four causes. A Tamil question
("can I get a patent for Giloy?") came back as English prose about Panchakarma,
cut off in mid-sentence, and the reason was never the model.

  1. rag.concepts.norm deleted Indic combining marks, so every Tamil, Telugu,
     Kannada, Malayalam, Bengali and Gujarati phrase in the concept lexicon was
     unmatchable. Only Devanagari worked, because its block had been whitelisted.
  2. DEFINITIONAL matched the substring "என்ன" ("what") inside "என்னால்"
     ("by me"), so a patent question was routed to the descriptive corpus.
  3. Routing read the machine translation rather than the user's own words, so
     a mistranslation could change what kind of question the system answered.
  4. Every fallback path emitted English scaffolding regardless of language.

No test here requires a model. The parts worth pinning are the deterministic
ones; the model is exactly the part that cannot be pinned.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.language import Language, detect  # noqa: E402
from core.localise import STRINGS, t  # noqa: E402
from rag.answer import (  # noqa: E402
    ExtractiveAnswerer,
    abstention_text,
    clip_quote,
    dedupe_sentences,
    trim_incomplete,
)
from rag.concepts import load_concepts, norm  # noqa: E402
from rag.retriever import DEFINITIONAL, load_retriever  # noqa: E402

TAMIL_PATENT = "கிலோய்க்கு (Giloy) என்னால் காப்புரிமை பெற முடியுமா?"


@pytest.fixture(scope="module")
def retriever():
    return load_retriever()


# --------------------------------------------------------------- norm ------
def test_norm_keeps_indic_vowel_signs():
    """A vowel sign is category Mn, not \\w. Stripping it destroys the word."""
    assert "காப்புரிமை" in norm(TAMIL_PATENT).split()
    # ...and the same for the other scripts the lexicon now carries.
    for word in ["పేటెంట్", "ಭಾರತ", "പേറ്റന്റ്", "পেটেন্ট", "પેટન્ટ", "पेटेंट"]:
        assert word in norm(f"x {word} y").split(), word


def test_norm_still_strips_punctuation():
    assert norm("Can I patent my formulation?") == "can i patent my formulation"


# -------------------------------------------------------- concept layer ----
def test_indic_questions_match_concepts():
    ci = load_concepts()
    cases = {
        TAMIL_PATENT: "TK_PATENTABILITY",
        "பயன் பகிர்வு என்றால் என்ன?": "BENEFIT_SHARING",
        "வர்த்தக முத்திரை பதிவு செய்ய முடியுமா?": "TRADEMARK_GROUNDS",
        "क्या मैं गिलोय का पेटेंट करा सकता हूँ": "TK_PATENTABILITY",
    }
    for question, expected in cases.items():
        matched = [m.concept.id for m in ci.match(question)]
        assert expected in matched, f"{question!r} -> {matched}"


def test_lexicon_provisions_all_resolve():
    assert load_concepts().problems == []


# ------------------------------------------------------------- routing -----
def test_definitional_does_not_fire_on_tamil_instrumental():
    """"என்னால்" is "by me", not "what"."""
    assert not DEFINITIONAL.search(TAMIL_PATENT)


def test_definitional_still_fires_on_a_real_question():
    assert DEFINITIONAL.search("ஆயுர்வேதம் என்ன?")
    assert DEFINITIONAL.search("What is Ayurveda?")
    assert not DEFINITIONAL.search("can i patent giloy")


def test_tamil_patent_question_reaches_the_patents_act(retriever):
    """The whole bug in one assertion: a legal question, answered from law."""
    res = retriever.search(TAMIL_PATENT, k=6, citable_only=True)
    assert not res.background_only
    assert not res.is_weak
    assert res.layer == "IN"
    assert res.hits[0].record["act_id"] == "IN.PATENTS.1970"
    assert res.hits[0].record["authority_rank"] == 1


def test_routing_ignores_a_bad_translation(retriever):
    """A mistranslation may cost ranking. It may not change the question type.

    The observed failure rendered the Tamil above as "What is the medicinal
    use of Giloy (Licorice)?" -- definitional, and about a different plant.
    """
    res = retriever.search(
        TAMIL_PATENT + " What is the medicinal use of Giloy?",
        k=6, citable_only=True,
    )
    assert not res.background_only


# ------------------------------------------------------- answer language ---
def test_extractive_scaffolding_is_localised(retriever):
    """The fallback every other path degrades to must speak the user's language.

    A concept matches this question, so it is the `concept` string that is
    expected; the assertion is on the invariant part of the sentence, since
    the concept label itself stays in English by the terminology lock.
    """
    res = retriever.search(TAMIL_PATENT, k=6, citable_only=True)
    text = ExtractiveAnswerer().write(TAMIL_PATENT, res)
    tail = t("ta", "concept", label="X").split("X", 1)[1].strip()
    assert tail in text
    assert t("ta", "quote_note") in text
    # The quote itself stays in the language of the statute.
    assert "Patents Act" in text
    assert "Answering from" not in text and "provision in the ingested" not in text


def test_abstention_is_localised():
    ta = abstention_text(detect(TAMIL_PATENT), "no provision scored high enough")
    assert t("ta", "abstention") in ta
    assert t("ta", "why") in ta
    en = abstention_text(detect("what is the EPO opposition period"), "reason")
    assert en.startswith("I don't have authority")


def test_every_language_row_is_complete():
    keys = set(STRINGS["en"])
    for code, row in STRINGS.items():
        assert set(row) == keys, code
        assert "{label}" in row["concept"], code


def test_unknown_language_falls_back_to_english():
    assert t("xx", "why") == "Why"


# ---------------------------------------------------------- truncation -----
def test_trim_incomplete_drops_a_clipped_tail():
    text = ("Under Section 21 the Authority must secure benefit sharing. "
            "Where biological resources or")
    out = trim_incomplete(text)
    assert out.endswith("benefit sharing.")
    assert "Where biological" not in out


def test_trim_incomplete_keeps_a_finished_answer():
    text = "The Authority must secure benefit sharing."
    assert trim_incomplete(text) == text


def test_trim_incomplete_never_empties_a_single_fragment():
    """One unfinished sentence is all there is. Show it rather than nothing."""
    text = "The Authority must secure"
    assert trim_incomplete(text) == text


def test_dedupe_removes_a_restatement():
    text = ("The Authority determines equitable benefit sharing. "
            "Equitable benefit sharing is determined by the Authority. "
            "It may order monetary compensation.")
    out = dedupe_sentences(text)
    assert out.count("determin") == 1
    assert "monetary compensation" in out


def test_clip_quote_ends_on_a_boundary():
    body = ("First sentence here. " * 60).strip()
    out = clip_quote(body, 200)
    assert len(out) <= 210
    assert out.endswith("…")
    assert not out.rstrip(" …").endswith("sentenc")


# ------------------------------------------------- localisation guards -----
def test_localisation_rejects_a_degenerate_translation():
    from rag.translate import _degenerate

    loop = "பெரிய அமைச்சரம் முதன்மையாக உள்ள தேவை " * 6
    assert _degenerate(loop)
    assert not _degenerate("இது ஒரு சாதாரண தமிழ் வாக்கியம் ஆகும்.")


def test_localisation_rejects_the_wrong_script():
    from rag.translate import _script_ratio

    ta = Language("ta", "Tamil", "தமிழ்", "indic", 1.0)
    assert _script_ratio("இது தமிழ் வாக்கியம்", ta) > 0.9
    assert _script_ratio("This is an English sentence.", ta) < 0.1


def test_localise_answer_is_a_no_op_without_a_model(monkeypatch):
    """No capable model installed is a supported state, not an error."""
    import rag.translate as tr

    monkeypatch.setattr(tr, "localisation_model", lambda: None)
    ta = Language("ta", "Tamil", "தமிழ்", "indic", 1.0)
    text = "Section 3(p) excludes traditional knowledge."
    out, ok = tr.localise_answer(text, ta)
    assert out == text and ok is False
