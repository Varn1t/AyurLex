# IP-SAKTI Sahayak — a grounded RAG assistant for AYUSH IP & regulatory compliance

A chat assistant over Indian IP and AYUSH law that will not answer without
citing the provision it relied on, and abstains when its corpus does not cover
the question. Underneath the chat sits a deterministic compliance compiler, so
it can do something an ordinary RAG bot cannot: when you describe a formulation
instead of asking a question, it **compiles** it and returns findings,
obligations and fixes for your own facts.

## Two ways in

**Ask a question** and you get an answer whose every sentence is tied to a
statutory span, with click-to-source back to the page of the source PDF:

```
you > can I advertise that my product cures diabetes

sakti [ASK] >
  This is a question about advertising a treatment claim. The governing text says:

  The Drugs and Magic Remedies (Objectionable Advertisements) Act, 1954,
  Section 3(d) — Prohibition of advertisement of certain drugs...:
  "(d) the diagnosis, cure, mitigation, treatment or prevention of any disease,
   disorder or condition specified in the Schedule..."

  sources:
    - Drugs and Magic Remedies Act, 1954, Section 3
      The_Drugs_And_Magic_Remedies...Act_1954.pdf p.2  [IN.DMR.1954::S3]
  groundedness 1.00
```

**Describe a formulation** and it stops being a lookup:

```
you > my churna contains amla, haritaki and bibhitaki and I want to patent it

sakti [COMPILE] >
  I compiled that as a formulation rather than answering it as a question.
  Resolved:  amla → Emblica officinalis · haritaki → Terminalia chebula
             bibhitaki → Terminalia bellirica
  3 blockers, 1 warning, 1 opportunity, 4 obligations
  Ask me to 'apply the fixes' and I'll recompile to prove which blockers clear.
```

And when it has no authority, it says so instead of improvising:

```
you > what is the EPO opposition period

sakti [ASK] >
  I don't have authority in the ingested corpus to answer that.
  Why: the question is about EPO law. The corpus covers Indian primary
  sources plus TRIPS, the CBD and Nagoya Protocol, the WIPO GRATK Treaty,
  the PCT, US FDA botanical-drug guidance and the WHO Ayurveda benchmarks
  — none of which govern it.
```

---

## The engine underneath

**In:** a formulation — ingredients in any Indian language or script, process,
dosage form, indications, marketing claims, target markets, filing intent.

**Out:** a Compliance Bill of Materials — every statutory duty triggered, every
blocker with the exact provision that causes it, the minimum change that clears
each blocker, and a jurisdiction matrix. Signed, versioned, diffable, and
reproducible byte for byte.

Chat is an interface. The engine is the product.

## Why it can be trusted, mechanically

The LLM is allowed to do three things: parse messy input into the typed schema,
phrase explanations of decisions the rule engine already made, and translate.
**It never decides a legal outcome.** Every legal outcome is a declarative rule
firing on resolved facts.

Four guarantees, each enforced in code rather than by convention:

| Guarantee | Where it is enforced |
|---|---|
| A finding without a citation cannot be serialised | `core/schema.py` — pydantic validator |
| A rule cannot cite a provision that was never extracted | `sutra/loader.py` — corpus binding at load |
| A rule's anchor must be verbatim in the source PDF | `sutra/loader.py` + `scripts/verify_provisions.py` |
| A number with no traceable source is stripped | `pramana/verify.py` — exact-match numeric path |

An unverified rule can match the facts and still emit nothing. That abstention
is printed in the report rather than hidden.

## Run it

```bash
pip install -r requirements.txt
ollama pull qwen2.5:1.5b        # or llama3.1 if you have a GPU

python samhita/ingest.py        # PDFs   -> corpus/provisions.jsonl  (3,094 provisions)
python samhita/priorart.py      # TKDL   -> corpus/tkdl_outcomes.jsonl (85 outcomes)
python samhita/schedules.py     # DMR    -> corpus/dmr_schedule.json  (54 conditions)

python cli.py serve             # web chat UI at http://127.0.0.1:8000
python cli.py chat              # same thing in the terminal
```

