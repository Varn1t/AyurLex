"""Jurisdictions -- the jurisdiction bridge.

An honest note about scope, because this is the module where it would be
easiest to cheat: the shipped corpus contains Indian primary sources only. So
It answers the four questions from the primary sources it actually has for
IN, and for every other jurisdiction it ABSTAINS explicitly, naming the corpus
it would need.

That is not a gap papered over -- it is the behaviour the design calls for.
Inventing a US or EU provision to fill a cell would be exactly the failure mode
the whole system exists to prevent, and a reader who catches one fabricated
cell discards everything else in the matrix. An abstention that says precisely what
is missing survives that check.

The cross-lane insight still lands in full, because it is an Indian-law
observation: the documented traditional use that Section 3(p) treats as
disqualifying is the same evidence base that traditional-use registration
routes consume. It labels that OPPORTUNITY on the IN row and marks the
destination-market rows as pending their own corpus.
"""
from __future__ import annotations

from core.schema import (
    Finding,
    Formulation,
    Jurisdiction,
    JurisdictionRow,
    Severity,
)
from compliance.facts import FactTable

ABSTAIN = "ABSTAIN — primary-source corpus for this jurisdiction not ingested"

# What each destination jurisdiction's row needs before it can be answered.
# Named concretely so this reads as a work item, not as a shrug.
REQUIRED_CORPUS = {
    Jurisdiction.US: "35 U.S.C. + FDA dietary-supplement/NDI pathway",
    Jurisdiction.EP: "EPC + the EU herbal-medicinal-product registration route",
    Jurisdiction.PCT: "PCT Articles and Regulations",
    Jurisdiction.JP: "Japanese Patent Act + kampo regulatory route",
}


def _india_row(findings: list[Finding], facts: FactTable) -> JurisdictionRow:
    ind = [f for f in findings if f.jurisdiction is Jurisdiction.IN]
    blockers = [f for f in ind if f.severity is Severity.BLOCKER]
    opps = [f for f in ind if f.severity is Severity.OPPORTUNITY]

    patentability = "Excluded as claimed" if any(
        f.rule_id.startswith("IN.PAT.S3") for f in blockers
    ) else "No exclusion rule fired on these facts"

    disclosure = (
        "Source and geographical origin of biological material must be "
        "disclosed in the specification"
        if facts.get("bioresource.uses_indian_biological_resource")
        else "Not triggered on these facts"
    )
    abs_req = (
        "NBA approval required before applying for IP based on Indian "
        "biological resources; benefit sharing is a condition of approval"
        if facts.get("bioresource.uses_indian_biological_resource")
        else "Not triggered on these facts"
    )
    market = (
        "Documented traditional use is an evidentiary ASSET here, not only a "
        "patent liability"
        if opps else "No traditional-use asset identified on these facts"
    )

    if blockers:
        status = Severity.BLOCKER
        action = f"Clear {len(blockers)} blocker(s); autofixes are attached"
    elif opps:
        status = Severity.OPPORTUNITY
        action = "Build the documented-use dossier"
    else:
        status = Severity.INFO
        action = "Proceed to drafting"

    return JurisdictionRow(
        jurisdiction=Jurisdiction.IN,
        patentability=patentability,
        disclosure_duty=disclosure,
        abs_requirement=abs_req,
        market_route=market,
        status=status,
        next_action=action,
        citation_count=sum(len(f.citations) for f in ind),
        findings=[f.rule_id for f in ind],
    )


def build_matrix(
    formulation: Formulation, findings: list[Finding], facts: FactTable
) -> list[JurisdictionRow]:
    rows = [_india_row(findings, facts)]

    for j in formulation.target_markets:
        if j is Jurisdiction.IN:
            continue
        need = REQUIRED_CORPUS.get(j, "primary sources for this jurisdiction")
        rows.append(
            JurisdictionRow(
                jurisdiction=j,
                patentability=ABSTAIN,
                disclosure_duty=ABSTAIN,
                abs_requirement=(
                    "India-side export duties still apply and are computed on "
                    "the IN row"
                ),
                market_route=(
                    "Candidate traditional-use route — the documented-use "
                    "dossier built for India is the input, subject to this "
                    "regime's own requirements"
                ),
                status=Severity.INFO,
                next_action=f"Ingest {need}, then re-run",
                citation_count=0,
                findings=[],
            )
        )
    return rows
