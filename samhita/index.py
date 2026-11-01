"""SAMHITA index: exact provision lookup + hybrid lexical retrieval.

Two access paths, and the distinction matters:

  * cite() -- exact, deterministic lookup of a declared provision. This is the
    only path a SUTRA rule may use. A rule cannot go fishing in the index for
    something that supports it; it declares its authority up front and we fetch
    that exact text.
  * search() -- BM25 retrieval with mandatory metadata pre-filters. Used for
    prior-art surfacing and the graph layer, never to justify a legal outcome.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
PROVISIONS = ROOT / "corpus" / "provisions.jsonl"

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "of", "and", "or", "to", "in", "a", "any", "for", "be", "shall",
    "is", "as", "by", "that", "this", "which", "with", "on", "not", "such",
    "under", "may", "an", "it", "from", "at", "has", "have", "are", "was",
}


def tokenise(s: str) -> list[str]:
    return [t for t in _TOKEN.findall(s.lower()) if t not in _STOP and len(t) > 1]


class CorpusError(RuntimeError):
    pass


class Corpus:
    """In-memory BM25 over the ingested provisions. No network, no API keys --
    the whole compiler runs offline, which is also the on-prem story."""

    K1 = 1.4
    B = 0.75

    def __init__(self, path: Path = PROVISIONS):
        if not path.exists():
            raise CorpusError(
                f"{path} not found. Run:  python samhita/ingest.py"
            )
        self.records: list[dict] = []
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    self.records.append(json.loads(line))
        self.by_id = {r["corpus_id"]: r for r in self.records}
        self._alias_subchunks()
        self._build()

    def _alias_subchunks(self) -> None:
        """Let the natural citation id reach a provision that had to be split.

        subchunk() splits an oversized record into "...::R16#part1",
        "...#part2" and so on, and nothing carries the plain "...::R16" any
        more. Every curated file -- the concept lexicon, the rules, the
        formulation classes, the graph links -- is written by a domain expert
        who cites Rule 16, not Rule 16 part 1 of 2, so all of them failed the
        load-time gate with "not in corpus" for no reason a reader could act
        on. The effect was an invisible rule that a provision may be cited only
        if it happens to be short.

        The base id resolves to the FIRST part, which is where a provision's
        operative opening is. The parts remain individually addressable, and
        nothing is aliased over a record that really exists under that id.
        """
        for r in self.records:
            cid = r["corpus_id"]
            base, sep, _part = cid.partition("#part")
            if sep and base not in self.by_id:
                self.by_id[base] = r

    def _build(self) -> None:
        self.docs: list[list[str]] = []
        df: Counter = Counter()
        for r in self.records:
            toks = tokenise(r["heading"] + " " + r["text"])
            self.docs.append(toks)
            df.update(set(toks))
        n = len(self.docs)
        self.avgdl = sum(len(d) for d in self.docs) / max(n, 1)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.tf: list[Counter] = [Counter(d) for d in self.docs]
        self.postings: dict[str, list[int]] = defaultdict(list)
        for i, d in enumerate(self.docs):
            for t in set(d):
                self.postings[t].append(i)

    # ------------------------------------------------------------ lookup --
    def get(self, corpus_id: str) -> dict:
        rec = self.by_id.get(corpus_id)
        if rec is None:
            raise CorpusError(
                f"corpus_id {corpus_id!r} is not in the ingested corpus. "
                "A rule may not cite a provision that was never extracted."
            )
        return rec

    def has(self, corpus_id: str) -> bool:
        return corpus_id in self.by_id

    def clause_text(self, corpus_id: str, clause: str | None) -> str:
        """Return the pin-cited clause if we indexed one, else the whole
        section. We never return a clause detached from a retrievable parent."""
        rec = self.get(corpus_id)
        if clause and clause in rec.get("clauses", {}):
            return rec["clauses"][clause]
        return rec["text"]

    # --------------------------------------------------------- retrieval --
    def search(
        self,
        query: str,
        *,
        k: int = 8,
        acts: Iterable[str] | None = None,
        max_rank: int = 7,
        citable_only: bool = False,
        as_of: date | None = None,
    ) -> list[tuple[dict, float]]:
        """BM25 with mandatory metadata pre-filters. Retrieving a repealed or
        not-yet-in-force provision is a correctness failure, so as_of filtering
        happens before scoring, not after."""
        acts = set(acts) if acts else None
        q = tokenise(query)
        scores: dict[int, float] = defaultdict(float)
        for t in q:
            if t not in self.postings:
                continue
            idf = self.idf[t]
            for i in self.postings[t]:
                f = self.tf[i][t]
                dl = len(self.docs[i])
                denom = f + self.K1 * (1 - self.B + self.B * dl / self.avgdl)
                scores[i] += idf * f * (self.K1 + 1) / denom
        out = []
        for i, s in scores.items():
            r = self.records[i]
            if acts and r["act_id"] not in acts:
                continue
            if r["authority_rank"] > max_rank:
                continue
            if citable_only and not r.get("citable", True):
                continue
            if as_of and not in_force(r, as_of):
                continue
            out.append((r, s))
        out.sort(key=lambda t: (-t[1], t[0]["corpus_id"]))
        return out[:k]


def in_force(rec: dict, on: date) -> bool:
    ef, et = rec.get("effective_from"), rec.get("effective_to")
    if ef and date.fromisoformat(ef) > on:
        return False
    if et and date.fromisoformat(et) <= on:
        return False
    return True


@lru_cache(maxsize=1)
def load_corpus() -> Corpus:
    return Corpus()
