# Promoting a SUTRA rule from UNVERIFIED to VERIFIED

A rule that has not been bound to primary-source text cannot emit a finding.
This is enforced in code, not by review discipline: `sutra/loader.py` refuses to
mark a rule `VERIFIED` unless every citation it declares resolves to a real
provision in the ingested corpus **and** every anchor phrase is a verbatim
substring of that provision. `sutra/engine.py` then refuses to emit findings
from an `UNVERIFIED` rule.

The failure mode this exists to prevent is specific and fatal: a hallucinated
section number in front of judges. A single one discredits every other claim on
the slide, including the correct ones.

## The checklist

For each rule, before it goes in:

**1. Locate the provision in a primary source.**
India Code, the Gazette, the relevant Ministry or authority site, or WIPO Lex.
Not a commentary, not a blog, not a model's recollection. For everything in the
current build the primary source is a PDF in `Dataset/`.

**2. Confirm it is ingested.**
```
python -c "from samhita.index import load_corpus; c=load_corpus(); print(c.get('IN.PATENTS.1970::S3')['text'][:400])"
```
If the provision is missing, fix `samhita/ingest.py` and re-run it. Do not
paste the text into the rule file by hand — the point of the anchor check is
that the corpus and the primary source are the same artefact.

**3. Copy the anchor verbatim.**
The `anchor` is the span the rule's reasoning actually leans on, copied
character for character out of the corpus record. Whitespace is normalised
before comparison (PDF extraction inserts line breaks mid-sentence), nothing
else is.

**4. Record the commencement date from the source, not from memory.**
Provision records carry `amendment_notes` extracted from the PDF's own
footnotes. Read the date off those:
```
python -c "from samhita.index import load_corpus; from samhita.ingest import commencement_dates; r=load_corpus().get('IN.PATENTS.1970::S3'); print(r['amendment_notes']); print(commencement_dates(r['amendment_notes']))"
```
For example, `effective_from: 2003-05-20` on `IN.PAT.S3P.TK_EXCLUSION` comes
from the footnote *"Ins. by s. 4, ibid. (w.e.f. 20-5-2003)"* on the page
carrying clauses (j)–(p). If no footnote establishes a date, leave
`effective_from: null` and say so in review — do not guess a date to make the
time-travel demo look better.

**5. Write at least two test cases.**
One fixture the rule must fire on, one it must not. A rule with no `test_cases`
cannot reach `VERIFIED`. `tests/test_engine.py::test_rule_declared_test_cases`
runs every declared case.

**6. Run the gates.**
```
python cli.py rules                    # all rules VERIFIED?
python scripts/verify_provisions.py    # re-extract from the PDFs, check drift
python -m pytest tests/ -q
```

**7. Record the review.**

| Field | Value |
|---|---|
| Rule id | |
| Provision | |
| Primary source (file / URL) | |
| Retrieved on | |
| Verbatim extract used as anchor | |
| Commencement date + the footnote it came from | |
| Reviewer initials | |

## What is deliberately *not* claimed

- **Corpus completeness.** The build claims verifiability of what it cites and
  explicit abstention where it lacks authority. It does not claim to cover any
  statute exhaustively. `python cli.py rules` prints the corpus size; the
  jurisdiction matrix prints `ABSTAIN` for every jurisdiction whose primary
  sources are not ingested.
- **Judgement calls.** Where two provisions conflict and the rule cannot
  resolve them, the correct output is a `WARNING` naming both and recommending
  professional review.
- **Legal advice.** Every report carries the disclaimer and the handoff to a
  registered patent agent or advocate.

## Rules currently VERIFIED

All 14 rules in `sutra/rules/` are bound to provisions extracted from the
shipped `Dataset/` PDFs and re-verified on every run. `verify_provisions.py`
re-opens the PDFs themselves rather than trusting `corpus/provisions.jsonl`, so
a corpus rebuild that silently moves text is caught before a report ships.
