"""Translation, in both directions, on opposite terms.

INBOUND (for_retrieval) -- an Indic question is translated to English so the
English corpus can be searched. The translation is a search key only.

OUTBOUND (localise_answer) -- a verified English answer is translated into the
user's language so the answer is readable. This one is gated: the output has to
be in the right script, non-degenerate, and must have preserved every section
number, Act name and citation marker verbatim, or it is discarded and the
English is returned with a note. An answer the user cannot check is worse than
an answer in the wrong language.

The order matters and is the point: draft and verify in English, translate
last. Verifying Tamil prose against English statutory spans is not
verification, because the two share no words -- the coverage test passes
everything, and the groundedness score it reports is fiction.

Query translation for retrieval.

The corpus is English: the Acts, the Rules, the TKDL annexures, the AYUSH
reference material. A question typed in Devanagari or Tamil therefore retrieves
almost nothing, because the tokeniser and both retrievers work on Latin script.
Answering in the user's language is worthless if the retrieval that feeds the
answer never fired.

So an Indic-script query is translated to English *for retrieval only*, and the
answer is generated back in the original language. Three things make this safe:

  * The translation is only ever used as a search key. It never becomes part of
    an answer and is never cited.
  * The original query is kept and shown, so a user can see what was searched.
  * Translation failures degrade rather than break: we fall back to the
    resolver's transliteration plus the concept lexicon, both of which already
    carry Devanagari entries.

The concept lexicon is checked FIRST and, when it matches, translation is
skipped entirely -- "क्या मैं गिलोय का पेटेंट करा सकता हूँ" is answered by the
lexicon and the taxon resolver without any model in the loop.
"""
from __future__ import annotations

from functools import lru_cache

import os
import re

from core.language import IMMUTABLE, Language, detect
from core.localise import t as localised

SYSTEM = (
    "You translate a user's question into English so it can be used as a "
    "search query over Indian statutes. Output ONLY the English translation, "
    "nothing else. No preamble, no quotes, no explanation. Keep proper nouns, "
    "plant names and legal terms. Preserve the intent exactly: a question about "
    "permission ('can I ...') must stay a question about permission, and a "
    "question about a rule must not become a question about a definition. Do "
    "not add any fact the source does not contain. If the text is already "
    "English, repeat it unchanged."
)


@lru_cache(maxsize=512)
def _translate(text: str, model: str | None = None) -> str:
    """Question -> English search key.

    Bhashini first when it is configured, because this is the step where the
    small local models fail worst and fail silently: qwen2.5:1.5b turns the
    Tamil for "can I get a patent for Giloy?" into "What is the medicinal use
    of Giloy (Licorice)?" -- wrong intent, wrong plant, and nothing downstream
    can tell. A mistranslated search key does not produce a wrong answer here,
    it produces a confident answer to a question nobody asked.

    Bhashini being unreachable is not an error state: the local model is still
    there, and the caller's own fallback keeps the original query as the search
    text if that fails too.
    """
    from rag import bhashini

    if bhashini.enabled():
        lang = detect(text)
        if not lang.is_english and lang.code in bhashini.SUPPORTED:
            try:
                return bhashini.translate(text, lang.code, "en")
            except Exception:
                pass                  # fall through to the local model

    from rag.llm import Ollama

    client = Ollama(model or best_translation_model())
    out = client.generate(
        f"Translate this question into English:\n\n{text}", SYSTEM,
        temperature=0.0, num_predict=90,
    ).strip()
    # A chatty model sometimes prefixes "Translation:" or wraps in quotes.
    for prefix in ("translation:", "english:", "answer:"):
        if out.lower().startswith(prefix):
            out = out[len(prefix):].strip()
    return out.strip('"“”\' \n')


def for_retrieval(query: str, *, model: str | None = None,
                  enabled: bool = True) -> tuple[str, Language, str]:
    """Return (search_text, detected_language, translation_or_empty).

    search_text is the original query with the English translation appended --
    appended rather than substituted, so a query that is already half-English
    (very common: "मेरा churna patent हो सकता है?") keeps its English terms.
    """
    lang = detect(query)
    if lang.script != "indic" or not enabled:
        return query, lang, ""
    try:
        english = _translate(query, model)
    except Exception:
        return query, lang, ""
    if not english or english.lower() == query.lower():
        return query, lang, ""
    return f"{query} {english}", lang, english


