"""SAMHITA prior-art layer, built from the TKDL annexures in the dataset.

"About TKDL.pdf" ships the official annexure listing patent applications that
were actually revoked, refused, withdrawn or amended after TKDL prior art was
cited against them. That is real, checkable outcome data, and it is far better
demo evidence than an asserted verse citation: when a user's formulation looks
like one of these, we can point at an application that a patent office already
killed on exactly that ground.

Everything here is extracted, never authored. Each record keeps its page number
so the claim is click-to-source back into the PDF.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "Dataset" / "About TKDL.pdf"
OUT = ROOT / "corpus" / "tkdl_outcomes.jsonl"

# Application numbers wrap across column breaks: "2426/DEL/20 07".
APP_NO = re.compile(r"(\d[\d ]{0,5}?)\s*/\s*([A-Z]{2,7})\s*/\s*(\d[\d ]{2,5})")
ENTRY = re.compile(r"(?:^|\s)(\d{1,3})\.\s+(?=\d[\d ]{0,5}?\s*/\s*[A-Z]{2,7})")
OUTCOME = re.compile(
    r"(was revoked|revoked|was refused|refused|withdrawn|deemed to be withdrawn|"
    r"abandoned|claims? (?:were |was )?amended|amendment)", re.I
)
APPLICANT_MARK = re.compile(
    r"(M/[Ss]\b|Ltd\b|Limited\b|Inc\b|S\.P\.A|Council for Research|"
    r"University|/\s*(?:India|Italy|China|Japan|USA|Germany|France|Switzerland|"
    r"Korea|Spain|UK))"
)
STOPWORDS_TITLE = re.compile(r"^(and|of|the|a|an|for|in|to)$", re.I)


def squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def clean_app_no(m: re.Match) -> str:
    a = re.sub(r"\s+", "", m.group(1))
    b = m.group(2)
    c = re.sub(r"\s+", "", m.group(3))
    if len(c) == 2:            # "20 07" halves that lost their leading digits
        c = "20" + c if int(c) < 30 else "19" + c
    return f"{a}/{b}/{c}"


def parse_page(text: str, page_no: int) -> list[dict]:
    flat = squash(text)
    bounds = [m.start() for m in ENTRY.finditer(flat)]
    if not bounds:
        return []
    bounds.append(len(flat))
    rows = []
    for i in range(len(bounds) - 1):
        chunk = flat[bounds[i]:bounds[i + 1]]
        m = APP_NO.search(chunk)
        if not m:
            continue
        app_no = clean_app_no(m)
        tail = chunk[m.end():]
        # Title runs from the application number to the applicant column.
        am = APPLICANT_MARK.search(tail)
        title = squash(tail[: am.start()] if am else tail[:160])
        title = re.sub(r"[-–]{3,}", " ", title)
        # Cut the applicant column off the tail of the title: a numbered
        # applicant list ("1 . RATNAM"), a filing date, or an ALL-CAPS name run.
        for cut in (r"\s\d{1,2}\s*\.\s", r"\s\d{1,2}\s*-\s*[A-Z][a-z]",
                    r"\s(?:[A-Z]{3,}[.,]?\s){2,}", r"\sDr\.\s"):
            cm = re.search(cut, title)
            if cm and cm.start() > 15:
                title = title[: cm.start()]
        title = squash(re.sub(r"\b\d{1,2}-\s*[A-Z][a-z]{2}\s*-?\d{0,4}\b", " ", title))
        om = OUTCOME.search(tail)
        outcome = om.group(1).lower() if om else "cited"
        if len(title) < 12:
            continue
        rows.append(
            {
                "id": f"TKDL.OUT::{app_no.replace('/', '-')}",
                "application_no": app_no,
                "title": title[:220],
                "outcome": normalise_outcome(outcome),
                "outcome_text": squash(tail[om.start(): om.start() + 90]) if om else "",
                "source_pdf": PDF.name,
                "page": page_no,
                "authority_rank": 4,   # office decision / outcome record
                "kind": "PRIOR_ART_OUTCOME",
            }
        )
    return rows


def normalise_outcome(o: str) -> str:
    o = o.lower()
    if "revok" in o:
        return "REVOKED"
    if "refus" in o:
        return "REFUSED"
    if "withdraw" in o:
        return "WITHDRAWN"
    if "abandon" in o:
        return "ABANDONED"
    if "amend" in o:
        return "CLAIMS_AMENDED"
    return "CITED"


# Terms that make a TKDL outcome record match a formulation. Kept explicit so a
# match is explainable ("matched on: herbal, composition, diabetes").
def title_terms(title: str) -> set[str]:
    toks = re.findall(r"[a-zA-Z]{4,}", title.lower())
    return {t for t in toks if not STOPWORDS_TITLE.match(t)}


def build() -> list[dict]:
    doc = pymupdf.open(PDF)
    rows: list[dict] = []
    for i, page in enumerate(doc):
        rows.extend(parse_page(page.get_text(), i + 1))
    seen, out = set(), []
    for r in rows:
        if r["application_no"] in seen:
            continue
        seen.add(r["application_no"])
        r["terms"] = sorted(title_terms(r["title"]))
        out.append(r)
    return out


def main() -> None:
    rows = build()
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter

    tally = Counter(r["outcome"] for r in rows)
    print(f"extracted {len(rows)} TKDL outcome records -> {OUT}")
    for k, v in tally.most_common():
        print(f"  {k:16s} {v}")


if __name__ == "__main__":
    main()