**Everything runs on your machine.** The LLM is Ollama, started automatically
if it is not already running — no API key, no network call, no data leaving the
box. That is not a convenience: it is the answer to the first question an
industry judge asks, which is why a manufacturer would paste a proprietary
formulation into someone else's API. With Ollama, they don't.

### The local model, and its honest cost

Measured on this machine (CPU-bound, no usable GPU), answering one legal
question from a retrieved extract:

| Model | Time | Notes |
|---|---|---|
| `qwen2.5:1.5b` | **14s** | default — best Indic coverage at this size |
| `llama3.2:3b` | 42s | |
| `llama3.1:8b` | 79s | best phrasing; use it if you have a GPU |

A 79-second pause in front of judges is a failed demo regardless of how well
the sentence reads, and the model here is only a phrasing layer over text the
retriever already found — so speed leads. Override with
`python cli.py serve --model llama3.1:latest` or `SAKTI_MODEL=...`.

Three things keep that latency out of the user's way:

1. **The model is warmed at boot**, so the first question does not pay the
   ~30s page-in.
2. **Citations stream first.** The authority arrives at ~0.1s, before a single
   word of prose. You can open the provision and read it while the model is
   still writing about it.
3. **The draft streams**, then is replaced by the verified text.

If Ollama cannot be reached at all, the assistant falls back to the extractive
backend — quotation of the retrieved provision, instantly, with no model. A
duller true answer beats an error page.

### The other commands

```bash
python cli.py serve                                # chat web UI
python cli.py chat                                 # chat in the terminal
python cli.py ask "can I patent a classical formulation"
python cli.py eval                                 # retrieval gold set
python cli.py compile <fixture> --autofix          # compile, fix, recompile, prove it clears
python cli.py compile <fixture> --html report.html # click-to-source report
python cli.py timetravel <fixture> 2002-01-01 2004-01-01 2026-08-31
python cli.py resolve गुडूची Giloy Kadukkai Brahmi
python cli.py reproduce <fixture> --runs 10        # same input -> same digest
python cli.py rules                                # verification status of every rule
python scripts/verify_provisions.py                # re-extract from PDFs, fail on drift
python -m pytest tests/ -q
```

## What the demo formulation produces

`fixtures/triphala_classical.json` — a classical three-fruit formulation, one
ingredient entered in Devanagari (आंवला), one as a Tamil common name
(Kadukkai), one as a Hindi trade name (Baheda), with two non-compliant
marketing claims and IN/US/EP as target markets.

- **4 blockers, 3 warnings, 1 opportunity, 3 info; 5 obligations.**
- All three ingredient names land on the correct binomials before any legal
  reasoning runs, because the statutory schedules are keyed on botanical names.
- `--autofix` clears all 4 blockers and proves it by recompiling.
- Compiling it ten times yields one C-BOM digest.

### The moment the whole pitch rests on

Two rules fire on the same facts and cite **the same provision** with opposite
consequences:

```
[BLOCKER]     IN.PAT.S3P.TK_EXCLUSION      [PATENT lane]
              Patents Act, 1970 — Section 3(p)
              ...excluded from patentability in India.

[OPPORTUNITY] REG.TRADITIONAL_USE_ASSET    [REGULATORY lane]
              Patents Act, 1970 — Section 3(p), read as evidence of traditional use
              The same documented traditional use that excludes this composition
              from patentability is an evidentiary asset in the regulatory lane.
```

A chatbot answers one question at a time and never notices. A compiler modelling
both lanes over one citation graph cannot miss it.
`tests/test_engine.py::test_same_provision_is_blocker_and_opportunity` asserts
it, so it cannot silently regress.

And the trade-off runs both ways: `--autofix` shows that applying
`ESTABLISH_SYNERGY` to clear the s.3(p) blocker also **removes** the
traditional-use opportunity. That is a strategic consequence the compiler
surfaces without being asked.

## Modules

