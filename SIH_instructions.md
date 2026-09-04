# SIH_instructions.md — project addendum for IP-SAKTI Sahayak

Read after the global instruction file. Everything here is specific to this repo.

## What this is

**SIH26045** (Ministry of Ayush / All India Institute of Ayurveda): *"IP-SAKTI
Sahayak — a multilingual, RAG-based (source-cited) AI assistant for Intellectual
Property and regulatory guidance in Ayurveda, across national and international
regimes."*

The problem statement verbatim, the coverage audit and the open gaps live in
[SIH26045-problem-statement-alignment.md](SIH26045-problem-statement-alignment.md).
Read it before proposing architecture — several obvious-sounding features are
already built (jurisdiction separation, the ABS helper, the
formulation-classification flow), and the doc's "Still open" section is the
honest list of what is not.

## Non-negotiables

These are the product, not preferences. Breaking one is a correctness failure,
not a style regression.

1. **Never emit an uncited legal assertion.** Every answer sentence is verified
   against spans of the retrieved provisions; unsupported sentences are dropped
   before display. If the whole draft fails, quote the provision instead.
2. **Abstain rather than improvise.** When the corpus has no authority, say so
   and name why. SIH26045 scores this explicitly. Never widen retrieval to make
   a refusal look like an answer.
3. **Never conflate jurisdictions.** India and international are separate
   retrieval layers, separated by a pre-filter and shown with a layer badge. An
   answer citing BDA s.21 and Nagoya Article 5 together is a bug.
4. **Cite the instrument's own unit.** Treaties number Articles, the PCT
   Regulations number Rules, Indian statutes number Sections, prose material has
   only pages. "Section 27 of TRIPS" is a wrong citation.
5. **State what force an instrument has.** Treaty records carry a `force_note`
   (e.g. TRIPS binds India as a WTO Member but is not directly enforceable in
   Indian courts). Do not let the model infer this.
6. **The compile and classification paths never call a model.** Findings come
   from the deterministic rule engine and categories from `vargikarana/`. Keep
   it that way — it is the demo's strongest claim and it returns in ~0.1s.
7. **A question whose whole answer is a polarity does not reach the model.**
   `turns_on_polarity()` claims first-person duty questions ("do I need", "must
   I") and quotes the provision instead. The citation gate verifies that a
   sentence is carried by the cited text; it cannot verify that the model kept
   the direction of the duty, and measured on the local model three of four
   such questions came back inverted. Never widen the gate to "fix" this and
   never let a paraphrase answer a duty question.
8. **Classify before advising.** The regulatory category decides the IP
   posture, so the compile leads with it. A missing fact is asked about, never
   assumed: tri-state facts exist so that "no disease claim made" and "nobody
   said" stay distinguishable.
9. **Nothing a user types is written to disk.** Sessions are in-process and
   ephemeral by design; it is the answer to "why would I upload my proprietary
   formulation?".

## Ground truth beats reasoning about this codebase

The corpus is real and the server is local, so **verify instead of inferring**:

```bash
python cli.py serve                # UI at http://127.0.0.1:8000
curl -s http://127.0.0.1:8000/api/health
python samhita/ingest.py           # rebuild corpus/ from Dataset/
python -m pytest -q                # 123 tests, all should pass
```

`corpus/` is generated and git-ignored — rebuild it, never hand-edit it.

A retrieval or answer-quality claim must be measured against the running server
before it goes in a document. Several questions that read as obviously fine
return wrong prose; the demo script's §5 is the measured list, and it exists
because guessing produced a wrong answer in front of a judge.

## Adding a source to the corpus

1. Put the PDF in `Dataset/` with a descriptive filename (global rule §5 — the
   name must identify it in a flat search).
2. Add a `Source(...)` entry to `SOURCES` in [samhita/ingest.py](samhita/ingest.py):
   `authority_rank` (1 statute, 2 rules, 3 notification, 4 case law, 5 official
   guidance, 6 pharmacopoeia/classical, 7 commentary), `jurisdiction`
   (`IN` or the regime: `WTO`, `CBD`, `WIPO`, `PCT`, `US`), `layout`
   (`gazette` | `kanoon` | `treaty` | `treaty_rules` | `prose`), `unit`, and a
   `force_note` for anything that is not directly enforceable Indian law.
3. Re-run the ingest and **check the provision count against the instrument's
   real structure.** TRIPS must yield 73 articles, the Nagoya Protocol 36, the
   PCT 69. A count that is suspiciously low usually means the parser is reading
   the table of contents — set `body_starts_page`. Where one PDF holds two
   instruments, as the India Code file does for the Drugs and Cosmetics Act and
   its Rules, split it into two Sources with `body_starts_page` /
   `body_ends_page` rather than letting the numbering restart mid-instrument.
4. Watch for two-column and two-up treaty typesetting. `_reading_order` in the
   ingester detects it per page; a document that yields zero provisions is
   almost always this or a deleted provision number.

## Adding or changing a formulation category

`data/formulation_classes.yaml` holds the six SIH26045 categories. It is data,
reviewable by a domain expert, and verified against the corpus by the same gate
as the rules: a category pointing at a provision that does not resolve fails
loudly.

- Categories are tested **in file order**, narrowest first, and the order is
  the legal order. Drug-or-not is settled before the purified-fraction
  question, because a phytopharmaceutical is a species of drug and a
  standardised extract in a face cream with no disease claim is a cosmetic.
- Every category must state all three postures — `requires`, `ip`, `abs`.
  `tests/test_classification.py` enforces it.
- Where the governing instrument is not ingested, set `uncited_authority` and
  say so in the answer. Do **not** pin a loosely related provision to make the
  category look cited.
- Pin a clause only when the clause body is substantive. A pin that yields
  under 150 characters falls back to the section and drops the pin, because
  s.3(h) reads "…means,— (i) in relation to Ayurvedic…" and the clause splitter
  cuts at that "(i)".

## Adding a concept

`data/legal_concepts.yaml` bridges lay phrasing to statutory vocabulary, and it
is the highest-leverage file in the repo — most "the model is bad" symptoms are
actually a missing `lay` phrase. It is curated data reviewable by a domain
expert who does not read Python, and the loader fails loudly if a concept points
at a provision that does not exist.

Include the abbreviation people actually type. A missing bare `"trademark"` and
a missing bare `"gi"` were the whole reason two regimes went unretrieved.

The layer a question is routed to is decided by the jurisdiction of the
concept's provisions, so a concept must not mix Indian and international
provisions in one entry.

## Sourcing primary texts

- **WIPO** has reorganised: the old `/export/sites/` paths 404. Treaty PDFs are
  at `wipo.int/documents/d/<system>/docs-en-texts-*.pdf`; find the exact link
  from the system's "legal texts" index page.
- **WIPO Lex** serves Indian legislation as *signed, time-limited* URLs. The
  signature expires, so re-derive the link from the WIPO Lex page each time.
- **India Code** PDFs sit behind unpredictable handles; the ministry or
  registry site (ipindia.gov.in, copyright.gov.in, fssai.gov.in) is usually the
  faster route.
- Record where each PDF came from — `docs/PROVISION_VERIFICATION.md` is the
  verification gate and treats provenance as part of correctness.
