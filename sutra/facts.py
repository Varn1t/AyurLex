"""Fact extraction: Formulation -> a flat, typed fact table.

Everything a SUTRA rule can test lives here, and every value is computed
deterministically from the formulation, the resolver and the ingested corpus.
No LLM touches this stage. If a fact cannot be established, it is None and the
rules that depend on it abstain -- which is a shipped feature, not a gap.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.resolver import Resolution, load_resolver
from core.schema import ClaimType, FilingIntent, Formulation, Jurisdiction

ROOT = Path(__file__).resolve().parent.parent
DMR_SCHEDULE = ROOT / "corpus" / "dmr_schedule.json"
TKDL_OUTCOMES = ROOT / "corpus" / "tkdl_outcomes.jsonl"

# Classical formulations whose constituent sets are common knowledge in the
# trade. Membership is decided by taxon set, so it survives any spelling or
# language the user types. Kept as data, not as prose in a prompt.
CLASSICAL_SETS: list[dict[str, Any]] = [
    {
        "name": "Triphala",
        "taxa": {"Emblica officinalis", "Terminalia chebula",
                 "Terminalia bellirica"},
        "basis": "Three-fruit classical combination; constituents carry the "
                 "TRIPHALA_CONSTITUENT flag in the curated taxa dataset.",
    },
    {
        "name": "Trikatu",
        "taxa": {"Piper longum", "Piper nigrum", "Zingiber officinale"},
        "basis": "Three-pungents classical combination; constituents carry the "
                 "TRIKATU_CONSTITUENT flag in the curated taxa dataset.",
    },
]

_WORD = re.compile(r"[a-z]{3,}")
_CLAIM_STOP = {
    "for", "the", "and", "with", "from", "our", "this", "that", "all", "any",
    "cure", "cures", "treatment", "treats", "helps", "relief", "natural",
    "herbal", "ayurvedic", "formula", "product", "safe", "best", "100",
}


@dataclass
class FactTable:
    values: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, str] = field(default_factory=dict)

    def set(self, path: str, value: Any, why: str = "") -> None:
        self.values[path] = value
        if why:
            self.provenance[path] = why

    def get(self, path: str, default: Any = None) -> Any:
        return self.values.get(path, default)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.values)


def _load_schedule() -> dict:
    if not DMR_SCHEDULE.exists():
        return {"items": [], "count": 0}
    return json.loads(DMR_SCHEDULE.read_text(encoding="utf-8"))


def _load_tkdl() -> list[dict]:
    if not TKDL_OUTCOMES.exists():
        return []
    return [json.loads(l) for l in TKDL_OUTCOMES.open(encoding="utf-8") if l.strip()]


def screen_claims(claims: list[str]) -> list[dict]:
    """Match marketing claims against the statutory Schedule.

    A hit is reported with the exact scheduled entry it matched, so the finding
    can point at the list item rather than assert a conclusion.
    """
    sched = _load_schedule()
    hits = []
    for claim in claims:
        low = claim.lower()
        for item in sched["items"]:
            # Match on the distinctive words of the scheduled entry, ignoring
            # its parenthetical qualifiers ("Fevers (in general)" -> "fever").
            core = re.sub(r"\(.*?\)", " ", item).lower()
            terms = [w for w in _WORD.findall(core) if w not in _CLAIM_STOP]
            if not terms:
                continue
            for t in terms:
                stem = t[:-1] if t.endswith("s") and len(t) > 4 else t
                if re.search(rf"\b{re.escape(stem)}", low):
                    hits.append({"claim": claim, "scheduled_item": item,
                                 "matched_term": t})
                    break
            else:
                continue
            break
    return hits


def match_prior_art(taxa: list[str], indications: list[str]) -> list[dict]:
    """Score the formulation against the TKDL outcome index extracted from the
    dataset. Scoring is transparent term overlap -- every match reports which
    terms drove it, so a reviewer can check it by eye."""
    rows = _load_tkdl()
    ing_terms = set()
    for t in taxa:
        ing_terms.update(w.lower() for w in _WORD.findall(t))
    ind_terms = set()
    for i in indications:
        ind_terms.update(w.lower() for w in _WORD.findall(i.lower())
                         if w not in _CLAIM_STOP)

    scored = []
    for r in rows:
        terms = set(r.get("terms", []))
        overlap = (terms & ind_terms) | (terms & ing_terms)
        # A bare "herbal composition" title matches everything; require that at
        # least one indication or taxon term lines up before we call it a hit.
        signal = (terms & ind_terms) | (terms & ing_terms)
        if not signal:
            continue
        weight = 2.0 if r["outcome"] in ("REVOKED", "REFUSED") else 1.0
        score = weight * len(overlap) / max(len(terms | ind_terms), 1)
        scored.append({**r, "score": round(score, 4),
                       "matched_terms": sorted(overlap)})
    scored.sort(key=lambda r: (-r["score"], r["application_no"]))
    return scored[:5]


def classify_classical_match(taxa: set[str], formulation: Formulation) -> dict:
    """Decide whether the composition, as claimed, is matter already described
    in the traditional corpus. Returns the match type consumed by the Patents
    Act s.3(p) rule."""
    for cs in CLASSICAL_SETS:
        if cs["taxa"] and cs["taxa"] <= taxa:
            extra = taxa - cs["taxa"]
            if not extra:
                return {"type": "EXACT", "classical_name": cs["name"],
                        "basis": cs["basis"], "extra_taxa": []}
            return {"type": "SUBSET_OF_CLASSICAL", "classical_name": cs["name"],
                    "basis": cs["basis"], "extra_taxa": sorted(extra)}

    # An all-known-constituent blend whose asserted effect is the sum of the
    # constituents' documented effects, with no synergy evidence, is the
    # aggregation case rather than the identity case.
    if len(taxa) >= 2 and not formulation.evidence.has_synergy_data:
        res = load_resolver()
        documented = [t for t in taxa
                      if any(x.taxon == t and x.record.get("classical_use")
                             for x in res.taxa)]
        if len(documented) == len(taxa) and taxa:
            return {"type": "KNOWN_PROPERTY_AGGREGATION",
                    "classical_name": None,
                    "basis": "every constituent has documented classical use "
                             "and no synergy evidence was supplied",
                    "extra_taxa": []}
    return {"type": "NONE", "classical_name": None, "basis": "", "extra_taxa": []}


def build_facts(f: Formulation, resolutions: list[Resolution]) -> FactTable:
    ft = FactTable()
    taxa = {r.taxon for r in resolutions if r.taxon}
    accepted = [r for r in resolutions if r.is_accepted]
    unresolved = [r for r in resolutions if r.path == "UNRESOLVED"]
    ambiguous = [r for r in resolutions
                 if r.path in ("AMBIGUOUS", "FUZZY_PROPOSED")]

    # ---- resolution ----------------------------------------------------
    ft.set("resolution.total", len(resolutions))
    ft.set("resolution.accepted_count", len(accepted))
    ft.set("resolution.unresolved_count", len(unresolved))
    ft.set("resolution.ambiguous_count", len(ambiguous))
    ft.set("resolution.has_ambiguity", bool(ambiguous or unresolved))
    ft.set("resolution.ambiguous_names", [r.raw_name for r in ambiguous])
    ft.set("resolution.unresolved_names", [r.raw_name for r in unresolved])
    ft.set("resolution.taxa", sorted(taxa))

    # ---- ingredients / sourcing ---------------------------------------
    flags: set[str] = set()
    for r in resolutions:
        if r.record:
            flags.update(r.record.get("schedule_flags", []))
    ft.set("ingredients.count", len(f.ingredients))
    ft.set("ingredients.schedule_flags", sorted(flags))
    ft.set("ingredients.has_cites_listed", "CITES_LISTED" in flags)
    ft.set("ingredients.has_threatened", "THREATENED_MEDICINAL_PLANT" in flags)
    ft.set("ingredients.has_restricted_export", "RESTRICTED_EXPORT" in flags)
    ft.set("ingredients.has_landmark_tk_case", "TKDL_LANDMARK_CASE" in flags)

    declared_indian = [i for i in f.ingredients if i.is_from_indian_bioresource]
    taxon_indian = [r for r in resolutions
                    if r.record and r.record.get("indian_bioresource")]
    ft.set("bioresource.uses_indian_biological_resource",
           bool(declared_indian or taxon_indian))
    ft.set("bioresource.indian_count", max(len(declared_indian), len(taxon_indian)))
    cultivated = [i for i in f.ingredients if i.is_cultivated]
    ft.set("bioresource.all_declared_cultivated",
           bool(f.ingredients) and len(cultivated) == len(f.ingredients))
    ft.set("bioresource.cultivation_status_unknown",
           any(i.is_cultivated is None for i in f.ingredients))

    # ---- prior art -----------------------------------------------------
    cm = classify_classical_match(taxa, f)
    ft.set("prior_art.classical_match_type", cm["type"],
           why=cm["basis"] or "no classical set matched")
    ft.set("prior_art.classical_name", cm["classical_name"])
    ft.set("prior_art.classical_basis", cm["basis"])
    ft.set("prior_art.extra_taxa", cm["extra_taxa"])

    pa = match_prior_art(sorted(taxa), f.indications)
    ft.set("prior_art.tkdl_hits", len(pa))
    ft.set("prior_art.tkdl_top", pa[0] if pa else None)
    ft.set("prior_art.tkdl_adverse_outcome",
           bool(pa) and pa[0]["outcome"] in ("REVOKED", "REFUSED"))
    ft.set("prior_art.all_hits", pa)

    # ---- claims / filing ----------------------------------------------
    ft.set("filing.intent", f.filing_intent.value)
    ft.set("filing.seeks_composition_claim",
           ClaimType.COMPOSITION in f.claim_types)
    ft.set("filing.seeks_process_claim", ClaimType.PROCESS in f.claim_types)
    ft.set("filing.foreign_first",
           f.filing_intent in (FilingIntent.FOREIGN_FIRST, FilingIntent.PCT))
    ft.set("filing.applicant_is_indian_resident", f.applicant_is_indian_resident)
    ft.set("filing.applicant_type", f.applicant_type.value)
    ft.set("applicant.is_exempt_practitioner", f.applicant_is_exempt_practitioner)
    ft.set("filing.targets_foreign_market",
           any(j != Jurisdiction.IN for j in f.target_markets))
    ft.set("filing.target_markets", [j.value for j in f.target_markets])

    # ---- process / evidence -------------------------------------------
    ft.set("process.has_non_obvious_step", f.process.has_non_obvious_step)
    ft.set("process.novel_step_count", len(f.process.novel_steps))
    ft.set("process.standardised", bool(f.process.standardised_marker))
    ft.set("evidence.has_synergy_data", f.evidence.has_synergy_data)
    ft.set("evidence.has_clinical_data", f.evidence.has_clinical_data)
    ft.set("evidence.has_documented_traditional_use",
           f.evidence.has_documented_traditional_use)
    ft.set("evidence.traditional_use_years", f.evidence.traditional_use_years)
    ft.set("evidence.nba_approval_obtained", f.evidence.nba_approval_obtained)
    ft.set("evidence.foreign_filing_permit", f.evidence.foreign_filing_permit)

    # ---- advertising screen -------------------------------------------
    hits = screen_claims(f.marketing_claims)
    ft.set("claims.count", len(f.marketing_claims))
    ft.set("claims.scheduled_hits", len(hits))
    ft.set("claims.scheduled_matches", hits)
    ft.set("claims.first_hit", hits[0] if hits else None)
    ft.set("claims.has_scheduled_disease_claim", bool(hits))

    # ---- documented traditional use, for the regulatory lane -----------
    has_classical = cm["type"] != "NONE" or any(
        r.record and r.record.get("classical_use") for r in resolutions
    )
    ft.set("traditional_use.documented", has_classical)
    ft.set("traditional_use.source",
           cm["classical_name"] or "constituent-level documented classical use")

    ft.set("formulation.name", f.name)
    ft.set("formulation.dosage_form", f.dosage_form.value)
    ft.set("formulation.indications", f.indications)
    return ft