| Module | Job | Where |
|---|---|---|
| **SAMHITA** | Prior-art and statute index: structure-aware extraction, authority ranks, BM25 | `samhita/` |
| **SUTRA** | Law as code — versioned, date-effective, declarative YAML | `sutra/` |
| **PRAMANA** | Citation verifier; an unverified sentence does not ship | `pramana/` |
| **NIYAMA** | Obligation checklist generator | in `sutra/engine.py` |
| **SETU** | Jurisdiction bridge, with explicit abstention | `setu/` |
| **VARGIKARANA** | Regulatory classification — which of the six categories a formulation falls into, and the very different IP posture each carries | `vargikarana/` |
| **RESOLVER** | Any script or language → canonical taxon | `core/resolver.py` |
| **RAG layer** | Hybrid retrieval, concept lexicon, grounded answers, chat | `rag/` |

### VARGIKARANA — classify before advising

SIH26045 puts classification before advice, and it is right to: the IP posture
of an Ayurvedic product is decided by which regulatory category it falls into,
not by what it contains. The same three herbs are unpatentable traditional
knowledge as a classical churna and a defensible invention as a standardised
phytopharmaceutical fraction — same plants, opposite advice.

So a compile leads with the category. Six tri-state facts decide it, the
categories are data in `data/formulation_classes.yaml` verified against the
corpus by the same gate as the rules, and a fact that is still open is *asked
about* rather than assumed — one question at a time, and only questions whose
answer would change the category. No model is involved.

### The polarity guard — where the citation gate cannot help

"Do I need NBA approval before filing?" has an answer whose entire content is
its polarity, and the citation gate cannot check polarity: it verifies that a
sentence is *carried by* spans of the cited provision, and "you do not need
approval" is built from the same words as the provision that requires it.

Measured on the local 1.5B model, three of four such questions came back
**inverted** — including "No, you do not need approval from the National
Biodiversity Authority", against a section headed *"Application for
intellectual property rights not to be made without approval"*, at
groundedness 1.00.

A lexical contradiction test does not work: every statutory span carries both
mandatory language and a proviso, so `shall` and `except` appear together in
all of them and discriminate nothing. So the model is taken out of this class
of question — `turns_on_polarity()` claims first-person duty questions and the
provision is quoted instead, which is duller and correct.

The lesson generalises, and it is worth saying out loud: **a groundedness score
is a traceability score, not a correctness score.**

### The retrieval stack, and the number that made us build it

Three retrievers fused with reciprocal rank fusion, then reranked on heading
match, authority rank and structural signals:

1. **BM25** — strong on exact statutory phrasing.
2. **LSA dense** — latent-semantic vectors learned from this corpus by truncated
   SVD over TF-IDF. Real semantics, trains in a second, no download, stays
   air-gapped. It is *not* a transformer embedding; BGE-M3 is a drop-in
   replacement at `DenseIndex.encode_query`.
3. **Taxon expansion** — the query goes through RESOLVER first, so a question
   about गिलोय also searches for *Tinospora cordifolia*.

That stack alone scored **2 / 9** on our first question set. The failure was not
tuning — it was register. "Can I patent my family formulation?" and "What are not
inventions" share no content words at all, and no embedding fixes that reliably.

So `data/legal_concepts.yaml` maps lay phrasing (including Hindi) to statutory
vocabulary, the provisions that govern it, and the SUTRA rules that decide it.
Matching is ordered-subsequence within a proximity window — "file abroad" must
match "file a patent abroad", but not "file" … forty words … "abroad". Concept
ids are corpus-verified at load exactly like rules: a concept pointing at a
provision that does not exist fails loudly rather than silently degrading search.
It can also pin a clause, so a question about traditional knowledge is answered
with s.3(p) rather than a recitation of all sixteen exclusions.

```
python cli.py eval

  recall@1            1.00  (17/17)
  recall@5            1.00  (17/17)
  abstention accuracy 1.00  (2/2)
```

**Read that honestly:** 17 items is a seed, not an evaluation, and the lexicon
was written while looking at these questions. The number that matters is the
same measurement on *held-out* questions, which is the next job (see below).

