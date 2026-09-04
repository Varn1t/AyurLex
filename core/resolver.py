"""RESOLVER: raw ingredient name (any language, any script) -> canonical taxon.

This is where multilingual does functional work rather than cosmetic work. The
statutory schedules and the prior-art index are keyed on botanical names, so a
vaidya who types गुडूची, Amrutha, Giloy or Guduchi must land on the same node
as "Tinospora cordifolia" *before* any legal reasoning runs.

Resolution order, strictly:
  1. exact match on any alias (case- and diacritic-folded)
  2. transliteration-normalised match
  3. fuzzy match -- PROPOSE, never auto-accept
  4. unresolved -- escalate to the user with a candidate list

Steps 3 and 4 never silently pick a winner. An ambiguous resolution is a
WARNING in the report, because botanical synonymy is genuinely contested for
several Ayurvedic drugs and surfacing that is more correct than guessing.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process

ROOT = Path(__file__).resolve().parent.parent
TAXA = ROOT / "data" / "taxa.jsonl"

FUZZY_ACCEPT = 88          # propose-only threshold, per the build spec

# Devanagari -> plain-roman fallback, so a Devanagari string can still be
# compared against ad-hoc romanisations typed by a different user.
_DEVA = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ii", "उ": "u", "ऊ": "uu", "ऋ": "ri",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "अं": "am", "क": "k", "ख": "kh",
    "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh",
    "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t",
    "थ": "th", "द": "d", "ध": "dh", "न": "n", "प": "p", "फ": "ph", "ब": "b",
    "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh",
    "ष": "sh", "स": "s", "ह": "h", "ळ": "l", "क्ष": "ksh", "ज्ञ": "gy",
    "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri", "े": "e",
    "ै": "ai", "ो": "o", "ौ": "au", "ं": "m", "ः": "h", "्": "", "़": "",
    "ॉ": "o", "ँ": "n",
}

# Ad-hoc romanisation variants collapse onto one another. ISO 15919 /
# Harvard-Kyoto / newspaper spellings all fold to the same key.
_ROMAN_FOLD = [
    (r"aa+", "a"), (r"ii+", "i"), (r"uu+", "u"), (r"ee+", "e"), (r"oo+", "o"),
    (r"ri", "r"), (r"ry", "r"), (r"sh", "s"), (r"ss", "s"), (r"chh", "ch"),
    (r"th", "t"), (r"dh", "d"), (r"ph", "f"), (r"bh", "b"), (r"gh", "g"),
    (r"kh", "k"), (r"jh", "j"), (r"v", "w"), (r"y$", "i"), (r"h", ""),
    (r"(.)\1+", r"\1"),
]


def strip_diacritics(s: str) -> str:
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def deva_to_roman(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        if s[i : i + 2] in _DEVA:
            out.append(_DEVA[s[i : i + 2]])
            i += 2
        elif s[i] in _DEVA:
            out.append(_DEVA[s[i]])
            i += 1
        else:
            out.append(s[i])
            i += 1
        # An unmarked Devanagari consonant carries an inherent 'a'.
        if out and i - 1 < len(s) and "क" <= s[i - 1] <= "ह":
            nxt = s[i] if i < len(s) else ""
            if not ("ा" <= nxt <= "्"):
                out.append("a")
    return "".join(out)


def fold(s: str) -> str:
    """Aggressive normalisation key. Only ever used for *matching*, never for
    display -- the user's original spelling is preserved in raw_name."""
    s = s.strip().lower()
    if any("ऀ" <= c <= "ॿ" for c in s):
        s = deva_to_roman(s)
    s = strip_diacritics(s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    for pat, rep in _ROMAN_FOLD:
        s = re.sub(pat, rep, s)
    return s


@dataclass
class Taxon:
    taxon: str
    record: dict
    aliases: list[str] = field(default_factory=list)

    @property
    def folded(self) -> set[str]:
        return {fold(a) for a in self.aliases if a.strip()}


@dataclass
class Resolution:
    raw_name: str
    taxon: str | None
    path: str                  # EXACT | TRANSLIT | FUZZY_PROPOSED | UNRESOLVED
    confidence: float
    candidates: list[str] = field(default_factory=list)
    matched_alias: str | None = None
    record: dict | None = None
    ambiguous_with: list[str] = field(default_factory=list)

    @property
    def is_accepted(self) -> bool:
        """Only exact and transliteration matches are auto-accepted. A fuzzy
        hit is a proposal that the user must confirm."""
        return self.path in ("EXACT", "TRANSLIT")


class Resolver:
    def __init__(self, path: Path = TAXA):
        self.taxa: list[Taxon] = []
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                aliases = [r["taxon"], *r.get("botanical_synonyms", []),
                           *r.get("sanskrit", []), *r.get("iast", []),
                           *r.get("translit", []), *r.get("trade_names", [])]
                for names in r.get("vernacular", {}).values():
                    aliases.extend(names)
                self.taxa.append(Taxon(r["taxon"], r, aliases))

        # folded alias -> list of taxa. A list, not a single taxon: shared
        # vernacular names (Brahmi -> Bacopa / Centella) are real and must stay
        # visible as an ambiguity rather than collapsing to a lucky winner.
        self.index: dict[str, list[Taxon]] = {}
        self.display: dict[str, str] = {}
        for t in self.taxa:
            for a in t.aliases:
                k = fold(a)
                if not k:
                    continue
                self.index.setdefault(k, [])
                if t not in self.index[k]:
                    self.index[k].append(t)
                self.display.setdefault(k, a)
        self._keys = list(self.index)

    def resolve(self, raw: str) -> Resolution:
        key = fold(raw)

        # 1 + 2. Exact / transliteration-normalised match. Folding already
        # covers both, so we distinguish them by whether the raw string was
        # itself a literal alias.
        if key in self.index:
            hits = self.index[key]
            literal = any(
                raw.strip().lower() == a.strip().lower()
                for t in hits for a in t.aliases
            )
            path = "EXACT" if literal else "TRANSLIT"
            if len(hits) > 1:
                # Genuine cross-taxon homonym. Do not pick.
                return Resolution(
                    raw_name=raw, taxon=None, path="AMBIGUOUS", confidence=0.5,
                    candidates=[t.taxon for t in hits],
                    matched_alias=self.display.get(key),
                    ambiguous_with=[t.taxon for t in hits],
                )
            t = hits[0]
            return Resolution(raw, t.taxon, path, 1.0 if path == "EXACT" else 0.95,
                              [t.taxon], self.display.get(key), t.record)

        # 3. Fuzzy -- propose only.
        best = process.extract(key, self._keys, scorer=fuzz.WRatio, limit=4)
        cands, top = [], 0.0
        for k, score, _ in best:
            if score >= FUZZY_ACCEPT:
                for t in self.index[k]:
                    if t.taxon not in cands:
                        cands.append(t.taxon)
                top = max(top, score)
        if cands:
            return Resolution(raw, None, "FUZZY_PROPOSED", top / 100.0, cands,
                              None, None)

        # 4. Unresolved -- escalate with nearest neighbours for the user to pick.
        near = [self.index[k][0].taxon for k, s, _ in best[:3] if s > 55]
        return Resolution(raw, None, "UNRESOLVED", 0.0, near)


@lru_cache(maxsize=1)
def load_resolver() -> Resolver:
    return Resolver()
