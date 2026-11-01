"""Tests for the Bhashini integration.

Nothing here touches the network. What is worth pinning is not that Bhashini
translates well -- that is its job, and it changes -- but the three properties
this repository is answerable for:

  1. It is off unless somebody configured it. A user who has not set
     credentials must never have their question leave the machine, and no test
     environment should be able to make one leave by accident.
  2. Its output faces exactly the same guards as a local model's. Being the
     national language infrastructure makes Bhashini a better translator, not
     a trusted one.
  3. Section numbers, Act names and citation markers survive the round trip.
     That is the terminology lock, and it is the one thing a real NMT system
     will break by default, because translating "Section 21" is precisely what
     a good translator does.

The transport is faked at rag.bhashini.translate rather than at the socket, so
these stay fast and stay honest about what they cover: the wire format is
exercised by `python cli.py bhashini --probe`, which needs credentials.
"""
from __future__ import annotations

import pytest

from core.language import Language
from rag import bhashini

TA = Language("ta", "Tamil", "தமிழ்", "indic", 1.0)
HI = Language("hi", "Hindi", "हिन्दी", "indic", 1.0)


@pytest.fixture(autouse=True)
def _no_credentials(monkeypatch):
    """Every test starts from "not configured", whatever the machine has set."""
    for var in ("BHASHINI_USER_ID", "BHASHINI_API_KEY", "AYURLEX_BHASHINI",
                "BHASHINI_PIPELINE_ID"):
        monkeypatch.delenv(var, raising=False)
    bhashini._CACHE.clear()


def _configure(monkeypatch):
    monkeypatch.setenv("BHASHINI_USER_ID", "test-user")
    monkeypatch.setenv("BHASHINI_API_KEY", "test-key")


# ------------------------------------------------------------ off by default --
def test_disabled_without_credentials():
    assert not bhashini.configured()
    assert not bhashini.enabled()
    st = bhashini.status()
    assert st.configured is False and st.enabled is False
    assert "not configured" in st.detail


def test_enabled_once_credentials_are_set(monkeypatch):
    _configure(monkeypatch)
    assert bhashini.enabled()
    assert bhashini.status().enabled is True


