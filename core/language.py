"""Language detection and the terminology lock.

Two jobs, and the second is the one that matters legally.

1. Detect the language of a question so the answer comes back in it. Detection
   is by Unicode block first (unambiguous for the Indic scripts) and then by a
   small function-word test for romanised Indic typed on a QWERTY keyboard,
   which is how a great many users actually write Hindi.

2. Hold the terminology lock. Statutory terms -- "prior art", "specification",
   section numbers, form numbers, the names of Acts -- are NEVER machine
   translated. They are substituted from the glossary or left in English with a
   translated gloss in parentheses. Machine-translating "prior art" into Tamil
   produces a phrase no examiner recognises, and a user who then writes it on a
   form has been actively harmed by the translation.

The citation itself is always rendered in the original language of the statute,
alongside any translation. A translated quote is a paraphrase, and a paraphrase
is not authority.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Unicode blocks -> (code, English name, endonym).
SCRIPTS: list[tuple[str, str, str, str]] = [
    ("ऀ-ॿ", "hi", "Hindi", "हिन्दी"),
    ("஀-௿", "ta", "Tamil", "தமிழ்"),
    ("ఀ-౿", "te", "Telugu", "తెలుగు"),
    ("ಀ-೿", "kn", "Kannada", "ಕನ್ನಡ"),
    ("ഀ-ൿ", "ml", "Malayalam", "മലയാളം"),
    ("ঀ-৿", "bn", "Bengali", "বাংলা"),
    ("઀-૿", "gu", "Gujarati", "ગુજરાતી"),
    ("਀-੿", "pa", "Punjabi", "ਪੰਜਾਬੀ"),
    ("଀-୿", "or", "Odia", "ଓଡ଼ିଆ"),
    ("؀-ۿ", "ur", "Urdu", "اردو"),
]
SCRIPT_RE = [(re.compile(f"[{blk}]"), code, name, endo)
             for blk, code, name, endo in SCRIPTS]

LANG_NAMES = {code: name for _, code, name, _ in SCRIPTS}
LANG_NAMES["en"] = "English"
ENDONYMS = {code: endo for _, code, _, endo in SCRIPTS}
ENDONYMS["en"] = "English"

# Romanised Indic function words. Deliberately small and high-precision: these
# words are rare in English legal questions, so a hit is strong evidence.
ROMANISED = {
    "hi": {"kya", "kaise", "kaun", "mera", "meri", "hai", "hain", "nahi",
           "nahin", "karna", "karne", "kar", "sakta", "sakte", "sakti",
           "chahiye", "kitna", "kitne", "kab", "kyun", "kyon", "aur", "ke",
           "ki", "ka", "mein", "par", "liye", "wala", "hota", "hoti"},
    "ta": {"enna", "eppadi", "yaar", "enakku", "irukku", "seyya", "mudiyuma",
           "vendum", "illai", "epo"},
    "te": {"enti", "ela", "evaru", "naaku", "cheyyagalana", "kavali", "ledu"},
}


@dataclass
class Language:
    code: str
    name: str
    endonym: str
    script: str          # "indic" | "latin"
    confidence: float

    @property
    def is_english(self) -> bool:
        return self.code == "en"


def detect(text: str) -> Language:
    """Script first, then romanised function words, then English."""
    counts: dict[str, int] = {}
    for rx, code, _name, _endo in SCRIPT_RE:
        n = len(rx.findall(text))
        if n:
            counts[code] = n
    if counts:
        code = max(counts, key=lambda c: counts[c])
        total = sum(counts.values())
        letters = sum(1 for ch in text if ch.isalpha()) or 1
        return Language(code, LANG_NAMES[code], ENDONYMS[code], "indic",
                        min(1.0, total / letters + 0.35))

    words = set(re.findall(r"[a-z]+", text.lower()))
    for code, markers in ROMANISED.items():
        hits = words & markers
        if len(hits) >= 2:
            return Language(code, LANG_NAMES[code], ENDONYMS[code], "latin",
                            min(1.0, 0.4 + 0.15 * len(hits)))
    return Language("en", "English", "English", "latin", 1.0)


# --------------------------------------------------------------- glossary ---
# Terms that must survive translation intact. The value is the gloss offered in
# parentheses, not a replacement.
LOCKED_TERMS: dict[str, str] = {
    "prior art": "existing public knowledge that can defeat a patent",
    "specification": "the written description filed with a patent application",
    "complete specification": "the full patent description",
    "provisional specification": "the preliminary patent description",
    "traditional knowledge": "knowledge held by a community over generations",
    "benefit sharing": "sharing the gains from using a biological resource",
    "biological resource": "plant, animal or microbial material",
    "geographical indication": "a sign identifying goods from a region",
    "trade mark": "a sign distinguishing one trader's goods",
    "Controller": "the Controller of Patents",
    "National Biodiversity Authority": "the national access-and-benefit "
                                       "sharing regulator",
    "State Biodiversity Board": "the state-level biodiversity regulator",
    "the Schedule": "the list attached to the Act",
    "Section": "a numbered provision of an Act",
    "prima facie": "on the face of it",
}

# Anything matching these must never be rewritten by a model: section numbers,
# form numbers, Act names with years, clause references.
IMMUTABLE = re.compile(
    r"\b(?:[Ss]ection\s+\d+[A-Za-z]*(?:\([^)]{1,4}\))*"
    r"|[Rr]ule\s+\d+[A-Za-z]*"
    r"|Form\s+\d+[A-Za-z]*"
    r"|(?:Act|Rules),?\s+\d{4}"
    r"|\d{4})\b"
)


def locked_terms_in(text: str) -> list[tuple[str, str]]:
    low = text.lower()
    return [(t, g) for t, g in LOCKED_TERMS.items() if t.lower() in low]


def immutable_tokens(text: str) -> list[str]:
    return IMMUTABLE.findall(text)


def translation_instruction(lang: Language) -> str:
    """The language clause handed to the generator.

    Note what it does NOT say: it never asks the model to translate the quoted
    statutory text. Quotes stay in the language of the statute, because a
    translated quote is a paraphrase and a paraphrase is not authority.
    """
    if lang.is_english:
        return (
            "Answer in English. Keep statutory terms and section numbers "
            "exactly as they appear in the extracts."
        )
    return (
        f"Answer in {lang.name} ({lang.endonym}), the language of the "
        f"question.\n"
        f"TERMINOLOGY LOCK — this overrides the instruction to answer in "
        f"{lang.name}:\n"
        f"- Never translate a section number, rule number, form number, Act "
        f"name or year. Write them in English/Latin script exactly as given.\n"
        f"- Never translate the legal terms of art (prior art, specification, "
        f"traditional knowledge, benefit sharing, geographical indication, "
        f"trade mark, Controller, National Biodiversity Authority). Keep the "
        f"English term and add a short {lang.name} gloss in brackets the first "
        f"time it appears.\n"
        f"- Quoted statutory text stays in its original English. You may add a "
        f"{lang.name} explanation after the quote, but the quote itself is "
        f"the authority and must not be rewritten."
    )
