"""The concept layer: lay phrasing -> statutory vocabulary + governing provisions.

Retrieval over statutes fails on real questions for a reason that is not fixable
by tuning an embedding: the question and the provision are written in different
registers. "Can I patent my family formulation?" and "What are not inventions"
share no content words at all. Measured on our own question set, pure hybrid
retrieval put the right provision in the top 5 for 2 questions out of 9.

So the mapping is curated data (data/legal_concepts.yaml), reviewable by a
domain expert who does not read Python, and verified against the corpus at load
time exactly like a compliance rule: a concept pointing at a provision that does not
exist fails loudly instead of silently degrading retrieval.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from sources.index import Corpus, load_corpus

ROOT = Path(__file__).resolve().parent.parent
CONCEPTS = ROOT / "data" / "legal_concepts.yaml"

_WS = re.compile(r"\s+")
# Punctuation stripper. The Indic ranges are NOT decoration: an Indic vowel
# sign or virama is a combining mark (Unicode category Mn/Mc), and Python's \w
# is alphanumeric-only, so a bare [^\w\s] class deletes every one of them.
# "காப்புரிமை" (patent) came out of that as "க ப ப ர ம" -- five bare
# consonants, no word left to match -- which is why every Tamil, Telugu,
# Kannada, Malayalam, Bengali and Gujarati phrase in this lexicon silently
# never matched, while the Devanagari ones worked because U+0900-U+097F was
# the one block that had been whitelisted here.
#
# The range covers Devanagari through Sinhala (U+0900-U+0DFF) plus Arabic
# (U+0600-U+06FF, for Urdu), which is every script core.language.detect
# recognises.
_PUNCT = re.compile(r"[^\w\s؀-ۿऀ-෿]+")


def norm(s: str) -> str:
    return _WS.sub(" ", _PUNCT.sub(" ", s.lower())).strip()


PIN = re.compile(r"^(?P<id>[^()]+)\((?P<clause>[^()]+)\)$")


def split_pin(spec: str) -> tuple[str, str | None]:
    """'IN.PATENTS.1970::S3(p)' -> ('IN.PATENTS.1970::S3', 'p')"""
    m = PIN.match(spec.strip())
    return (m.group("id"), m.group("clause")) if m else (spec.strip(), None)


@dataclass
class Concept:
    id: str
    label: str
    lay: list[str]
    statutory: list[str]
    provisions: list[str]
    pins: dict[str, str] = field(default_factory=dict)
    rules: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


@dataclass
class ConceptMatch:
    concept: Concept
    score: float
    matched_on: list[str]


class ConceptIndex:
    def __init__(self, path: Path = CONCEPTS, corpus: Corpus | None = None):
        corpus = corpus or load_corpus()
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        self.concepts: list[Concept] = []
        for c in raw:
            ids, pins = [], {}
            for spec in c.get("provisions", []):
                pid, clause = split_pin(spec)
                ids.append(pid)
                if clause:
                    pins[pid] = clause
            concept = Concept(
                id=c["id"], label=c["label"],
                lay=[norm(x) for x in c.get("lay", [])],
                statutory=c.get("statutory", []),
                provisions=ids, pins=pins,
                rules=c.get("rules", []) or [],
            )
            for pid in concept.provisions:
                if not corpus.has(pid):
                    concept.problems.append(f"{pid} not in corpus")
                elif pid in concept.pins:
                    clause = concept.pins[pid]
                    if clause not in corpus.get(pid).get("clauses", {}):
                        concept.problems.append(
                            f"{pid} has no clause ({clause})")
            self.concepts.append(concept)

    def match(self, query: str, *, limit: int = 3) -> list[ConceptMatch]:
        """Ordered-subsequence phrase matching within a proximity window.

        Literal containment is too brittle for real questions: the lay phrase
        "file abroad" has to match "file a patent abroad", and "mix two herbs"
        has to match "mix two known herbs". So every token of the phrase must
        appear in the query IN ORDER, within a window proportional to the phrase
        length -- which keeps "file" ... forty words ... "abroad" from matching.

        Still deliberately not fuzzy: a concept match applies a large boost to
        specific provisions, so a loose match would be worse than none. A
        question this misses falls through to ordinary hybrid retrieval.
        """
        qt = norm(query).split()
        pos: dict[str, list[int]] = {}
        for i, t in enumerate(qt):
            pos.setdefault(t, []).append(i)

        out: list[ConceptMatch] = []
        for c in self.concepts:
            if not c.ok:
                continue
            hits = [p for p in c.lay if p and self._subseq(p.split(), pos)]
            if not hits:
                continue
            score = sum(len(h.split()) for h in hits) / 3.0
            out.append(ConceptMatch(c, min(score, 3.0),
                                    sorted(hits, key=len, reverse=True)))
        out.sort(key=lambda m: -m.score)
        return out[:limit]

    @staticmethod
    def _subseq(phrase: list[str], pos: dict[str, list[int]]) -> bool:
        window = 3 + 2 * len(phrase)      # allowed slack between first and last
        start = -1
        cursor = -1
        for tok in phrase:
            nxt = next((i for i in pos.get(tok, []) if i > cursor), None)
            if nxt is None:
                return False
            if start < 0:
                start = nxt
            cursor = nxt
        return cursor - start < window

    def expansion(self, matches: list[ConceptMatch]) -> str:
        return " ".join(t for m in matches for t in m.concept.statutory)

    def pin_for(self, matches: list[ConceptMatch], corpus_id: str) -> str | None:
        """The clause a matched concept pin-cites for this provision, if any."""
        base = corpus_id.split("#")[0]
        for m in matches:
            if base in m.concept.pins:
                return m.concept.pins[base]
        return None

    def boosted_ids(self, matches: list[ConceptMatch]) -> dict[str, float]:
        out: dict[str, float] = {}
        for m in matches:
            for pid in m.concept.provisions:
                out[pid] = max(out.get(pid, 0.0), 1.0 + m.score)
        return out

    @property
    def problems(self) -> list[str]:
        return [f"{c.id}: {p}" for c in self.concepts for p in c.problems]


@lru_cache(maxsize=1)
def load_concepts() -> ConceptIndex:
    return ConceptIndex()