# =========================================================================
# Model choice
#
# The default generator is chosen for speed, because it only has to phrase
# text that retrieval already found. Translation is a different job with a
# different failure mode, and the fastest installed model is measurably bad
# at it: qwen2.5:1.5b renders the Tamil for "can I get a patent for Giloy?"
# as "What is the medicinal use of Giloy (Licorice)?" -- wrong intent, wrong
# plant, no warning. So the translation step is allowed to pick a bigger
# model than the answering step, and pays the extra second for it.
#
# Writing INTO an Indic language is harder still, and nothing in the small
# local range does it acceptably: measured on this machine, qwen2.5:1.5b and
# mistral:7b both collapse into repetition loops in Tamil and llama3.2:3b
# silently translates "Section" -- which the terminology lock forbids. So a
# model is only trusted to localise an answer if it is on the list below AND
# its output passes the guards in localise_answer(). Absent such a model the
# system localises its own scaffolding (core.localise, hand-written and
# deterministic) and leaves the paraphrase in English, which is a legible
# answer rather than a fluent wrong one.
# =========================================================================
TRANSLATION_PREFERRED = [
    "gemma3:12b", "gemma3:4b", "gemma2:9b",
    "qwen2.5:7b", "llama3.1:latest", "llama3.1:8b",
    "mistral:latest", "llama3:latest", "llama3.2:latest",
]

# Models trusted to WRITE an Indic language. Deliberately short: presence on
# this list is necessary, never sufficient -- every output is still gated.
INDIC_CAPABLE = (
    "gemma3", "gemma2", "aya", "sarvam", "navarasa", "airavata",
    "qwen2.5:7b", "qwen2.5:14b", "qwen2.5:32b", "qwen3",
    "llama3.1:70b", "mistral-nemo", "command-r",
)


def _installed() -> list[str]:
    from rag.llm import installed_models

    try:
        return installed_models()
    except Exception:
        return []


def best_translation_model() -> str | None:
    """The best installed model for query translation, or None for the default."""
    override = os.environ.get("AYURLEX_TRANSLATE_MODEL")
    if override:
        return override
    have = _installed()
    return next((m for m in TRANSLATION_PREFERRED if m in have), None)


def localisation_model() -> str | None:
    """An installed model trusted to write the answer in an Indic language.

    None means "nobody here can do this", which is a supported state, not an
    error: the caller keeps the English paraphrase and says so in the user's
    language. Set AYURLEX_LOCALISE_MODEL to force a specific model, or
    AYURLEX_LOCALISE=0 to turn the whole step off.
    """
    if os.environ.get("AYURLEX_LOCALISE", "1") == "0":
        return None
    forced = os.environ.get("AYURLEX_LOCALISE_MODEL")
    if forced:
        return forced
    for name in _installed():
        if any(name.startswith(p) or name == p for p in INDIC_CAPABLE):
            return name
    return None


# --------------------------------------------------------------- guards ----
# A degenerate model loops. qwen2.5:1.5b asked for Tamil produced the same
# nine-word clause five times and nothing else; the answer looked like Tamil
# and meant nothing. Repetition is the cheapest reliable signal for that.
def _degenerate(text: str, *, n: int = 6, limit: int = 2) -> bool:
    words = text.split()
    if len(words) < n * 2:
        return False
    grams: dict[tuple, int] = {}
    for i in range(len(words) - n + 1):
        g = tuple(words[i:i + n])
        grams[g] = grams.get(g, 0) + 1
    return max(grams.values()) > limit


def _script_ratio(text: str, lang: Language) -> float:
    """Share of the letters that are actually in the target script."""
    from core.language import SCRIPT_RE

    rx = next((r for r, code, _n, _e in SCRIPT_RE if code == lang.code), None)
    if rx is None:
        return 1.0
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return len(rx.findall(text)) / len(letters)


CITE = re.compile(r"\[\d+\]")

