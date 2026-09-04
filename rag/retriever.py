"""Hybrid retrieval over the SAMHITA corpus.

Three retrievers fused, then reranked:

  1. BM25            -- lexical. Strong on exact statutory phrasing.
  2. LSA dense       -- latent-semantic vectors built from the corpus itself by
                        truncated SVD over TF-IDF. Catches the paraphrase case
                        ("can I stop someone copying my brand name" -> the trade
                        marks provisions) that BM25 misses entirely.
  3. Taxon expansion -- the query is run through RESOLVER first, so a question
                        asked about गिलोय also searches for Tinospora cordifolia.
                        The statutes are keyed on binomials; without this step a
                        vernacular question retrieves nothing.

Fused with reciprocal rank fusion, then reranked on query-term coverage,
authority rank and structural signals.

On the dense retriever, precisely: LSA is a real semantic model learned from
this corpus, not a bag of words -- but it is not a transformer embedding. The
upgrade is BGE-M3 or multilingual-e5, which is a drop-in replacement at
`DenseIndex.encode_query` / `.doc_vectors`. LSA is what ships because it trains
in two seconds, needs no download, and keeps the whole stack air-gapped.

Metadata pre-filters (jurisdiction, instrument type, as_of, authority rank) are
applied BEFORE scoring, never after. Retrieving a repealed provision and then
filtering it out of the display is still a correctness failure -- it has already
displaced a good result from the top-k.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import numpy as np

from core.resolver import load_resolver
from rag.concepts import load_concepts
from samhita.index import Corpus, in_force, load_corpus, tokenise

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "corpus" / "lsa_index.npz"

DIMS = 192          # latent dimensions
MAX_VOCAB = 14000   # cap by document frequency; the tail is mostly OCR noise
RRF_K = 60          # standard reciprocal-rank-fusion damping


# --------------------------------------------------------------- LSA index --
class DenseIndex:
    """Truncated SVD over TF-IDF, computed with a randomized range finder.

    Randomized SVD rather than a full decomposition: the corpus is ~1.5k docs by
    ~14k terms, and we only want 192 components, so the full factorisation would
    be almost entirely wasted work.
    """

    def __init__(self, corpus: Corpus):
        self.corpus = corpus
        self._build()

    def _build(self) -> None:
        docs = [tokenise(r["heading"] + " " + r["text"]) for r in self.corpus.records]
        df: dict[str, int] = defaultdict(int)
        for d in docs:
            for t in set(d):
                df[t] += 1
        # Drop hapax terms and terms in almost every document: neither separates
        # one provision from another.
        n = len(docs)
        terms = [t for t, c in df.items() if 1 < c < n * 0.6]
        terms.sort(key=lambda t: -df[t])
        self.vocab = {t: i for i, t in enumerate(terms[:MAX_VOCAB])}
        self.idf = np.zeros(len(self.vocab), dtype=np.float32)
        for t, i in self.vocab.items():
            self.idf[i] = math.log(1 + n / (1 + df[t]))

        A = np.zeros((n, len(self.vocab)), dtype=np.float32)
        for r, d in enumerate(docs):
            counts: dict[int, int] = defaultdict(int)
            for t in d:
                j = self.vocab.get(t)
                if j is not None:
                    counts[j] += 1
            if not counts:
                continue
            idx = np.fromiter(counts.keys(), dtype=np.int64, count=len(counts))
            val = np.fromiter(counts.values(), dtype=np.float32, count=len(counts))
            A[r, idx] = (1.0 + np.log(val)) * self.idf[idx]

        # Randomized range finder -> SVD on the small projected matrix.
        rng = np.random.default_rng(0)          # fixed seed: reproducible build
        k = min(DIMS, min(A.shape) - 1)
        omega = rng.standard_normal((A.shape[1], k + 12)).astype(np.float32)
        Y = A @ omega
        Q, _ = np.linalg.qr(Y)
        B = Q.T @ A
        Ub, S, Vt = np.linalg.svd(B, full_matrices=False)
        self.components = Vt[:k].astype(np.float32)          # k x vocab
        self.singular = S[:k].astype(np.float32)

        V = (Q @ Ub)[:, :k] * S[:k]
        self.doc_vectors = self._unit(V.astype(np.float32))

    @staticmethod
    def _unit(M: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(M, axis=-1, keepdims=True)
        return M / np.maximum(norms, 1e-8)

    def encode_query(self, text: str) -> np.ndarray:
        vec = np.zeros(len(self.vocab), dtype=np.float32)
        counts: dict[int, int] = defaultdict(int)
        for t in tokenise(text):
            j = self.vocab.get(t)
            if j is not None:
                counts[j] += 1
        if counts:
            idx = np.fromiter(counts.keys(), dtype=np.int64, count=len(counts))
            val = np.fromiter(counts.values(), dtype=np.float32, count=len(counts))
            vec[idx] = (1.0 + np.log(val)) * self.idf[idx]
        q = self.components @ vec
        return self._unit(q)

    def search(self, text: str, k: int = 40) -> list[tuple[int, float]]:
        q = self.encode_query(text)
        if not np.any(q):
            return []
        sims = self.doc_vectors @ q
        top = np.argpartition(-sims, min(k, len(sims) - 1))[:k]
        return sorted(((int(i), float(sims[i])) for i in top),
                      key=lambda t: -t[1])


# ------------------------------------------------------------------ result --
@dataclass
class Hit:
    record: dict
    score: float
    bm25_rank: int | None = None
    dense_rank: int | None = None
    why: list[str] = field(default_factory=list)

    @property
    def corpus_id(self) -> str:
        return self.record["corpus_id"]


@dataclass
class RetrievalResult:
    query: str
    expanded_query: str
    hits: list[Hit]
    translated_query: str = ""
    taxa_expansions: list[tuple[str, str]] = field(default_factory=list)
    filters: dict = field(default_factory=dict)
    concepts: list = field(default_factory=list)

    @property
    def rules(self) -> list[str]:
        """SUTRA rules that decide the matched concepts. This is what lets chat
        offer 'compile your formulation' instead of only quoting law at you."""
        out: list[str] = []
        for m in self.concepts:
            for r in m.concept.rules:
                if r not in out:
                    out.append(r)
        return out

    out_of_corpus: str = ""
    # "IN" or "INTL" -- which layer this answer was resolved against. SIH26045
    # requires the national and international answer-sets to stay visibly
    # separate, so a result is always drawn from exactly one of them.
    layer: str = "IN"
    background_only: bool = False

    @property
    def is_weak(self) -> bool:
        """Retrieval too thin to answer on. The chat layer abstains rather than
        assembling something plausible out of the best of a bad set.

        The floor is set by what the top hit IS, not by one flag, because the
        score a good hit earns depends on the kind of document it came from.

        A statutory section is a tight, self-contained chunk and a real match
        scores well above 0.10. Guidance (rank 5) is ingested as whole pages of
        continuous prose -- the FDA botanical guidance and the WHO Ayurveda
        benchmarks both -- so its best hit is diffuse by construction and lands
        around 0.09. Holding it to the statutory floor made the assistant
        abstain on "what does the WHO benchmark say about infection prevention"
        while holding the page that answers it, which is not caution, just a
        miscalibrated threshold. Reference material (rank 6+) is pushed further
        down still by the reranker, and gets the lowest floor of the three.
        """
        if self.out_of_corpus or not self.hits:
            return True
        rank = self.hits[0].record["authority_rank"]
        if self.background_only or rank >= 6:
            floor = 0.012
        elif rank == 5:
            floor = 0.05
        else:
            floor = 0.10
        return self.hits[0].score < floor


# ------------------------------------------------------- query understanding -
ACT_HINTS = {
    "IN.PATENTS.1970": ["patent", "patents", "invention", "inventive", "claim",
                        "specification", "controller", "patentab", "prior art"],
    "IN.BDA.2002": ["biodiversity", "biological resource", "nba", "benefit shar",
                    "access", "bioresource", "national biodiversity"],
    "IN.DMR.1954": ["advertis", "magic remed", "claim on the label", "marketing"],
    "IN.TM.1999": ["trade mark", "trademark", "brand", "logo", "deceptive"],
    "IN.GI.1999": ["geographical indication", " gi ", "region of origin"],
    "IN.PPVFR.2001": ["plant variety", "farmers right", "cultivar", "breeder"],
    "IN.DCA.1940": ["licence", "license", "manufactur", "drugs and cosmetics",
                    "gmp", "asu"],
    "IN.PATENT_RULES.2003": ["form 1", "form 27", "fee", "rule "],
}

TAXON_HINT = re.compile(r"[A-Za-zऀ-ॿ஀-௿ఀ-౿ಀ-೿"
                        r"ഀ-ൿঀ-৿઀-૿]{3,}")

# The corpus is Indian primary sources only. A question about foreign law that
# no Indian concept covers has no answerable basis here -- and retrieval will
# still cheerfully return some Indian section about fees or oppositions, which
# is exactly the confident wrong answer this product exists not to give.
# "What is X?" / "explain X" / "tell me about X" -- a request for description,
# not for a rule. The corpus carries the AYUSH reference material and the WHO
# terminologies, which answer these perfectly well provided the answer says it
# is background.
#
# The Indic markers need explicit script boundaries. Tamil is agglutinative:
# "என்னால்" means "by me" and merely CONTAINS "என்ன" ("what"), so an unanchored
# alternation classified "கிலோய்க்கு என்னால் காப்புரிமை பெற முடியுமா?" ("can I
# get a patent for Giloy?") as a request for a description -- which widened
# retrieval to the AYUSH reference material and answered a patent question out
# of a book about Panchakarma. \b is no help here: it is defined on word
# characters and every Tamil letter is one, so the boundary has to be stated as
# "no other letter of the same script on either side".
DEFINITIONAL = re.compile(
    r"^\s*(what|which|who)\s+(is|are|was|were)\b"
    r"|^\s*(explain|describe|define|tell me about|introduction to)\b"
    r"|what does\s+\w+\s+mean"
    r"|क्या\s*(है|हैं)"
    r"|(?<![஀-௿])என்ன(?![஀-௿])"
    r"|(?<![ఀ-౿])ఏమిటి(?![ఀ-౿])"
    r"|(?<![ಀ-೿])ಏನು(?![ಀ-೿])"
    r"|(?<![ഀ-ൿ])എന്താണ്(?![ഀ-ൿ])",
    re.I,
)

# Instruments in the international layer, named explicitly. Used only when no
# concept matched, to route a question that plainly concerns one of them.
INTL_MARKER = re.compile(
    r"\b(TRIPS|WTO|Nagoya|CBD|WIPO|GRATK|PCT|FDA|WHO|"
    r"World Health Organi[sz]ation|"
    r"Convention on Biological Diversity)\b", re.I
)

FOREIGN_JURISDICTION = re.compile(
    r"\b(US|USA|U\.S\.|American?|USPTO|EPO|EPC|Europe|European|"
    r"Japan|Japanese|JPO|China|Chinese|CNIPA|WIPO|Canada|Australia)\b"
)


def infer_acts(query: str) -> list[str]:
    q = f" {query.lower()} "
    hits = [act for act, kws in ACT_HINTS.items() if any(k in q for k in kws)]
    return hits


def expand_taxa(query: str) -> tuple[str, list[tuple[str, str]]]:
    """Resolve any ingredient name in the question to its binomial and append it.

    This is the step that makes a vernacular question answerable at all: the
    statutes never say 'giloy', they say nothing about it by any name, and the
    curated taxon record is what carries the schedule flags.
    """
    resolver = load_resolver()
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for tok in TAXON_HINT.findall(query):
        if len(tok) < 4 or tok.lower() in seen:
            continue
        seen.add(tok.lower())
        res = resolver.resolve(tok)
        if res.taxon and res.is_accepted:
            found.append((tok, res.taxon))
        elif res.path == "AMBIGUOUS":
            for cand in res.candidates:
                found.append((tok, cand))
    extra = " ".join(t for _, t in found)
    return (f"{query} {extra}".strip() if extra else query), found


# -------------------------------------------------------------- retriever ---
class HybridRetriever:
    def __init__(self, corpus: Corpus | None = None):
        self.corpus = corpus or load_corpus()
        self.dense = DenseIndex(self.corpus)
        self._index_of = {r["corpus_id"]: i
                          for i, r in enumerate(self.corpus.records)}

    @staticmethod
    def _layer_for(concepts: list, text: str) -> str:
        """Decide whether a question belongs to the Indian or the international
        layer.

        A matched concept settles it, because a concept names the instruments
        that govern it: NAGOYA_ABS points only at Protocol articles, so
        "what does the Nagoya Protocol require" is international even though
        it also brushes the Indian benefit-sharing concept. Concepts are
        score-ordered, so the strongest match decides and the runner-up does
        not drag the answer across the boundary.
        """
        if concepts:
            from samhita.index import load_corpus

            corpus = load_corpus()
            for m in concepts:
                js = {corpus.get(pid)["jurisdiction"]
                      for pid in m.concept.provisions if corpus.has(pid)}
                if js:
                    return "IN" if "IN" in js else "INTL"
        return "INTL" if INTL_MARKER.search(text) else "IN"

    def search(
        self,
        query: str,
        *,
        k: int = 6,
        as_of: date | None = None,
        citable_only: bool = False,
        max_rank: int = 7,
        acts: Iterable[str] | None = None,
        translate: bool = True,
    ) -> RetrievalResult:
        # Concept layer first: it rewrites the question into statutory
        # vocabulary and names the provisions that govern it. Without this the
        # lay-vs-statutory register gap sinks most real questions. It carries
        # Devanagari entries, so an Indic question it matches needs no
        # translation at all.
        concepts = load_concepts().match(query)

        # Indic script with no concept hit: translate for retrieval only. The
        # corpus is English, so without this the search has nothing to match on.
        translated = ""
        search_text = query
        if translate and not concepts:
            from rag.translate import for_retrieval

            search_text, _lang, translated = for_retrieval(query)

        expanded, taxa = expand_taxa(search_text)
        statutory = load_concepts().expansion(concepts)
        boosts = load_concepts().boosted_ids(concepts)
        if statutory:
            expanded = f"{expanded} {statutory}"
        acts = list(acts) if acts else infer_acts(query + " " + statutory)

        # A definitional question ("what is Ayurveda?", "what is a rasayana?")
        # is answerable from the AYUSH reference material even though that
        # material is not law. Refusing it makes the assistant look broken for
        # the easiest question a user will ask, so we widen to background
        # material and label the answer as descriptive rather than legal.
        # Jurisdiction guard, evaluated FIRST. The corpus is Indian primary
        # sources only, so a question about foreign law that no Indian concept
        # covers has no answerable basis here. Retrieval would still return
        # *something* -- some Indian section about oppositions or fees -- and
        # that is precisely the confident wrong answer this product exists not
        # to give. A question that merely mentions another country while asking
        # about Indian law ("file in America before India") matches a concept
        # and so is not caught by this.
        #
        # This runs before the definitional widening on purpose: "what is the
        # EPO opposition period" is phrased as a definitional question, and
        # widening it to background material would let it retrieve an Indian
        # opposition section and answer confidently about the wrong regime.
        foreign = FOREIGN_JURISDICTION.search(search_text)
        out_of_corpus = ""
        if foreign and not concepts:
            out_of_corpus = (
                f"the question is about {foreign.group(0)} law. The corpus "
                f"covers Indian primary sources plus TRIPS, the CBD and Nagoya "
                f"Protocol, the WIPO GRATK Treaty, the PCT, US FDA "
                f"botanical-drug guidance and the WHO Ayurveda benchmarks -- "
                f"none of which govern it"
            )

        # Which layer answers this question. A concept decides it, because a
        # concept names the instruments it is governed by; failing that, an
        # explicit international marker does.
        layer = self._layer_for(concepts, search_text)

        # Routing is decided on what the USER wrote, not on the translation.
        #
        # The translation is documented as a search key: it may influence
        # ranking, never routing. It was doing both, and the failure was not
        # hypothetical -- qwen2.5:1.5b rendered "can I get a patent for Giloy?"
        # (Tamil) as "What is the medicinal use of Giloy (Licorice)?". That
        # single bad translation turned a patent question into a definitional
        # one, widened retrieval to non-law, and invented a second plant for
        # the taxon resolver to expand. A mistranslation should cost us
        # ranking quality; it must not be able to change what kind of question
        # the system thinks it was asked.
        #
        # The foreign-jurisdiction guard deliberately keeps reading the
        # translated text as well. The asymmetry is the point: a false
        # positive there causes an abstention, a false negative in the
        # definitional test causes a confident answer out of the wrong corpus.
        definitional = (bool(DEFINITIONAL.search(query)) and not concepts
                        and not out_of_corpus)
        if definitional:
            citable_only = False
            max_rank = 7

        # Pre-filter, then score. Never the other way round.
        allowed = {
            i for i, r in enumerate(self.corpus.records)
            if r["authority_rank"] <= max_rank
            and (not citable_only or r.get("citable", True))
            and (as_of is None or in_force(r, as_of))
            # The layer separation is a pre-filter, not a post-hoc sort. An
            # answer that quotes Section 21 of the Biological Diversity Act
            # and Article 5 of the Nagoya Protocol in one breath is the exact
            # conflation this assistant is required not to produce.
            #
            # It binds AUTHORITY, though, not description. The rule exists so
            # that two legal regimes are never merged into one answer; a
            # non-citable reference page has no regime to merge. Holding
            # background material to it would mean the WHO's standard
            # terminology for a Sanskrit term could not answer "what is
            # vamana?" unless the user happened to say "WHO" in the question,
            # which is a worse outcome and guards nothing: such material is
            # labelled background, never cited as a rule, and carries its own
            # jurisdiction in the citation the user sees.
            and (r["authority_rank"] >= 6 and not r.get("citable", True)
                 or (r["jurisdiction"] == "IN") == (layer == "IN"))
        }

        bm = [(self._index_of[r["corpus_id"]], s)
              for r, s in self.corpus.search(expanded, k=60, max_rank=max_rank,
                                             citable_only=citable_only,
                                             as_of=as_of)
              if self._index_of[r["corpus_id"]] in allowed]
        dn = [(i, s) for i, s in self.dense.search(expanded, k=60)
              if i in allowed]

        # Reciprocal rank fusion: rank-based, so the two retrievers' wildly
        # different score scales never need calibrating against each other.
        fused: dict[int, float] = defaultdict(float)
        bm_rank = {i: r for r, (i, _) in enumerate(bm)}
        dn_rank = {i: r for r, (i, _) in enumerate(dn)}
        for i, r in bm_rank.items():
            fused[i] += 1.0 / (RRF_K + r + 1)
        for i, r in dn_rank.items():
            fused[i] += 1.0 / (RRF_K + r + 1)

        hits = [Hit(record=self.corpus.records[i], score=s,
                    bm25_rank=bm_rank.get(i), dense_rank=dn_rank.get(i))
                for i, s in fused.items()]
        hits = self._rerank(hits, expanded, acts, boosts, definitional)
        return RetrievalResult(
            query=query, expanded_query=expanded, hits=hits[:k],
            taxa_expansions=taxa, concepts=concepts,
            out_of_corpus=out_of_corpus,
            layer=layer,
            background_only=definitional,
            translated_query=translated,
            filters={"acts": acts, "as_of": str(as_of) if as_of else None,
                     "max_rank": max_rank, "citable_only": citable_only},
        )

    def _rerank(self, hits: list[Hit], query: str, acts: list[str],
                boosts: dict[str, float] | None = None,
                definitional: bool = False) -> list[Hit]:
        """Signals a pure vector score cannot see: which Act the question is
        about, whether the provision is binding law or commentary, and whether
        the query's distinctive terms actually appear in the text."""
        qt = set(tokenise(query))
        out = []
        for h in hits:
            r = h.record
            base = h.score
            why = []

            if h.bm25_rank is not None and h.dense_rank is not None:
                base *= 1.25
                why.append("found by both lexical and semantic retrieval")
            elif h.dense_rank is not None and h.bm25_rank is None:
                why.append("semantic match (wording differs from the statute)")
            elif h.bm25_rank is not None:
                why.append("lexical match on statutory phrasing")

            # A concept named this provision as governing the question. This is
            # curated, corpus-verified knowledge, so it outweighs every
            # statistical signal here.
            bid = r["corpus_id"].split("#")[0]
            if boosts and bid in boosts:
                base *= 3.0 + boosts[bid]
                why.append("named by the matched legal concept as governing")

            if acts and r["act_id"] in acts:
                base *= 1.6
                why.append(f"question is about {r['act_id'].split('.')[1]}")

            body = (r["heading"] + " " + r["text"]).lower()
            cover = sum(1 for t in qt if t in body) / max(len(qt), 1)
            base *= 0.7 + 0.6 * cover

            # The heading is the drafter's own summary of the provision, so a
            # query term landing there is worth far more than one landing
            # anywhere in the body. This is what lifts "What are not inventions"
            # above forty sections that merely mention the word "patent".
            head = r["heading"].lower()
            head_hits = sum(1 for t in qt if t in head)
            if head_hits:
                base *= 1.0 + 0.55 * head_hits
                why.append("query terms match the section heading")

            # Binding law outranks reference material. The gap has to be wide:
            # the TKDL and Ayurveda prose pages discuss "traditional knowledge
            # patent" on nearly every page, so a gentle penalty leaves them
            # occupying the whole first page of results for exactly the queries
            # this product exists to answer.
            #
            # For a definitional question the preference inverts. "What is
            # Ayurveda?" asked against the statutory weighting retrieves
            # "What are NOT inventions" -- a lexical accident that reads as a
            # broken assistant. A request for description wants the
            # descriptive corpus.
            weights = ({6: 1.60, 5: 1.30, 7: 1.10, 1: 0.55, 2: 0.45,
                        3: 0.45, 4: 0.45} if definitional else
                       {1: 1.40, 2: 1.20, 3: 1.05, 4: 1.0,
                        5: 0.90, 6: 0.30, 7: 0.20})
            base *= weights.get(r["authority_rank"], 0.2)
            if not r.get("citable", True):
                why.append("background only — not citable as authority")

            # A stub is usually an omitted or repealed section; a swallowed
            # region is usually an unparsed schedule. Neither answers a question.
            if len(r["text"]) < 200:
                base *= 0.60
            if "#part" in r["corpus_id"]:
                base *= 0.85
                why.append("part of a long schedule")

            h.score = base
            h.why = why
            out.append(h)
        out.sort(key=lambda h: (-h.score, h.corpus_id))
        return out


@lru_cache(maxsize=1)
def load_retriever() -> HybridRetriever:
    return HybridRetriever()
