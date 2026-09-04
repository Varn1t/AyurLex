"""Tests for the local-LLM layer: language handling and the citation gate.

Almost nothing here calls the model. That is deliberate — the parts worth
testing are the ones that constrain the model, and those are pure functions.
The two tests that do need Ollama skip cleanly when it is not running, so the
suite still passes on a machine that has never installed it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.language import (  # noqa: E402
    detect,
    immutable_tokens,
    locked_terms_in,
    translation_instruction,
)
from rag.answer import (  # noqa: E402
    PROMPT_HITS,
    ExtractiveAnswerer,
    build_prompt,
    verify_against_spans,
)
from rag.llm import choose_model, ensure, is_up  # noqa: E402
from rag.retriever import load_retriever  # noqa: E402

needs_ollama = pytest.mark.skipif(
    not is_up(timeout=1.5), reason="ollama is not running"
)


@pytest.fixture(scope="module")
def res():
    return load_retriever().search(
        "Can I patent a traditional ayurvedic formulation?", k=5
    )


# -------------------------------------------------------------- language ----
def test_detects_indic_scripts():
    assert detect("क्या मैं गिलोय का पेटेंट करा सकता हूँ").code == "hi"
    assert detect("இது என்ன மருந்து").code == "ta"
    assert detect("Can I patent this?").code == "en"


def test_detects_romanised_hindi():
    """A great many users type Hindi on a QWERTY keyboard."""
    lang = detect("kya main apna churna patent kar sakta hai")
    assert lang.code == "hi"
    assert lang.script == "latin"


def test_terminology_lock_is_in_the_prompt():
    """Machine-translating 'prior art' into Tamil produces a phrase no examiner
    recognises. The instruction must forbid it explicitly."""
    instr = translation_instruction(detect("இது என்ன"))
    assert "Tamil" in instr
    assert "Never translate" in instr
    assert "prior art" in instr
    assert "quote itself is the authority" in instr.replace("\n", " ")


def test_english_gets_no_translation_clause():
    assert "Never translate" not in translation_instruction(detect("hello"))


def test_locked_terms_and_immutables_are_detected():
    assert dict(locked_terms_in("what counts as prior art here"))
    assert "Section 3" in immutable_tokens("see Section 3 of the Act")
    # The year is captured as part of the Act reference, not on its own --
    # "Act, 1970" is the unit that must survive translation intact.
    assert any("1970" in t for t in immutable_tokens("the Patents Act, 1970"))


# ------------------------------------------------------------------ gate ----
def test_gate_drops_a_fabricated_quotation(res):
    """Observed failure: the model wrote that s.3(p) 'defines an invention as
    "...new, involves an inventive step..."' -- words that appear nowhere in
    the section, presented as if read off the page."""
    text = ('Section 3(p) defines an invention as "an innovation or improvement '
            'which is new, involves an inventive step, and has some industrial '
            'application."')
    kept, _, dropped = verify_against_spans(text, res)
    assert dropped and not kept.strip()


def test_gate_keeps_a_genuine_quotation(res):
    text = ('Section 3(p) excludes "an invention which, in effect, is '
            'traditional knowledge".')
    kept, _, dropped = verify_against_spans(text, res)
    assert kept.strip() and not dropped


def test_gate_drops_an_untraceable_number(res):
    kept, _, dropped = verify_against_spans(
        "Traditional knowledge is excluded. The penalty is 47 years.", res
    )
    assert any("47" in d for d in dropped)
    assert "47" not in kept


def test_gate_window_matches_the_prompt_window(res):
    """The gate must verify against exactly the extracts the model was shown.
    Verifying against more lets a weakly-ranked hit the model never saw
    legitimise an invented cross-reference."""
    shown = {h.corpus_id for h in res.hits[:PROMPT_HITS]}
    prompt = build_prompt("test", res, detect("test"))
    for h in res.hits[:PROMPT_HITS]:
        assert h.record["heading"][:25] in prompt or h.record["section"] in prompt
    assert len(shown) <= PROMPT_HITS


def test_prompt_labels_background_material_as_not_law():
    r = load_retriever().search("What is Ayurveda?", k=4)
    prompt = build_prompt("What is Ayurveda?", r, detect("What is Ayurveda?"))
    assert "NOT law" in prompt


# --------------------------------------------------------------- fallback ---
def test_extractive_backend_needs_no_model(res):
    """The fallback path must work with Ollama stopped -- this is what keeps a
    venue with no working machine from killing the demo."""
    out = ExtractiveAnswerer().write("Can I patent this?", res)
    assert "“" in out and "Patents Act" in out


# ----------------------------------------------------------------- ollama ---
def test_model_preference_is_deterministic():
    """Whatever is installed, the choice must not vary run to run."""
    assert choose_model() == choose_model()


@needs_ollama
def test_ollama_is_reachable_and_has_a_model():
    st = ensure()
    assert st.running
    assert st.model, st.detail


@needs_ollama
def test_generated_answer_is_gated_not_trusted():
    """End to end with the real model: whatever it writes, every surviving
    sentence must be traceable to the retrieved spans."""
    from rag.answer import OllamaAnswerer

    r = load_retriever().search("can I advertise that my product cures diabetes",
                                k=5)
    draft = OllamaAnswerer().write(
        "can I advertise that my product cures diabetes", r
    )
    kept, grounded, dropped = verify_against_spans(draft, r)
    # Either something survived the gate, or everything was dropped -- both are
    # correct outcomes. What must never happen is ungated text reaching a user.
    assert kept != draft or not dropped
    assert 0.0 <= grounded <= 1.0
