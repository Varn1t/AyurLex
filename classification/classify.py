"""Deterministic regulatory classification of a formulation.

The decision is a small ordered rule set over five facts, not a model call.
That is deliberate: the category decides the whole downstream posture, so it
must be reproducible and it must be explainable in terms of the facts the user
actually supplied. Where a fact is missing, the classifier says which question
would settle it rather than guessing -- the minimum clarifying questions, which means asking only for facts that would
change the answer.

Every category's provision ids are verified against the corpus at load time,
exactly like a compliance rule or a RAG concept. A category pointing at a provision
that does not resolve fails loudly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from sources.index import Corpus, load_corpus

ROOT = Path(__file__).resolve().parent.parent
CLASSES = ROOT / "data" / "formulation_classes.yaml"

# The five facts the categories turn on. Each is tri-state: True, False, or
# None for "not yet known", because "no disease claim" and "nobody has said
# whether there is a disease claim" are different situations and only one of
# them is safe to act on.
FACTS = (
    "purified_fraction",
    "classical_text_formulation",
    "authoritative_ingredients",
    "disease_claim",
    "cosmetic_use",
    "food_positioning",
)

# What to ask when a fact is missing. Phrased for a vaidya or an MSME founder,
# not for a lawyer.
QUESTIONS = {
    # Phrased so a bare "yes" or "no" is unambiguous. An either/or question
    # cannot be answered with a yes, and the answer is recorded as a fact.
    "purified_fraction":
        "Is the product a purified or standardised extract with defined "
        "bio-active constituents (rather than the whole herb or a traditional "
        "preparation)?",
    "classical_text_formulation":
        "Is both the formula and the method of preparation taken from a "
        "classical text listed in the First Schedule (for example the "
        "Ayurvedic Formulary of India), or is the combination your own?",
    "authoritative_ingredients":
        "Are all the ingredients ones named in the authoritative books of "
        "Ayurveda, Siddha or Unani?",
    "disease_claim":
        "Does the product claim to treat, cure, mitigate or prevent a disease?",
    "cosmetic_use":
        "Is it applied to the body for cleansing, beautifying or altering "
        "appearance?",
    "food_positioning":
        "Is it sold as a food, drink or nutraceutical rather than as a "
        "medicine?",
}


@dataclass
class FormulationClass:
    id: str
    label: str
    when: str
    provisions: list[str]
    pins: dict[str, str] = field(default_factory=dict)
    requires: str = ""
    ip: str = ""
    abs: str = ""
    uncited_authority: str = ""
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


@dataclass
class Classification:
    """The outcome. `category` is None when a fact that would change the answer
    is missing, in which case `ask` carries the questions to put to the user."""

    category: FormulationClass | None = None
    facts: dict[str, bool | None] = field(default_factory=dict)
    ask: list[str] = field(default_factory=list)
    because: str = ""

    @property
    def decided(self) -> bool:
        return self.category is not None


PIN = re.compile(r"^(?P<id>[^()]+)\((?P<clause>[^()]+)\)$")


def split_pin(spec: str) -> tuple[str, str | None]:
    m = PIN.match(spec.strip())
    return (m.group("id"), m.group("clause")) if m else (spec.strip(), None)


class ClassIndex:
    def __init__(self, path: Path = CLASSES, corpus: Corpus | None = None):
        corpus = corpus or load_corpus()
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        self.classes: list[FormulationClass] = []
        for c in raw:
            ids, pins = [], {}
            for spec in c.get("provisions", []):
                pid, clause = split_pin(spec)
                ids.append(pid)
                if clause:
                    pins[pid] = clause
            fc = FormulationClass(
                id=c["id"], label=c["label"], when=c["when"],
                provisions=ids, pins=pins,
                requires=(c.get("requires") or "").strip(),
                ip=(c.get("ip") or "").strip(),
                abs=(c.get("abs") or "").strip(),
                uncited_authority=(c.get("uncited_authority") or "").strip(),
            )
            for pid in fc.provisions:
                if not corpus.has(pid):
                    fc.problems.append(f"{pid} not in corpus")
                elif pid in fc.pins:
                    clause = fc.pins[pid]
                    if clause not in corpus.get(pid).get("clauses", {}):
                        fc.problems.append(f"{pid} has no clause ({clause})")
            self.classes.append(fc)

    def by_id(self, cid: str) -> FormulationClass | None:
        return next((c for c in self.classes if c.id == cid), None)

    @property
    def problems(self) -> list[str]:
        return [f"{c.id}: {p}" for c in self.classes for p in c.problems]

    # ------------------------------------------------------------------ #
    def classify(self, facts: dict[str, bool | None]) -> Classification:
        """Ordered tests, narrowest category first.

        Each branch either decides, or reports the single question that would
        decide it. The order is the legal order: a standardised fraction is a
        phytopharmaceutical whatever else is true of it, and a disease claim
        makes something a drug however it is marketed.
        """
        f = {k: facts.get(k) for k in FACTS}
        out = Classification(facts=f)

        def need(*keys: str) -> Classification | None:
            missing = [k for k in keys if f.get(k) is None]
            if missing:
                out.ask = [QUESTIONS[k] for k in missing]
                out.because = (
                    "these facts decide the category, and the category decides "
                    "the IP posture"
                )
                return out
            return None

        # 1. Drug or not, first. A phytopharmaceutical is a species of drug,
        #    so a standardised extract in a face cream that claims nothing is
        #    a cosmetic, not a phytopharmaceutical -- asking about the fraction
        #    before the claim would both mis-classify it and waste a question.
        if (blocked := need("disease_claim")):
            return blocked

        if not f["disease_claim"]:
            if f["cosmetic_use"] is None and f["food_positioning"] is None:
                if (blocked := need("cosmetic_use")):
                    return blocked
            if f["cosmetic_use"]:
                return self._decide(out, "COSMETIC",
                                    "it is applied to the body for appearance "
                                    "and makes no disease claim")
            if f["food_positioning"]:
                return self._decide(out, "AYURVEDA_AAHARA",
                                    "it is positioned as a food rather than a "
                                    "medicine and makes no disease claim")
            # No claim, not a cosmetic, not a food: still an ASU medicine, so
            # fall through to the split below.

        # 2. Within the drugs, a purified and standardised fraction is a
        #    phytopharmaceutical whatever the herbs are.
        if (blocked := need("purified_fraction")):
            return blocked
        if f["purified_fraction"]:
            return self._decide(out, "PHYTOPHARMACEUTICAL",
                                "it is a purified and standardised fraction "
                                "with defined bio-active constituents")

        # 3. Classical text formulation, a new formula from authoritative
        #    ingredients, or something outside both.
        if (blocked := need("classical_text_formulation")):
            return blocked
        if f["classical_text_formulation"]:
            return self._decide(out, "CLASSICAL",
                                "both the formula and the method are drawn "
                                "from a First Schedule authoritative text")

        if (blocked := need("authoritative_ingredients")):
            return blocked
        if f["authoritative_ingredients"]:
            return self._decide(out, "PATENT_PROPRIETARY",
                                "the ingredients are all named in the "
                                "authoritative books but the formula is not")

        return self._decide(out, "NEW_DRUG",
                            "it is not a classical formulation and not built "
                            "only from ingredients in the authoritative books")

    def _decide(self, out: Classification, cid: str, because: str
                ) -> Classification:
        cat = self.by_id(cid)
        if cat is None or not cat.ok:
            # A category whose provisions do not resolve is not usable. Say so
            # rather than emitting an uncitable classification.
            out.because = f"category {cid} is not usable: {cat.problems if cat else 'missing'}"
            return out
        out.category = cat
        out.because = because
        return out


@lru_cache(maxsize=1)
def load_classes() -> ClassIndex:
    return ClassIndex()


# --------------------------------------------------------------- from text ---
# Reading the facts off what the user already said, so the assistant asks only
# for what is genuinely still open. Conservative by design: a phrase must
# actually be present. Nothing here infers a disease claim from an ingredient.
PURIFIED = re.compile(
    r"\b(purified|standardi[sz]ed (?:fraction|extract)|defined bio-?active|"
    r"bio-?active fraction|isolated (?:compound|constituent)|"
    r"phytopharmaceutical|\d+\s*%\s*(?:extract|withanolide|curcumin))\b", re.I)
WHOLE_HERB = re.compile(
    r"\b(whole herb|churna|kwath|kashaya|vati|taila|ghrita|bhasma|asava|"
    r"arishta|powder of|traditional preparation)\b", re.I)
CLASSICAL_TEXT = re.compile(
    r"\b(classical formulation|classical text|first schedule|"
    r"ayurvedic formulary|sharangdhar|bhaishajya ratnavali|"
    r"as per the (?:text|shastra)|textual formulation)\b", re.I)
OWN_FORMULA = re.compile(
    r"\b(my own (?:formula|combination|blend)|our own (?:formula|blend)|"
    r"proprietary (?:formula|blend)|new combination|modified the classical)\b",
    re.I)
# "treating" and "treatment" must both match, or a plain therapeutic claim
# reads as no claim at all and the product is mis-classified as a cosmetic.
DISEASE_CLAIM = re.compile(
    r"\b(cure\w*|treat\w*|prevent\w*|mitigat\w*|"
    r"therapy for|remedy for|heal\w*|indicated for|"
    r"for (?:diabetes|cancer|arthritis|asthma|hypertension))\b", re.I)

# An explicit denial settles the fact; silence does not.
NO_CLAIM = re.compile(
    r"\b(no (?:disease|therapeutic|medicinal|medical) claim|"
    r"makes no (?:disease|therapeutic|medical) claim|"
    r"not claimed to treat|without any disease claim)\b", re.I)
COSMETIC_USE = re.compile(
    r"\b(cosmetic|face ?(?:cream|pack|wash)|skin cream|hair oil|shampoo|"
    r"soap|lotion|beautif\w+|fairness|anti-?wrinkle)\b", re.I)
FOOD_USE = re.compile(
    r"\b(food|beverage|drink|nutraceutical|health supplement|"
    r"dietary supplement|aahar\w*|ayurveda aahara|fssai)\b", re.I)


def facts_from_text(text: str) -> dict[str, bool | None]:
    """Read what the text actually settles; leave the rest None.

    A False is only ever recorded where the text positively indicates the
    opposite -- "my churna" says whole-herb, so purified_fraction is False.
    Silence stays None so the caller asks instead of assuming.
    """
    f: dict[str, bool | None] = {k: None for k in FACTS}

    if PURIFIED.search(text):
        f["purified_fraction"] = True
    elif WHOLE_HERB.search(text):
        f["purified_fraction"] = False

    if CLASSICAL_TEXT.search(text):
        f["classical_text_formulation"] = True
    elif OWN_FORMULA.search(text):
        f["classical_text_formulation"] = False

    # An explicit denial is checked first: "no disease claim" contains no
    # claim language, but "sold as a supplement, not claimed to treat
    # anything" contains both and the denial is the operative half.
    if NO_CLAIM.search(text):
        f["disease_claim"] = False
    elif DISEASE_CLAIM.search(text):
        f["disease_claim"] = True

    if COSMETIC_USE.search(text):
        f["cosmetic_use"] = True
    if FOOD_USE.search(text):
        f["food_positioning"] = True

    return f


def facts_from_formulation(form, text: str = "") -> dict[str, bool | None]:
    """Facts from a parsed Formulation, plus anything the sentence settles."""
    f = facts_from_text(text or "")

    # A marketing claim already parsed off the input is a disease claim if it
    # reads like one. The compiler's BRAND lane makes the same reading.
    claims = " ".join(getattr(form, "marketing_claims", []) or [])
    if claims and DISEASE_CLAIM.search(claims):
        f["disease_claim"] = True

    # A dosage form recorded on the formulation is a whole-herb preparation.
    form_kind = getattr(getattr(form, "dosage_form", None), "value", None)
    if form_kind in {"churna", "vati", "kashaya", "asava_arishta", "taila",
                     "ghrita", "bhasma"}:
        f.setdefault("purified_fraction", None)
        if f["purified_fraction"] is None:
            f["purified_fraction"] = False
    elif form_kind == "extract":
        if f["purified_fraction"] is None:
            f["purified_fraction"] = True

    # Stated fields settle what prose can only suggest. These were ignored, so
    # a product entered as "classical: yes" was still asked whether it was
    # classical. Unset (None) stays unset, so the question is still asked.
    classical = getattr(form, "is_classical_formulation", None)
    if classical is not None:
        f["classical_text_formulation"] = classical
    process = getattr(form, "process", None)
    if getattr(process, "standardised_marker", None):
        f["purified_fraction"] = True

    return f


# ------------------------------------------------------------------ payload ---
def classification_payload(result: Classification | None) -> dict | None:
    """The classification as JSON, with the provisions that define the category
    resolved into real citations.

    The citation is built from the corpus, not from the YAML, so a category can
    never present an instrument name or a page number that the ingested source
    does not actually carry.
    """
    if result is None:
        return None

    out: dict = {
        "decided": result.decided,
        "because": result.because,
        "ask": list(result.ask),
        "facts": {k: v for k, v in result.facts.items() if v is not None},
        "citations": [],
    }
    if not result.decided:
        return out

    c = result.category
    out.update(category=c.id, label=c.label, requires=c.requires,
               ip=c.ip, abs=c.abs, uncited_authority=c.uncited_authority)

    corpus = load_corpus()
    for pid in c.provisions:
        if not corpus.has(pid):
            continue
        r = corpus.get(pid)
        clause = c.pins.get(pid)
        # A pinned clause is quoted on its own: reciting the whole definitions
        # section when the category turns on clause (h) buries the answer.
        #
        # But a definition whose body is itself sub-divided -- s.3(h) runs
        # "patent or proprietary medicine means,— (i) in relation to
        # Ayurvedic..." -- has its clause body cut at that "(i)", leaving a
        # stub that says nothing. A pin that yields a stub is less use than
        # the section, so it falls back and drops the pin from the label
        # rather than citing a clause it is not really quoting.
        body = r.get("clauses", {}).get(clause) if clause else None
        if body is not None and len(body.strip()) < 150:
            body, clause = None, None
        quote = body or r["text"]
        sec = str(r["section"])
        label = (f"page {sec[2:]}" if sec.startswith("p.")
                 else f"{r.get('unit', 'Section')} {sec}")
        if clause:
            label = f"{label}({clause})"
        out["citations"].append({
            "corpus_id": r["corpus_id"],
            "instrument": r["act_title"],
            "provision": label,
            "hierarchy": r["hierarchy_path"],
            "pdf": r["source_pdf"],
            "page": r["page_start"],
            "quote": quote.strip(),
            "jurisdiction": r.get("jurisdiction", "IN"),
            "force": r.get("force_note", ""),
        })
    return out
