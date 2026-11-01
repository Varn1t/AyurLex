"""Answer generation, with the generator held to the same citation gate.

Two backends behind one interface:

  * ExtractiveAnswerer (default) -- selects and quotes the operative sentences
    of the retrieved provisions. No model, no network, fully deterministic. It
    cannot hallucinate because it never writes a sentence: everything it emits
    is either a verbatim span or fixed connective text. This is what runs in the
    air-gapped profile, and it is what runs when no API key is present.

  * ClaudeAnswerer -- an LLM that may only paraphrase the supplied spans. Its
    output is then passed through PRAMANA exactly like a compiler finding, so a
    sentence it invents that no span supports is dropped before the user sees
    it. The model is a phrasing layer over retrieved text, never an authority.

That second point is the whole design: adding an LLM must not add a new way to
be wrong. If the verifier drops most of what the model wrote, the answer
degrades toward the extractive one rather than toward fluent nonsense.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Protocol

from core.language import Language, detect
from core.localise import t as localised
from core.schema import Citation, CitationKind
from pramana.verify import ENTAILED, content_words, entailment_score
from rag.retriever import RetrievalResult

# Sentence boundaries. The Latin branch requires the next sentence to start
# with a capital, which is what keeps "s. 3(p)" and "Rs. 5,000" from splitting
# a sentence in half. The Indic branch cannot use that test -- these scripts
# have no case -- so it splits on the danda and on terminal punctuation
# followed by a non-Latin letter. Without it an entire Tamil answer arrives at
# the verifier as ONE sentence, and a single unsupported number then drops the
# whole answer instead of the one clause that earned it.
SENT = re.compile(
    r"(?<=[.;:?!])\s+(?=[A-Z(“])"
    r"|(?<=[।॥])\s*"
    r"|(?<=[.?!])\s+(?=[^\W\dA-Za-z])"
)

# How many extracts the generator is shown. The verification gate MUST use
# the same window: verifying against more spans than the model saw lets an
# invented cross-reference ("Plant Variety Rights Act") be legitimised by a
# weakly-ranked hit the model never had, which is exactly how a plausible
# hallucination survives a citation check.
PROMPT_HITS = 3

# The English abstention lives in core.localise with its translations, so the
# wording cannot drift between languages. Kept here as a name because callers
# and tests refer to it.
ABSTENTION = localised("en", "abstention")


@dataclass
class Answer:
    question: str
    text: str
    citations: list[Citation] = field(default_factory=list)
    groundedness: float = 0.0
    abstained: bool = False
    abstain_reason: str = ""
    concept: str = ""
    concept_label: str = ""
    suggested_rules: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    backend: str = ""
    taxa: list[tuple[str, str]] = field(default_factory=list)
    language: str = "en"
    language_name: str = "English"
    background_only: bool = False
    # Names a guard that changed how this answer was produced, so the UI can
    # say why the wording is a quotation rather than prose.
    guard: str = ""


class AnswerBackend(Protocol):
    name: str

    def write(self, question: str, res: RetrievalResult) -> str: ...


# --------------------------------------------------------------- helpers ----
def _provision_label(r: dict) -> str:
    sec = str(r["section"])
    if sec.startswith("p."):
        return f"page {sec[2:]}"
    return f"{r.get('unit', 'Section')} {sec}"


def to_citation(hit) -> Citation:
    r = hit.record
    return Citation(
        kind=CitationKind.RULES if r["instrument_type"] == "RULES"
        else CitationKind.REFERENCE if r["authority_rank"] >= 6
        else CitationKind.STATUTE,
        corpus_id=r["corpus_id"],
        instrument=r["act_title"],
        # A treaty numbers Articles and the PCT Regulations number Rules.
        # Citing "Section 27" of TRIPS would be a wrong citation, which is the
        # one thing this system may never emit. Prose material has no numbered
        # provisions at all, only pages, so it is cited as a page.
        provision=_provision_label(r),
        quote=r["text"].strip(),
        hierarchy_path=r["hierarchy_path"],
        source_pdf=r["source_pdf"],
        page=r["page_start"],
        retrieved_on=r.get("retrieved_on", ""),
        authority_rank=r["authority_rank"],
        jurisdiction=r.get("jurisdiction", "IN"),
        force_note=r.get("force_note", ""),
    )


def pin_for_hit(res: RetrievalResult, record: dict) -> str | None:
    """The clause a matched concept pin-cites for this provision, if any."""
    from rag.concepts import load_concepts

    if not res.concepts:
        return None
    return load_concepts().pin_for(res.concepts, record["corpus_id"])


def operative_sentences(text: str, query_terms: set[str], limit: int = 3
                        ) -> list[str]:
    """Pick the sentences of a provision that actually bear on the question.

    Quoting a whole 4,000-character section at someone is not an answer; it is
    a refusal dressed as thoroughness.
    """
    sents = [s.strip() for s in SENT.split(text) if len(s.strip()) > 40]
    if not sents:
        return [text[:600]]
    scored = []
    for i, s in enumerate(sents):
        w = content_words(s)
        overlap = len(w & query_terms) / max(len(query_terms), 1)
        # The opening sentence carries the section heading and the main rule.
        lead = 0.25 if i == 0 else 0.0
        scored.append((overlap + lead, i, s))
    scored.sort(key=lambda t: -t[0])
    chosen = sorted(scored[:limit], key=lambda t: t[1])
    return [s for _, _, s in chosen]


def clip_quote(text: str, limit: int = 900) -> str:
    """Cut a long quote at a sentence or word boundary, and say that you did.

    A quote sliced mid-word reads as the system having crashed, which is the
    same complaint a truncated generation produces and is fixed the same way:
    end where a reader can tell the text ended deliberately.
    """
    if len(text) <= limit:
        return text
    head = text[:limit]
    stop = max(head.rfind(". "), head.rfind("; "), head.rfind(": "))
    if stop < limit * 0.5:
        stop = head.rfind(" ")
    return head[:stop].rstrip(" ,;:") + " …"


# ------------------------------------------------------------- extractive ---
class ExtractiveAnswerer:
    """Quotation and navigation. Never paraphrase, never infer.

    This is also the fallback for every other backend, which is why it is
    localised. It used to emit English scaffolding unconditionally, so every
    path that degraded to it -- Ollama down, draft failed the gate -- answered
    a Tamil question in English no matter what the generator had been told.
    The connective text here comes from a hand-written table, so it is right
    in the user's language without a model in the loop.

    The QUOTE stays in the language of the statute, with a line above it
    saying so. Translating it would turn authority into paraphrase.
    """

    name = "extractive (offline, no model)"

    def write(self, question: str, res: RetrievalResult) -> str:
        qt = content_words(question + " " + res.expanded_query)
        lang = detect(question)
        parts: list[str] = []

        if res.background_only:
            parts.append(localised(lang.code, "background"))
        elif res.concepts:
            label = res.concepts[0].concept.label
            parts.append(localised(lang.code, "concept", label=label))
        else:
            parts.append(localised(lang.code, "provision"))

        note = localised(lang.code, "quote_note")
        if note:
            parts.append(f"\n{note}")

        top = res.hits[0].score if res.hits else 0.0
        for n, hit in enumerate(res.hits[:2]):
            r = hit.record
            if r["authority_rank"] >= 6 and not res.background_only:
                continue
            # A distant second provision is noise, not thoroughness. Quote it
            # only when it is genuinely competitive with the first.
            if n and hit.score < 0.5 * top:
                break
            # If a concept pin-cites a clause, quote that clause. Reciting the
            # whole of section 3 when the question is about clause (p) buries
            # the answer under fifteen irrelevant exclusions.
            clause = pin_for_hit(res, r)
            if clause and clause in r.get("clauses", {}):
                body = r["clauses"][clause]
                label = f"{_provision_label(r)}({clause})"
            else:
                body = " ".join(operative_sentences(r["text"], qt))
                label = _provision_label(r)
            quoted = re.sub(r"\s+", " ", body).strip()
            if r["authority_rank"] >= 6:
                # Reference material has no section number worth printing, and
                # its "heading" is just the first line of the page.
                page_word = localised(lang.code, "page")
                where = f"{r['act_title']}, {page_word} {r['page_start']}"
            else:
                where = f"{r['act_title']}, {label} — {r['heading']}"
            parts.append(f"\n\n{where}:\n“{clip_quote(quoted)}”")
        return "".join(parts)


# ------------------------------------------------------------------ Claude ---
SYSTEM = """You answer questions about Indian IP and AYUSH regulatory law for \
practitioners and small manufacturers.

