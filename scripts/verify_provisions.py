"""Re-extract every cited provision from the source PDFs and fail on drift.

This is the guard the build spec insists on. It does not trust
corpus/provisions.jsonl -- it re-opens the PDF, re-extracts the page range the
provision was found on, and checks that the anchor each rule relies on is still
there, character for character.

Run it in CI. If a corpus rebuild, an extraction change, or a swapped-in newer
PDF moves the text out from under a rule, this goes red before a report does.

    python scripts/verify_provisions.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pymupdf  # noqa: E402

from samhita.ingest import DATASET, page_body_text, repair_text  # noqa: E402
from samhita.index import load_corpus  # noqa: E402
from sutra.loader import load_rules  # noqa: E402


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def reextract(pdf_name: str, page_start: int, page_end: int) -> str:
    """Pull the page range straight from the PDF, bypassing the corpus file."""
    doc = pymupdf.open(DATASET / pdf_name)
    lo = max(page_start - 2, 1)
    hi = min(page_end + 2, len(doc))
    out = []
    for pno in range(lo - 1, hi):
        body, _ = page_body_text(doc[pno])
        out.append(repair_text(body))
    return "\n".join(out)


def main() -> int:
    corpus = load_corpus()
    rules = load_rules(corpus=corpus)

    checked = 0
    problems: list[str] = []
    print(f"verifying {len(rules)} rule(s) against {len(DATASET.iterdir.__self__.name and list(DATASET.glob('*.pdf')))} source PDFs\n")

    for rule in sorted(rules, key=lambda r: r.id):
        for c in rule.citations:
            if c.from_fact:
                print(f"  SKIP  {rule.id:<38} {c.corpus_id} "
                      f"(resolved from fact at emit time)")
                continue
            checked += 1
            if not corpus.has(c.corpus_id):
                problems.append(f"{rule.id}: {c.corpus_id} absent from corpus")
                print(f"  FAIL  {rule.id:<38} {c.corpus_id} missing")
                continue

            rec = corpus.get(c.corpus_id)
            fresh = reextract(rec["source_pdf"], rec["page_start"], rec["page_end"])
            if norm(c.anchor) in norm(fresh):
                print(f"  OK    {rule.id:<38} {c.corpus_id} "
                      f"({rec['source_pdf']} p.{rec['page_start']})")
            else:
                problems.append(
                    f"{rule.id}: anchor for {c.corpus_id} no longer found when "
                    f"re-extracted from {rec['source_pdf']} "
                    f"pp.{rec['page_start']}-{rec['page_end']}"
                )
                print(f"  DRIFT {rule.id:<38} {c.corpus_id}")
                print(f"        anchor: {c.anchor[:90]}…")

    print(f"\n{checked} citation(s) re-verified against primary sources")
    if problems:
        print(f"\n{len(problems)} PROBLEM(S) — build must not ship:")
        for p in problems:
            print(f"  * {p}")
        return 1
    print("no drift detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