### Answer generation, and why adding an LLM adds no new way to be wrong

- **Ollama (default).** A local model that may only paraphrase the supplied
  extracts. Its output goes through PRAMANA exactly like a compiler finding.
- **Extractive (fallback).** Selects and quotes the operative clause. It cannot
  hallucinate because it never writes a sentence — everything it emits is a
  verbatim span or fixed connective text.
- **Claude (optional).** Same contract, if `ANTHROPIC_API_KEY` is set.

The gate has four exact-match paths, and each one was added because a real
model failed it during this build:

| Check | The failure that motivated it |
|---|---|
| Numbers and section refs | invented deadlines and penalties |
| **Quoted text must be verbatim** | the model wrote that s.3(p) *defines an invention as "…new, involves an inventive step…"* — words that appear nowhere in the section, presented inside quotation marks as if read off the page |
| **Named instruments must be in the extracts** | it suggested the "Plant Variety Rights Act" as an alternative — plausible, adjacent, not retrieved, and invisible to a numeric check because it has no digits |
| **The gate window equals the prompt window** | verifying against 5 hits when the model saw 3 let a weakly-ranked hit legitimise a cross-reference the model never had |

A fabricated *quotation* is a worse failure than a bad paraphrase: a paraphrase
the reader can weigh, a quotation they cannot. So quotation marks get exact
match, and the UI shows what was dropped and why rather than quietly deleting
it.

### Multilingual, and where the translation stops

The corpus is English. A question typed in Devanagari or Tamil therefore
retrieves almost nothing on its own, so an Indic-script query is **translated
to English for retrieval only** — never for the answer, never cited. The
concept lexicon carries Devanagari entries and is checked first, so
`क्या मैं गिलोय का पेटेंट करा सकता हूँ` is answered with no model in the loop at
all: the lexicon matches and the resolver turns गिलोय into *Tinospora
cordifolia*.

The answer then comes back in the user's language — under a **terminology
lock** that overrides it:

- Section numbers, rule numbers, form numbers, Act names and years are never
  translated.
- Terms of art (*prior art*, *specification*, *benefit sharing*) keep their
  English form with a short gloss. Machine-translating "prior art" into Tamil
  produces a phrase no examiner recognises, and a user who writes it on a form
  has been actively harmed by the translation.
- **Quoted statutory text stays in its original language.** A translated quote
  is a paraphrase, and a paraphrase is not authority.

### Where it refuses

- **Outside the corpus.** A question about US or EPO law that no Indian concept
  covers is abstained on by name, because retrieval would otherwise happily
  return some Indian section about oppositions and sound confident about it.
  This is checked *before* the definitional widening below, so "what is the EPO
  opposition period" does not slip through as a definition question.
- **Weak retrieval.** Nothing scoring high enough to rely on → abstain.
- **Contested taxon.** *Brahmi* returns both candidates and a warning, never a
  silent pick.

### Where it deliberately does not refuse

"What is Ayurveda?" used to abstain — while the corpus held 387 pages of AYUSH
reference material that answers it. Refusing the easiest question a user will
ask makes the whole assistant look broken. A definitional question now widens
to that background material, inverts the authority weighting (a request for
description wants the descriptive corpus, not "What are *not* inventions"), and
the answer is **labelled as background, not law**.

### SAMHITA — extraction that respects legal structure

Chunks split at **section** level and never below, so a proviso or an
*Explanation* can never be orphaned from its parent — a chunk holding only the
main clause produces a confidently wrong answer, because provisos invert
meaning. The Biological Diversity Act s.7 rule tests its proviso rather than
ignoring it, which is why a practising vaidya is not told to file an intimation
the statute exempts them from.

Three extraction problems in the shipped PDFs, each solved deterministically and
documented in `samhita/ingest.py`:

- **Footnotes read as sections.** India Code sets footnotes at 9pt at the foot
  of the page, renumbered per page. A linear extraction reads *"3. Cl. (a)
  omitted by Act 33 of 2021..."* as Section 3 and overwrites the real one. Font
  size and y-position separate them. Those footnotes are then kept as
  `amendment_notes` — they carry the commencement dates.