Absolute rules:
- Use ONLY the numbered provision extracts supplied in the user message. They \
are verbatim statutory text.
- Never state a section number, date, percentage or time limit that does not \
appear in those extracts.
- If the extracts do not answer the question, say so plainly. Do not reason \
from general knowledge of law. Saying "the ingested corpus does not cover this" \
is a correct and valued answer.
- Cite as [1], [2] matching the extract numbers, on the sentence they support.
- No preamble, no "great question". 3-6 sentences. Plain language a vaidya or a \
small manufacturer can act on, but never soften a prohibition into a suggestion.
- Close with the single most useful next step if one is clear from the extracts.

You are not giving legal advice; you are reporting what the cited provisions say."""


class ClaudeAnswerer:
    name = "claude (verified by PRAMANA)"

    def __init__(self, model: str = "claude-sonnet-5"):
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model

    def write(self, question: str, res: RetrievalResult) -> str:
        blocks = []
        for i, hit in enumerate(res.hits[:5], 1):
            r = hit.record
            blocks.append(
                f"[{i}] {r['act_title']} — Section {r['section']} "
                f"({r['heading']})\n"
                f"source: {r['source_pdf']} p.{r['page_start']}\n"
                f"{r['text'][:2500]}"
            )
        prompt = (
            f"Question: {question}\n\n"
            f"Provision extracts:\n\n" + "\n\n---\n\n".join(blocks)
        )
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=700,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in msg.content if b.type == "text").strip()


# ------------------------------------------------------------------ Ollama --
OLLAMA_SYSTEM = """You are AyurLex, answering questions about Indian intellectual property and AYUSH regulatory law for practitioners and small manufacturers.