def test_kill_switch_beats_credentials(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("AYURLEX_BHASHINI", "0")
    assert bhashini.configured() and not bhashini.enabled()
    assert "switched off" in bhashini.status().detail


def test_translate_refuses_without_credentials():
    with pytest.raises(bhashini.BhashiniUnavailable):
        bhashini.translate("क्या मैं पेटेंट करा सकता हूँ", "hi", "en")


def test_unsupported_language_is_refused_not_guessed(monkeypatch):
    _configure(monkeypatch)
    with pytest.raises(bhashini.BhashiniUnavailable):
        bhashini.translate("hello", "en", "fr")


# ---------------------------------------------------------------- masking ----
def test_masking_round_trips_immutable_tokens():
    text = "Section 6(1) of the Biological Diversity Act, 2002 applies [1]."
    tokens = ["Section 6(1)", "Act, 2002", "[1]"]
    masked, mapping = bhashini.protect(text, tokens)
    for tok in tokens:
        assert tok not in masked
    assert bhashini.restore(masked, mapping) == text


def test_masking_prefers_the_longer_token():
    """A short token inside a longer one must not be masked out from under it.

    "2002" is an immutable token in its own right and also sits inside
    "Act, 2002". Masking the short one first leaves a mask embedded in the
    longer match, and the longer token then never restores.
    """
    text = "The Act, 2002 was amended in 2023."
    masked, mapping = bhashini.protect(text, ["2002", "Act, 2002", "2023"])
    assert bhashini.restore(masked, mapping) == text


def test_restore_survives_a_respaced_mask():
    """A translator that keeps a mask may still respace or recase it.

    Leaving "saktiref 0 x" in a user-facing answer would be worse than either
    the token or an outright rejection, so the restore is deliberately
    tolerant about the shape of what comes back.
    """
    masked, mapping = bhashini.protect("See Section 21 today.", ["Section 21"])
    mangled = masked.replace(bhashini.MASK.format(0), "saktiref 0 x")
    assert "Section 21" in bhashini.restore(mangled, mapping)


def test_restore_leaves_an_unknown_mask_alone():
    """A mask that was never issued is not silently invented into a citation."""
    out = bhashini.restore("stray SAKTIREF9X here", {})
    assert out == "stray SAKTIREF9X here"


# ------------------------------------------------- the guards still apply ----
def test_localisation_through_bhashini_passes_the_guards(monkeypatch):
    _configure(monkeypatch)
    import rag.translate as tr

    text = "Section 6(1) of the Biological Diversity Act, 2002 applies [1]."

    def fake(masked: str, src: str, tgt: str, **kw) -> str:
        assert (src, tgt) == ("en", "ta")
        # A real NMT run keeps the masks and translates everything else.
        return "உயிரியல் " + masked.replace("of the Biological Diversity", "") \
                                   .replace("applies", "பொருந்தும்")

    monkeypatch.setattr(bhashini, "translate", fake)
    out, ok = tr.localise_answer(text, TA)
    assert ok is True
    assert "Section 6(1)" in out and "Act, 2002" in out and "[1]" in out


def test_a_dropped_citation_marker_is_rejected(monkeypatch):
    """Bhashini gets no exemption from the citation guard."""
    _configure(monkeypatch)
    import rag.translate as tr

    text = "Section 21 requires benefit sharing [1]."
    monkeypatch.setattr(
        bhashini, "translate",
        lambda masked, src, tgt, **kw: "பயன் பகிர்வு தேவை.")
    monkeypatch.setattr(tr, "localisation_model", lambda: None)
    out, ok = tr.localise_answer(text, TA)
    assert ok is False and out == text


def test_a_wrong_script_answer_is_rejected(monkeypatch):
    _configure(monkeypatch)
    import rag.translate as tr

    text = "Section 21 requires benefit sharing [1]."
    monkeypatch.setattr(
        bhashini, "translate",
        lambda masked, src, tgt, **kw: masked)     # echoed back in English
    monkeypatch.setattr(tr, "localisation_model", lambda: None)
    out, ok = tr.localise_answer(text, HI)
    assert ok is False and out == text


def test_bhashini_failure_falls_through_rather_than_breaking(monkeypatch):
    """An unreachable service is a degradation, never an error the user sees."""
    _configure(monkeypatch)
    import rag.translate as tr

    def boom(*a, **kw):
        raise bhashini.BhashiniUnavailable("network down")

    monkeypatch.setattr(bhashini, "translate", boom)
    monkeypatch.setattr(tr, "localisation_model", lambda: None)
    text = "Section 21 requires benefit sharing."
    out, ok = tr.localise_answer(text, TA)
    assert out == text and ok is False


def test_query_translation_prefers_bhashini(monkeypatch):
    _configure(monkeypatch)
    import rag.translate as tr

    tr._translate.cache_clear()
    monkeypatch.setattr(
        bhashini, "translate",
        lambda text, src, tgt, **kw: "can I patent my formulation")

    def no_ollama(*a, **kw):
        raise AssertionError("the local model must not be reached")

    monkeypatch.setattr(tr, "best_translation_model", no_ollama)
    search, lang, english = tr.for_retrieval("क्या मैं पेटेंट करा सकता हूँ")
    assert lang.code == "hi"
    assert english == "can I patent my formulation"
    # Appended, not substituted: a half-English question keeps its own terms.
    assert search.startswith("क्या")
    tr._translate.cache_clear()


def test_query_translation_survives_bhashini_being_down(monkeypatch):
    """The original query is still a usable search key. Nothing raises."""
    _configure(monkeypatch)
    import rag.translate as tr

    tr._translate.cache_clear()

    def boom(*a, **kw):
        raise bhashini.BhashiniUnavailable("network down")

    monkeypatch.setattr(bhashini, "translate", boom)
    monkeypatch.setattr(tr, "best_translation_model",
                        lambda: (_ for _ in ()).throw(RuntimeError("no model")))
    search, lang, english = tr.for_retrieval("क्या मैं पेटेंट करा सकता हूँ")
    assert lang.code == "hi" and english == ""
    assert search == "क्या मैं पेटेंट करा सकता हूँ"
    tr._translate.cache_clear()