- **Substituted sections are missed.** A substituted section carries its
  amendment bracket first: `3[39. Residents not to apply...`. Without an
  optional prefix in the pattern, s.39 and s.43 vanish entirely.
- **Broken ToUnicode maps.** Em dashes and curly quotes both extract as U+FFFD.
  Repaired by rule; `text_raw` keeps the untouched extraction for audit.

Result: 157 of 163 Patents Act sections, 1,464 provisions across 14 PDFs.

### The prior-art layer is real outcome data

`About TKDL.pdf` ships the official annexure of patent applications **actually
revoked, refused or withdrawn** after TKDL prior art was cited against them.
`samhita/priorart.py` extracts 85 of those records with application numbers and
page provenance. When a formulation resembles one, the compiler cites an
application a patent office already killed on that ground — checkable evidence,
not an asserted verse citation.

### RESOLVER — multilingual that does work, not decoration

A vaidya types **गुडूची** or **Amrutha** or **Giloy** or **Guduchi** or
**gulvel**; all five land on *Tinospora cordifolia* before any legal reasoning
runs. Resolution order is exact → transliteration-normalised → fuzzy (propose
only) → escalate.

It refuses to guess where guessing would be wrong. **Brahmi** denotes *Bacopa
monnieri* in some regions and *Centella asiatica* in others, so it resolves to
neither and raises a warning with both candidates. That is not a limitation —
botanical synonymy is genuinely contested for several Ayurvedic drugs, and
surfacing the ambiguity is more correct than resolving it.

## What is deliberately not claimed

The corpus is **Indian primary sources, plus a named international layer** —
TRIPS, the CBD and the Nagoya Protocol, the WIPO GRATK Treaty, the PCT and its
Regulations, US FDA botanical-drug guidance, and the WHO benchmarks and
standard terminologies for Ayurveda. It is not a general law library. Any
jurisdiction outside that list prints `ABSTAIN — primary-source corpus for this
jurisdiction not ingested` and names exactly what it would need. Inventing a US
or EU provision to fill a cell would be the very failure the system exists to
prevent, and a judge who checks one fabricated cell discards everything else.

The national and international layers never mix in one answer. Retrieval picks
one layer and pre-filters to it, so an answer cannot quote Section 21 of the
Biological Diversity Act and Article 5 of the Nagoya Protocol as though they
were the same authority. The one exception is non-citable reference material,
which is labelled background and never cited as a rule.

Also out of scope, on purpose: drafting patent specifications (skeletons and
annexures, not claims), legal advice, and outcome prediction.

## Status

```
14/14 SUTRA rules VERIFIED against primary sources
13 citations re-verified directly from the source PDFs — no drift
123/123 tests passing
10/10 identical C-BOM digests
3,094 provisions from 29 instruments · 17/17 retrieval gold set · 2/2 abstentions
questions answerable in 11 languages · runs with zero network calls
```

## Next

1. **Grow the gold set to 300+ held-out items.** The current 17 were written
   alongside the concept lexicon, so 1.00 is a smoke test, not a score. Items
   written by someone who has not seen the lexicon are what make the number
   mean anything — plus the three ablation charts (dense-only vs hybrid vs
   hybrid+concepts; with and without the concept layer on lay phrasing).
2. **Rule breadth** — trade marks, GI, PPV&FR and the Drugs and Cosmetics ASU
   licensing route. The corpus for all four is already ingested; each needs the
   §PROVISION_VERIFICATION pass.
3. **PRAMANA upgrade** — swap the lexical coverage path in `entailment_score`
   for a cross-encoder NLI model and tune the thresholds on a labelled set.
4. **Graph layer** — the multi-hop cross-schedule query.
5. **KAVACH** — sealed mode and the on-prem compose file.

---

*Informational compliance analysis generated from primary statutory sources.
Not legal advice; does not replace a registered patent agent or advocate.*