ABSOLUTE RULES — these override every other instruction:
1. Use ONLY the numbered extracts supplied. They are verbatim statutory text.
2. Never state a section number, rule number, date, percentage or time limit that does not appear in the extracts. If you are unsure, leave it out.
3. If the extracts do not answer the question, say exactly that. "The ingested corpus does not cover this" is a correct and valued answer. Never fill a gap with general knowledge.
4. Cite as [1], [2] matching the extract numbers, placed on the sentence they support.
5. Do not invent obligations, penalties, fees or deadlines.

6. Answer in ENGLISH, whatever language the question is in. The answer is translated afterwards; that is not your job here.

STYLE: 3-4 short sentences, under 90 words, and always finish the sentence you are in. Do not repeat a clause you have already written. Never put statutory
text in quotation marks unless you are copying it exactly from an extract. No preamble, no "great question". Plain language a vaidya or a small manufacturer can act on. Never soften a prohibition into a suggestion. End with the single most useful next step if the extracts make one clear.

You report what the cited provisions say. You do not give legal advice."""

# Generation cap. It was 170, which is roughly 130 words -- below the length
# the model actually writes, so answers were being cut off in mid-clause
# ("...Where biological resources or") and the fragment then went to the
# verifier as though it were a finished sentence. The cap now sits above the
# instructed length rather than below it, and trim_incomplete() removes any
# tail that still gets clipped.
NUM_PREDICT = 420


def trim_incomplete(text: str) -> str:
    """Drop a trailing fragment left behind by the token limit.

    Only ever removes from the end, and only when there is a completed
    sentence to fall back to: truncating an answer is a display problem,
    silently deleting the whole of it would be a correctness one.
    """
    t = text.rstrip()
    if not t or t[-1] in ".!?;:”\"।॥":
        return t
    cut = max(t.rfind(". "), t.rfind("! "), t.rfind("? "), t.rfind("। "))
    if cut <= 0:
        return t
    return t[:cut + 1].rstrip()


# How much of a sentence's content has to be carried by an earlier sentence
# before it is restating rather than adding.
REDUNDANT = 0.85

# Crude suffix stripping, used ONLY for the redundancy test below. A model
# restating itself reaches for a different inflection -- "the Authority
# determines benefit sharing" then "benefit sharing is determined by the
# Authority" -- and on exact tokens those two sentences overlap 0.80, just
# under the bar. This is deliberately not applied to pramana.content_words:
# the citation gate is a check on whether a claim is supported, and making
# that comparison fuzzier makes it weaker.
_SUFFIX = ("ations", "ation", "ements", "ement", "ings", "ing", "ers",
           "ies", "ied", "ed", "es", "s")


def _stem(word: str) -> str:
    for suf in _SUFFIX:
        if word.endswith(suf) and len(word) - len(suf) >= 4:
            return word[:-len(suf)]
    return word


def dedupe_sentences(text: str) -> str:
    """Remove sentences that restate one already written.

    Raising the token cap fixed the truncation and immediately exposed what
    the cap had been hiding: a 1.5B model given room to run says the same
    thing three times. On "what is benefit sharing under Section 21" it listed
    joint ownership, transfer of technology and venture capital funds in three
    separate paragraphs.

    This runs BEFORE verification, not inside it, so the groundedness score is
    computed over what the user is actually shown. Counting a restatement as a
    separate supported sentence inflates the score with the same claim twice,
    which is the sort of number that looks like evidence and is not.
    """
    kept: list[str] = []
    seen: list[set[str]] = []
    for sent in [s.strip() for s in SENT.split(text) if s.strip()]:
        w = {_stem(x) for x in content_words(sent)}
        if w and any(len(w & prior) / len(w) >= REDUNDANT for prior in seen):
            continue
        seen.append(w)
        kept.append(sent)
    return " ".join(kept)


def build_prompt(question: str, res: RetrievalResult, lang: Language) -> str:
    """Assemble the extracts the model is allowed to use, and nothing else.

    Background (rank 6) material is labelled as such in the prompt itself, so
    the model describes from it but never treats it as authority.

    The model is asked for English regardless of the question's language, and
    the verified English is localised afterwards (rag.translate). Asking a
    small local model to do grounded legal reasoning AND write Tamil in one
    pass got neither: the Tamil was degenerate, and because the citation gate
    is a content-word overlap against English spans it could not see that, so
    the answer was dropped and the user got the English fallback anyway.
    Splitting the two puts each step on ground it can be checked on.
    """
    blocks = []
    for i, hit in enumerate(res.hits[:PROMPT_HITS], 1):
        r = hit.record
        clause = pin_for_hit(res, r)
        body = (r["clauses"].get(clause) if clause and r.get("clauses")
                else None) or r["text"]
        kind = ("BACKGROUND — descriptive only, NOT law, never cite as a rule"
                if r["authority_rank"] >= 6 else "STATUTE — binding law")
        pin = f"({clause})" if clause else ""
        header = (
            f"[{i}] ({kind}) {r['act_title']} — "
            f"Section {r['section']}{pin} — {r['heading']}"
        )
        source = f"source: {r['source_pdf']} p.{r['page_start']}"
        blocks.append("\n".join([header, source, body[:2200]]))

    return "\n\n".join([
        "Answer in English. Keep statutory terms and section numbers exactly "
        "as they appear in the extracts.",
        f"Question: {question}",
        "Extracts:",
        "\n\n---\n\n".join(blocks),
    ])


class OllamaAnswerer:
    """The default generator: a local model, phrasing retrieved text only.

    Its output goes through the same verification gate as everything else, so
    the model cannot introduce an authority the retrieval did not find.
    """

    def __init__(self, model: str | None = None):
        from rag.llm import Ollama

        self.client = Ollama(model)
        self.name = f"ollama · {self.client.model} (verified by PRAMANA)"

    def write(self, question: str, res: RetrievalResult) -> str:
        lang = detect(question)
        return dedupe_sentences(trim_incomplete(self.client.generate(
            build_prompt(question, res, lang), OLLAMA_SYSTEM,
            num_predict=NUM_PREDICT,
        )))


# ----------------------------------------------------------------- gateway --
def pick_backend(prefer: str = "auto", model: str | None = None
                 ) -> AnswerBackend:
    """Ollama by default, started if it is not already running.

    Everything stays local: no API key, no network, and the formulation never
    leaves the machine. If Ollama genuinely cannot be reached we fall back to
    the extractive backend rather than failing -- a degraded answer that still
    quotes the right provision beats an error page.
    """
    if prefer == "extractive":
        return ExtractiveAnswerer()
    if prefer == "claude":
        try:
            return ClaudeAnswerer()
        except Exception:
            return ExtractiveAnswerer()
    try:
        return OllamaAnswerer(model)
    except Exception:
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                return ClaudeAnswerer()
            except Exception:
                pass
        return ExtractiveAnswerer()


# A model asked about patents will reach for the names of other statutes it
# knows. "Plant Variety Rights Act (PVR Act)" is the exact failure observed:
# plausible, adjacent, not in the extracts, and invisible to a numeric check
# because it contains no digits. Any instrument named in an answer must appear
# in the retrieved text.
INSTRUMENT_NAME = re.compile(
    r"\b(?:[A-Z][A-Za-z&'-]+\s+){1,6}(?:Act|Rules|Regulations|Treaty|"
    r"Convention|Protocol|Agreement)\b(?:,?\s*\d{4})?"
)

# Anything the model presents inside quotation marks.
QUOTED = re.compile(r"[\"“]([^\"”]{12,400})[\"”]")

# Whole numbers including comma grouping and decimals.
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def verify_against_spans(text: str, res: RetrievalResult
                         ) -> tuple[str, float, list[str]]:
    """PRAMANA applied to free text: every sentence must be carried by a
    retrieved span, or by the fixed connective vocabulary of the answer itself."""
    spans = " ".join(h.record["text"] for h in res.hits[:PROMPT_HITS])
    meta = " ".join(f"{h.record['act_title']} Section {h.record['section']} "
                    f"{h.record['heading']}" for h in res.hits[:PROMPT_HITS])
    haystack = spans + " " + meta
    hay_norm = re.sub(r"\s+", " ", haystack).lower()

    kept, dropped, scores = [], [], []
    for sent in [s.strip() for s in SENT.split(text) if s.strip()]:
        # Numerics take the exact-match path, as everywhere else in the system.
        # Comma-grouped numbers must be matched whole: splitting "5,000"
        # into "5" and "000" lets it pass on any span containing a 5.
        nums = NUMBER.findall(sent)
        bad = [n for n in nums if n not in haystack]

        # Quoted text must be verbatim. Observed failure: the model wrote that
        # s.3(p) 'defines an invention as "an innovation or improvement which
        # is new, involves an inventive step..."' -- a definition that appears
        # nowhere in the section, presented inside quotation marks as if read
        # off the page. A paraphrase the reader can weigh is one thing; a
        # fabricated quotation is a different and much worse failure, so
        # quotation marks are held to exact match.
        for quoted in QUOTED.findall(sent):
            body = quoted.strip(" .,:;")
            if len(body) < 12:
                continue
            if re.sub(r"\s+", " ", body).lower() not in hay_norm:
                bad.append(f'quotation: "{body[:60]}…"')

        # Named instruments take the same exact-match path. Every distinctive
        # word of the name must be present -- ANY-match is useless here, since
        # "Plant Variety Rights Act" shares "rights" with almost any statute
        # and would sail through.
        for name in INSTRUMENT_NAME.findall(sent):
            key = re.sub(r"\s+", " ", name).strip().lower()
            core = [w for w in re.findall(r"[a-z]{4,}", key)
                    if w not in {"act", "rules", "regulations", "the", "under",
                                 "this", "said", "such", "same"}]
            if core and not all(w in hay_norm for w in core):
                bad.append(name)

        score = entailment_score(sent, haystack)
        if bad or score < 0.34:
            dropped.append(sent)
            continue
        scores.append(score)
        kept.append(sent)

    # Groundedness is the MEAN entailment of the sentences actually shown.
    #
    # It used to be the fraction of sentences clearing ENTAILED (0.55), over a
    # denominator that also counted the dropped ones. That had two defects and
    # they compounded:
    #
    #   * The gate SHOWS a sentence at 0.34 but only COUNTED it at 0.55, so
    #     every sentence scoring in between was displayed and scored zero. An
    #     answer whose sentences all landed at 0.5 read "groundedness 0.00"
    #     while being, by the gate's own decision, well enough supported to
    #     print. Measured on one question across three runs of the local model,
    #     the same question returned 0.750, 0.200 and 0.000 -- and the 0.000
    #     run still displayed two sentences.
    #   * It threw away the continuous measure it was computed from. 0.54 and
    #     0.00 are not the same situation and the old formula reported them
    #     identically, which is precisely the information a confidence
    #     indicator exists to carry.
    #
    # So the pill now answers the question a reader is actually asking: how
    # well is the text in front of me carried by the provision it cites? What
    # the gate REMOVED is reported separately -- the UI already prints the
    # dropped count and quotes what went -- rather than being folded into one
    # number where a reader cannot tell the two apart.
    #
    # `entailed_fraction` keeps the strict measure available for anyone who
    # wants it. Nothing is hidden; the two numbers just stopped being averaged
    # into one that meant neither.
    grounded = (sum(scores) / len(scores)) if scores else 0.0
    return " ".join(kept), round(grounded, 3), dropped


def entailed_fraction(scores: list[float]) -> float:
    """The strict measure: what share of shown sentences are fully entailed.

    Kept as a separate number rather than as the headline, for the reasons in
    verify_against_spans. A high mean with a low fraction means the answer is
    broadly traceable but paraphrases loosely; both facts are worth having.
    """
    if not scores:
        return 0.0
    return round(sum(1 for s in scores if s >= ENTAILED) / len(scores), 3)


def abstention_text(lang: Language, reason: str) -> str:
    """The abstention, in the user's language.

    This is the answer given when the system has nothing, so it is the one
    sentence that must never itself be broken. It comes from the hand-written
    table, not from a model.
    """
    from core.localise import full_stop

    stop = "" if reason.rstrip().endswith((".", "।", "۔")) else full_stop(lang.code)
    return (f"{localised(lang.code, 'abstention')}\n\n"
            f"{localised(lang.code, 'why')}: {reason}{stop}")


def localise(text: str, lang: Language) -> tuple[str, bool]:
    """Render a verified answer in the user's language, or say why not."""
    from rag.translate import english_note, localise_answer

    out, ok = localise_answer(text, lang)
    if ok or lang.is_english:
        return out, ok
    note = english_note(lang)
    return (f"{out}\n\n{note}" if note else out), False


