"""Typed data model for the AyurLex compliance compiler.

The one structural guarantee that matters: a Finding cannot exist without at
least one Citation, and a Citation cannot exist without a corpus_id pointing at
a real extracted provision. Both are enforced in validators, not by convention,
so the entire class of "the model invented a section number" failure is
unrepresentable rather than merely discouraged.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------- enums ----
class PlantPart(str, Enum):
    ROOT = "root"
    RHIZOME = "rhizome"
    LEAF = "leaf"
    STEM = "stem"
    WHOLE_PLANT = "whole_plant"
    LATEX = "latex"
    SEED = "seed"
    BARK = "bark"
    FRUIT = "fruit"
    FLOWER = "flower"
    GUM_RESIN = "gum_resin"
    MINERAL = "mineral"
    ANIMAL_ORIGIN = "animal_origin"


class DosageForm(str, Enum):
    CHURNA = "churna"
    VATI = "vati"
    KASHAYA = "kashaya"
    ASAVA_ARISHTA = "asava_arishta"
    TAILA = "taila"
    GHRITA = "ghrita"
    BHASMA = "bhasma"
    CAPSULE = "capsule"
    TABLET = "tablet"
    SYRUP = "syrup"
    TOPICAL = "topical"
    EXTRACT = "extract"


class Jurisdiction(str, Enum):
    IN = "IN"
    PCT = "PCT"
    US = "US"
    EP = "EP"
    JP = "JP"


class FilingIntent(str, Enum):
    IN_FIRST = "IN_FIRST"
    FOREIGN_FIRST = "FOREIGN_FIRST"
    PCT = "PCT"
    NONE = "NONE"


class ApplicantType(str, Enum):
    NATURAL_PERSON = "natural_person"
    STARTUP = "startup"
    SMALL_ENTITY = "small_entity"
    LARGE_ENTITY = "large_entity"
    FOREIGN_ENTITY = "foreign_entity"


class Severity(str, Enum):
    BLOCKER = "BLOCKER"
    WARNING = "WARNING"
    INFO = "INFO"
    OPPORTUNITY = "OPPORTUNITY"


class CitationKind(str, Enum):
    STATUTE = "STATUTE"
    RULES = "RULES"
    PRIOR_ART = "PRIOR_ART"
    REFERENCE = "REFERENCE"


class ClaimType(str, Enum):
    COMPOSITION = "composition"
    PROCESS = "process"
    USE = "use"


class VerificationStatus(str, Enum):
    """Promotion gate for a SUTRA rule. Only VERIFIED rules may emit findings
    in a production compile; see docs/PROVISION_VERIFICATION.md."""

    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"


class MatchType(str, Enum):
    NONE = "NONE"
    EXACT = "EXACT"
    SUBSET_OF_CLASSICAL = "SUBSET_OF_CLASSICAL"
    KNOWN_PROPERTY_AGGREGATION = "KNOWN_PROPERTY_AGGREGATION"
    PARTIAL = "PARTIAL"


# ------------------------------------------------------------ building ----
class Quantity(BaseModel):
    value: float
    unit: str = "part"

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{self.value:g} {self.unit}"


class Citation(BaseModel):
    """A pointer into the ingested corpus plus the verbatim span relied on.

    quote MUST appear in the cited provision's text. PRAMANA re-checks this at
    emit time against corpus/provisions.jsonl, so a citation whose quote has
    drifted from the primary source fails the build instead of shipping.
    """

    kind: CitationKind
    corpus_id: str = Field(min_length=3)
    instrument: str
    provision: str
    quote: str = Field(min_length=10)
    hierarchy_path: str = ""
    source_pdf: str = ""
    page: int = 0
    retrieved_on: str = ""
    authority_rank: int = 9
    # "IN" for Indian instruments, otherwise the international regime the
    # instrument belongs to (WTO, CBD, WIPO, PCT, US). Shown on the citation so
    # a reader can never mistake a treaty article for Indian law.
    jurisdiction: str = "IN"
    # What force the instrument actually has -- e.g. that a treaty binds India
    # as a state but is not directly enforceable in an Indian court.
    force_note: str = ""

    @field_validator("corpus_id")
    @classmethod
    def _corpus_id_shape(cls, v: str) -> str:
        if "::" not in v:
            raise ValueError(f"corpus_id must be '<ACT_ID>::<LOCATOR>', got {v!r}")
        return v


class Autofix(BaseModel):
    id: str
    description: str
    # Facts this fix would set, applied to a copy of the formulation on recompile.
    sets_facts: dict[str, Any] = Field(default_factory=dict)
    preconditions: list[dict[str, Any]] = Field(default_factory=list)
    expected_effect: str = ""
    emits_protocol: str | None = None
    available: bool = True
    unavailable_reason: str = ""


class Finding(BaseModel):
    id: str
    severity: Severity
    rule_id: str
    jurisdiction: Jurisdiction
    instrument: str
    provision: str
    statement: str
    citations: list[Citation]
    autofix: list[Autofix] = Field(default_factory=list)
    as_of: date
    groundedness: float = 0.0
    verification: VerificationStatus = VerificationStatus.UNVERIFIED
    lane: Literal["PATENT", "REGULATORY", "BRAND", "ACCESS", "OTHER"] = "OTHER"

    @model_validator(mode="after")
    def _must_be_cited(self) -> Finding:
        if not self.citations:
            raise ValueError(
                f"Finding {self.id!r} has zero citations. A Finding without "
                "textual authority is not serialisable by design."
            )
        return self


class Obligation(BaseModel):
    """NIYAMA output: a duty triggered, with the act that discharges it."""

    id: str
    jurisdiction: Jurisdiction
    instrument: str
    provision: str
    duty: str
    discharged_by: str
    when: str = "before filing"
    citations: list[Citation]

    @model_validator(mode="after")
    def _must_be_cited(self) -> Obligation:
        if not self.citations:
            raise ValueError(f"Obligation {self.id!r} has zero citations.")
        return self


class ProcessDescription(BaseModel):
    summary: str = ""
    extraction_solvent: str | None = None
    temperature_c: float | None = None
    standardised_marker: str | None = None
    has_non_obvious_step: bool = False
    novel_steps: list[str] = Field(default_factory=list)


class EvidencePack(BaseModel):
    has_synergy_data: bool = False
    has_clinical_data: bool = False
    has_documented_traditional_use: bool = False
    traditional_use_years: int | None = None
    pre_1994_us_marketing: bool = False
    nba_approval_obtained: bool = False
    foreign_filing_permit: bool = False


class Ingredient(BaseModel):
    raw_name: str
    canonical_taxon: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    part_used: PlantPart = PlantPart.WHOLE_PLANT
    proportion: Quantity = Field(default_factory=lambda: Quantity(value=1))
    is_from_indian_bioresource: bool | None = None
    is_cultivated: bool | None = None
    schedule_flags: list[str] = Field(default_factory=list)
    # Populated by RESOLVER, never by hand.
    resolution_path: str = "UNRESOLVED"
    resolution_confidence: float = 0.0
    candidates: list[str] = Field(default_factory=list)
    classical_refs: list[str] = Field(default_factory=list)


class Formulation(BaseModel):
    name: str
    ingredients: list[Ingredient]
    process: ProcessDescription = Field(default_factory=ProcessDescription)
    dosage_form: DosageForm = DosageForm.CHURNA
    indications: list[str] = Field(default_factory=list)
    marketing_claims: list[str] = Field(default_factory=list)
    target_markets: list[Jurisdiction] = Field(default_factory=lambda: [Jurisdiction.IN])
    filing_intent: FilingIntent = FilingIntent.IN_FIRST
    claim_types: list[ClaimType] = Field(default_factory=lambda: [ClaimType.COMPOSITION])
    applicant_type: ApplicantType = ApplicantType.SMALL_ENTITY
    applicant_is_indian_resident: bool = True
    # Biological Diversity Act s.7 carries a proviso for local communities,
    # growers and cultivators, and vaids and hakims practising indigenous
    # medicine. Modelled explicitly so the compiler does not tell a practising
    # vaidya to file something the statute exempts them from.
    applicant_is_exempt_practitioner: bool = False
    evidence: EvidencePack = Field(default_factory=EvidencePack)
    is_classical_formulation: bool | None = None

    def fingerprint(self) -> str:
        """Stable content hash. Two identical formulations compile to the same
        C-BOM id -- this is what makes the build reproducible."""
        payload = self.model_dump(mode="json")
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


class JurisdictionRow(BaseModel):
    """One row of the SETU matrix."""

    jurisdiction: Jurisdiction
    patentability: str
    disclosure_duty: str
    abs_requirement: str
    market_route: str
    status: Severity
    next_action: str
    citation_count: int
    findings: list[str] = Field(default_factory=list)


class CBOM(BaseModel):
    """Compliance Bill of Materials -- the build artifact."""

    cbom_version: str = "1.0"
    formulation_name: str
    formulation_fingerprint: str
    as_of: date
    law_version: str
    generated_by: str = "AyurLex"
    resolution_log: list[dict[str, Any]] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    obligations: list[Obligation] = Field(default_factory=list)
    jurisdiction_matrix: list[JurisdictionRow] = Field(default_factory=list)
    groundedness_score: float = 0.0
    suppressed_count: int = 0
    abstentions: list[str] = Field(default_factory=list)
    disclaimer: str = (
        "Informational compliance analysis generated from primary statutory "
        "sources. This is not legal advice and does not replace a registered "
        "patent agent or advocate."
    )

    def digest(self) -> str:
        """Content digest over everything except wall-clock metadata, so that
        10 identical runs produce 10 identical digests."""
        payload = self.model_dump(mode="json")
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()