LOCALISE_SYSTEM = """You translate a finished English answer into {name} ({endonym}).

Output ONLY the translation. No preamble, no notes, no English gloss of your own.

NEVER translate, and reproduce exactly as written in Latin script:
- section, rule and form numbers, and the word Section/Rule/Form before them
- names of Acts, Rules, Treaties and Conventions, and any year
- the citation markers [1] [2] [3]
- these terms of art: prior art, specification, traditional knowledge, benefit \
sharing, geographical indication, trade mark, Controller, National Biodiversity \
Authority, State Biodiversity Board

Do not add, remove, soften or strengthen any statement. Translate what is there."""


def passes_guards(source: str, out: str, lang: Language) -> bool:
    """The four guards every localisation must pass, whoever produced it.

    Each one is a failure actually observed on this machine, and none of them
    is relaxed for a better translator. Bhashini goes through this function on
    exactly the same terms as a local model does: being the national language
    infrastructure makes it a better translator, not a trusted one.
    """
    if not out or _degenerate(out):
        return False
    if _script_ratio(out, lang) < 0.5:
        return False
    # Every immutable token -- section numbers, Act names, years -- must have
    # survived verbatim. llama3.2 renders "Section 21" as "பிரிவு 21", and a
    # user who writes that on a form has been harmed by the translation.
    for token in set(IMMUTABLE.findall(source)):
        if token not in out:
            return False
    return not (set(CITE.findall(source)) - set(CITE.findall(out)))


def _localise_via_bhashini(text: str, lang: Language) -> str | None:
    """Translate through Bhashini, with the immutable tokens masked.

    Masking is what makes a real NMT system usable here at all. Bhashini will
    faithfully translate "Section 21", which is the one thing the terminology
    lock forbids -- so the section numbers, Act names, years and citation
    markers are lifted out before the text is sent and put back afterwards.
    The guards still run on the result: a mask the service drops is caught
    there, and the answer falls back to English rather than going out short a
    citation.

    Returns None on any failure, which the caller reads as "try the local
    model", never as "give up".
    """
    from rag import bhashini

    if not bhashini.enabled() or lang.code not in bhashini.SUPPORTED:
        return None
    tokens = list(IMMUTABLE.findall(text)) + list(CITE.findall(text))
    masked, mapping = bhashini.protect(text, tokens)
    try:
        out = bhashini.translate(masked, "en", lang.code)
    except Exception:
        return None
    return bhashini.restore(out, mapping).strip()


def localise_answer(text: str, lang: Language, *, model: str | None = None
                    ) -> tuple[str, bool]:
    """Render a verified English answer in the user's language.

    Returns (text, localised). `localised` is False when the answer is being
    returned in English because no trustworthy localisation could be produced,
    which the caller reports to the user rather than hiding.

    The answer is drafted and verified in English and only then translated, so
    that the citation gate runs on text it can actually check. Gating Tamil
    prose against English statutory spans is not verification -- it is a
    coverage test with no words in common, which passes everything.

    Two translators are tried in order and both face the same guards. Bhashini
    goes first when configured, because writing into an Indic language is the
    job nothing in the small local range does acceptably -- measured here,
    qwen2.5:1.5b and mistral:7b both collapse into repetition loops in Tamil.
    An explicit `model` argument means the caller is asking for that model, so
    Bhashini is skipped.
    """
    if lang.is_english or not text.strip():
        return text, False

    if model is None:
        out = _localise_via_bhashini(text, lang)
        if out and passes_guards(text, out, lang):
            return out, True

    name = model or localisation_model()
    if not name:
        return text, False

    from rag.llm import Ollama

    try:
        client = Ollama(name)
        out = client.generate(
            text,
            LOCALISE_SYSTEM.format(name=lang.name, endonym=lang.endonym),
            temperature=0.0, num_predict=max(320, len(text.split()) * 6),
        ).strip()
    except Exception:
        return text, False

    if not passes_guards(text, out, lang):
        return text, False
    return out, True


def english_note(lang: Language) -> str:
    """The line shown when the paraphrase had to stay in English."""
    return localised(lang.code, "english_note")