# ---------------------------------------------------------------- polarity ---
# A question like "do I need NBA approval before filing?" has an answer whose
# entire content is its polarity. The citation gate cannot check polarity: it
# verifies that a sentence is carried by spans of the retrieved provision, and
# "you do not need approval" is built from the same words as the provision that
# requires it. Measured on the local 1.5B model, three of four such questions
# came back with the polarity inverted -- including "No, you do not need
# approval from the National Biodiversity Authority", against a section headed
# "Application for intellectual property rights not to be made without
# approval".
#
# A lexical contradiction test was tried first and does not work: every
# statutory span carries both mandatory language and a proviso, so "shall" and
# "except" appear together in all of them and discriminate nothing.
#
# So the model is taken out of this class of question entirely. The provision is
# quoted instead of paraphrased, which is duller and correct, and the UI says
# that is what happened. This is the same trade the extractive fallback already
# makes when a draft fails the gate.
POLARITY_QUESTION = re.compile(
    # First person only. "What does the Nagoya Protocol require?" asks what a
    # duty contains and the model answers it well; "do I need approval?" asks
    # whether the duty binds the asker, and that is the polarity the gate
    # cannot check.
    r"\b(?:"
    r"do(?:es)?\s+(?:i|we|my|our)\b[^?.]{0,60}?\b(?:need|require)\b"
    r"|do\s+(?:i|we)\s+have\s+to\b"
    r"|must\s+(?:i|we|my|our)\b"
    r"|(?:am\s+i|are\s+we)\s+(?:required|obliged)\b"
    r"|is\s+(?:it|there|an?|any|prior)\b[^?.]{0,50}?\b"
    r"(?:required|necessary|mandatory|compulsory)\b"
    r"|need\s+i\b"
    r")",
    re.I,
)

