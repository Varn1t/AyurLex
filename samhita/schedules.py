"""Extract statutory schedules that the compiler screens against.

Right now: the Schedule to the Drugs and Magic Remedies (Objectionable
Advertisements) Act, 1954 -- the enumerated list of diseases, disorders and
conditions whose treatment may not be advertised. This is a closed statutory
list, so screening a marketing claim against it is a deterministic string
operation, not a judgement call an LLM should be making.

The list is read out of the shipped PDF, never typed in from memory.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "Dataset" / (
    "The_Drugs_And_Magic_Remedies_Objectionable_Advertisements_Act_1954.pdf"
)
OUT = ROOT / "corpus" / "dmr_schedule.json"

ITEM = re.compile(r"^\s*(\d{1,3})\.\s+([A-Z][^\n]{2,90}?)\s*$", re.M)
NOISE = re.compile(r"Indian Kanoon|indiankanoon|Objectionable Advertisements", re.I)


def extract() -> dict:
    doc = pymupdf.open(PDF)
    items: dict[int, str] = {}
    pages: set[int] = set()
    for pno, page in enumerate(doc):
        text = page.get_text()
        # The Schedule is the only place where a long run of bare numbered
        # single-line entries appears; body sections always run into prose.
        hits = [(int(n), t.strip()) for n, t in ITEM.findall(text)
                if not NOISE.search(t)]
        if len(hits) < 5:
            continue
        for n, t in hits:
            if n not in items and len(t.split()) <= 10:
                items[n] = t.rstrip(".")
                pages.add(pno + 1)
    ordered = [items[k] for k in sorted(items)]
    return {
        "instrument": "The Drugs and Magic Remedies "
                      "(Objectionable Advertisements) Act, 1954",
        "provision": "The Schedule",
        "corpus_ref": "IN.DMR.1954::SCHEDULE",
        "source_pdf": PDF.name,
        "pages": sorted(pages),
        "count": len(ordered),
        "items": ordered,
    }


def main() -> None:
    data = extract()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"extracted {data['count']} scheduled conditions "
          f"from pages {data['pages']} -> {OUT}")
    for i, it in enumerate(data["items"], 1):
        print(f"  {i:3d}. {it}")


if __name__ == "__main__":
    main()