# The guard is about a duty, not about permission. "Can I patent X" is answered
# by a prohibition and the model handles it correctly, so it stays on the
# drafting path.
POLARITY_GUARD_REASON = (
    "this question turns on whether a duty applies, so the provision is quoted "
    "rather than paraphrased"
)


def turns_on_polarity(question: str) -> bool:
    return bool(POLARITY_QUESTION.search(question))


def answer(question: str, res: RetrievalResult, *,
           backend: AnswerBackend | None = None) -> Answer:
    backend = backend or pick_backend()
    lang = detect(question)

    if res.is_weak:
        # The out-of-corpus reason stays in English: it is composed at runtime
        # and names instruments (TRIPS, the Nagoya Protocol), which the
        # terminology lock forbids translating in any case.
        reason = res.out_of_corpus or localised(lang.code, "why_weak")
        return Answer(
            question=question, text=abstention_text(lang, reason),
            abstained=True, abstain_reason=reason, backend=backend.name,
            taxa=res.taxa_expansions, language=lang.code,
            language_name=lang.name,
        )

    # Take the model out of questions whose whole answer is a polarity.
    guard = ""
    if turns_on_polarity(question) and not isinstance(backend, ExtractiveAnswerer):
        backend = ExtractiveAnswerer()
        guard = POLARITY_GUARD_REASON

    raw = backend.write(question, res)

    if isinstance(backend, ExtractiveAnswerer):
        # Nothing to verify: the text is quotation plus fixed connectives, and
        # the connectives are already in the user's language.
        text, grounded, dropped = raw, 1.0, []
    else:
        # The draft is English by construction (see build_prompt), so the gate
        # runs on text it can actually check. Localisation happens after.
        text, grounded, dropped = verify_against_spans(raw, res)
        if not text.strip():
            return Answer(
                question=question,
                text=abstention_text(lang, localised(lang.code, "why_gate")),
                abstained=True,
                abstain_reason="generated text failed the citation gate",
                backend=backend.name, dropped=dropped,
                taxa=res.taxa_expansions, language=lang.code,
                language_name=lang.name,
            )
        text, _ok = localise(text, lang)

    # Background answers cite the reference material they came from; legal
    # answers never cite rank-6 material as authority.
    if res.background_only:
        cits = [to_citation(h) for h in res.hits[:3]]
    else:
        cits = [to_citation(h) for h in res.hits[:3]
                if h.record["authority_rank"] < 6]
    return Answer(
        question=question, text=text, citations=cits, groundedness=grounded,
        concept=res.concepts[0].concept.id if res.concepts else "",
        concept_label=res.concepts[0].concept.label if res.concepts else "",
        suggested_rules=res.rules, dropped=dropped, backend=backend.name,
        taxa=res.taxa_expansions, language=lang.code, language_name=lang.name,
        background_only=res.background_only,
        guard=guard,
    )
