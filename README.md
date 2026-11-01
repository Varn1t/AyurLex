# AyurLex — a grounded RAG assistant for AYUSH IP & regulatory compliance

A chat assistant over Indian IP and AYUSH law that will not answer without
citing the provision it relied on, and abstains when its corpus does not cover
the question. Underneath the chat sits a deterministic compliance compiler, so
it can do something an ordinary RAG bot cannot: when you describe a formulation
instead of asking a question, it **compiles** it and returns findings,
obligations and fixes for your own facts.

## Documentation

The written documentation is **generated, not committed** — every count in it
is read from the running system at build time rather than typed into the prose,
so a stale figure is impossible by construction and a checked-in copy would
only be a snapshot that disagrees with the code. Build it:

```bash
python sources/ingest.py                        # the corpus everything reads

python scripts/build_documentation_pdf.py       # the full technical record
python scripts/build_architecture_diagrams.py   # three 16:9 diagrams
```

- **Technical and evaluation documentation** — every module, every design
  decision and the failure that forced it, the full coverage audit. For the
  reader who digs.
- **Diagrams** land in `docs/` as `.svg` (sharp at any size in PowerPoint
  2016+ / Google Slides), `.png` (300 dpi) and `.pdf`:
  `architecture-system-layers` (the four layers, with the one amber box
  showing where a language model may touch anything),
  `architecture-request-flow` (the ASK and COMPILE paths side by side, with
  the three points where a request ends *before* the model is called),
  `architecture-trust-gates` (why a fabricated citation is structurally
  impossible, and the one failure the gate cannot catch).

## Two ways in

**Ask a question** and you get an answer whose every sentence is tied to a
statutory span, with click-to-source back to the page of the source PDF:

```
you > can I advertise that my product cures diabetes

ayurlex [ASK] >
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

ayurlex [COMPILE] >
  I compiled that as a formulation rather than answering it as a question.
  Resolved:  amla → Emblica officinalis · haritaki → Terminalia chebula
             bibhitaki → Terminalia bellirica
  3 blockers, 1 warning, 1 opportunity, 4 obligations
  Ask me to 'apply the fixes' and I'll recompile to prove which blockers clear.
```

And when it has no authority, it says so instead of improvising:

```
you > what is the EPO opposition period

ayurlex [ASK] >
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

| Guarantee                                               | Where it is enforced                                   |
| ------------------------------------------------------- | ------------------------------------------------------ |
| A finding without a citation cannot be serialised       | `core/schema.py` — pydantic validator               |
| A rule cannot cite a provision that was never extracted | `compliance/loader.py` — corpus binding at load          |
| A rule's anchor must be verbatim in the source PDF      | `compliance/loader.py` + `scripts/verify_provisions.py` |
| A number with no traceable source is stripped           | `citations/verify.py` — exact-match numeric path      |

An unverified rule can match the facts and still emit nothing. That abstention
is printed in the report rather than hidden.

## The web app

`ayurlex serve` opens a five-view app rather than a bare chat box:

| View | What it does |
|---|---|
| **Assistant** | Cited answers, streamed; click any citation to read the provision at its page |
| **Check a product** | A form for a formulation — ingredients in any script, claims, markets, evidence — compiled straight to findings, obligations and fixes (`POST /api/compile`, no regex parsing, no model) |
| **Library** | All 35 instruments, filterable by Indian / international / background, each opening to its table of contents (`/api/sources`) |
| **Connections** | Walks the knowledge graph between two instruments, every hop cited |
| **Get expert help** | The facilitator directory with each office's establishing provision, and a referral packet built from the session |

One session runs across all five, so a product checked in the form can be
fixed in the Assistant and handed off as a referral packet.

## Run it

```bash
pip install -e .                # installs the `ayurlex` command (editable: it reads data/ in place)
ollama pull qwen2.5:1.5b        # or llama3.1 if you have a GPU

python sources/ingest.py        # PDFs   -> corpus/provisions.jsonl  (3,491 provisions)
python sources/priorart.py      # TKDL   -> corpus/tkdl_outcomes.jsonl (85 outcomes)
python sources/schedules.py     # DMR    -> corpus/dmr_schedule.json  (54 conditions)

ayurlex serve                                # web chat UI at http://127.0.0.1:8000
ayurlex chat                                 # same thing in the terminal
```

Or with Docker (the image builds the corpus; Ollama stays on the host):

```bash
docker build -t ayurlex .
docker run --rm -p 8000:8000 ayurlex     # http://localhost:8000
```

With no reachable Ollama it still answers, extractively — it quotes the
provision instead of paraphrasing it.

**Everything runs on your machine.** The LLM is Ollama, started automatically
if it is not already running — no API key, no network call, no data leaving the
box. That is not a convenience: it is the answer to the first question any
manufacturer asks, which is why a manufacturer would paste a proprietary
formulation into someone else's API. With Ollama, they don't.

### The local model, and its honest cost

Measured on this machine (CPU-bound, no usable GPU), answering one legal
question from a retrieved extract:

| Model            | Time          | Notes                                   |
| ---------------- | ------------- | --------------------------------------- |
| `qwen2.5:1.5b` | **14s** | default — best Indic coverage at this size |
| `llama3.2:3b`  | 42s           |                                         |
| `llama3.1:8b`  | 79s           | best phrasing; use it if you have a GPU |

`qwen3.5:4b` is supported but not the default: on eight in-corpus questions
it got 2/8 answers past the citation gate against 8/8 for `qwen2.5:1.5b`. It
paraphrases further from the statute, so the gate withholds its drafts. The
default is the first installed model in `PREFERRED` (`rag/llm.py`).

A 79-second pause is a broken experience regardless of how well the sentence
reads, and the model here is only a phrasing layer over text the
retriever already found — so speed leads. Override with
`ayurlex serve --model llama3.1:latest` or `AYURLEX_MODEL=...`.

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
ayurlex serve                                # chat web UI
ayurlex chat                                 # chat in the terminal
ayurlex ask "can I patent a classical formulation"
ayurlex eval                                 # retrieval: gold, dev and held-out sets
ayurlex compile <fixture> --autofix          # compile, fix, recompile, prove it clears
ayurlex compile <fixture> --html report.html # click-to-source report
ayurlex timetravel <fixture> 2002-01-01 2004-01-01 2026-08-31
ayurlex resolve गुडूची Giloy Kadukkai Brahmi
ayurlex reproduce <fixture> --runs 10        # same input -> same digest
ayurlex rules                                # verification status of every rule

ayurlex graph --stats                        # knowledge graph: nodes, edges, problems
ayurlex path "Nagoya Protocol" "The Biological Diversity Act, 2002"
ayurlex plan "what does Nagoya require and what must I do in India" --dry-run
ayurlex facilitators                         # escalation directory + its verification
ayurlex escalate <fixture> --redact          # referral packet, recipe withheld

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

### The finding the whole design rests on

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

| Module                | Job                                                                                                                               | Where                  |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| **Sources**     | Prior-art and statute index: structure-aware extraction, authority ranks, BM25                                                    | `sources/`           |
| **Rules**       | Law as code — versioned, date-effective, declarative YAML                                                                        | `compliance/`             |
| **Citation gate**     | Citation verifier; an unverified sentence does not ship                                                                           | `citations/`           |
| **Obligations**      | Obligation checklist generator                                                                                                    | in `compliance/engine.py` |
| **Jurisdictions**        | Jurisdiction bridge, with explicit abstention                                                                                     | `jurisdictions/`              |
| **Classification** | Regulatory classification — which of the six categories a formulation falls into, and the very different IP posture each carries | `classification/`       |
| **Knowledge graph**   | Relational knowledge graph — 3,392 nodes over provisions, rules, concepts, taxa and treaties; multi-hop walks                    | `graph/`         |
| **Planner**       | Agentic orchestration — deterministic plan, typed tools, auditable trace                                                         | `planner/`             |
| **Escalation**     | Escalation to a human IP facilitator, with a referral packet                                                                      | `escalation/`           |
| **Resolver**    | Any script or language → canonical taxon                                                                                         | `core/resolver.py`   |
| **RAG layer**   | Hybrid retrieval, concept lexicon, grounded answers, chat                                                                         | `rag/`               |

### Classify before advising

Classification comes before advice, and it has to: the IP posture
of an Ayurvedic product is decided by which regulatory category it falls into,
not by what it contains. The same three herbs are unpatentable traditional
knowledge as a classical churna and a defensible invention as a standardised
phytopharmaceutical fraction — same plants, opposite advice.

So a compile leads with the category. Six tri-state facts decide it, the
categories are data in `data/formulation_classes.yaml` verified against the
corpus by the same gate as the rules, and a fact that is still open is *asked
about* rather than assumed — one question at a time, and only questions whose
answer would change the category. No model is involved.

### The knowledge graph, and why it adds no new way to be wrong

The questions an AYUSH founder actually asks are multi-hop, and retrieval is
single-hop by construction. *"India is a Party to the Nagoya Protocol — so what
do I have to do?"* has no single provision as its answer. The answer is a path:
Nagoya Article 5 is given domestic effect by Biological Diversity Act s.21;
s.6 is the control point an applicant meets; the rule that fires on your facts
cites it; and `OBTAIN_NBA_APPROVAL` clears that rule. A retriever scores those
four nodes independently and returns whichever wins. A graph walks the chain.

**3,392 nodes, 4,643 edges.** Almost every edge is *derived* rather than
authored, and therefore cannot be wrong: a provision belongs to the instrument
it was extracted from, a rule cites what its own anchor-verified YAML declares,
a concept governs the provisions listed against it, a provision cross-refers to
whatever section number appears in its own text.

The only authored edges are the thirteen cross-instrument ones in
`data/graph_links.yaml` — treaty obligation to the domestic provision that
gives it effect, a section and the later section that rewrote it, and the line
where the food regime hands over to the drug regime — and they are held to the
rule-loader gate: **both endpoints must
resolve in the corpus and every declared anchor must be verbatim in its
endpoint.** A link that fails is dropped and reported. `cli.py graph --stats`
prints the failures rather than hiding them.

Two design decisions are worth stating because both were wrong first:

- **Containers are never walked through.** An instrument holds all its
  provisions, so allowing a walk to pass through one makes any two sections of
  the Patents Act two hops apart via "is a provision of / contains" — true,
  useless, and it crowds out the real path. Membership is not a relationship.
- **A bare name means the instrument, not its first article.** "Nagoya
  Protocol" is a substring of the instrument title *and* of all 36 article
  labels; unranked lookup returned Article 1, and a walk from Article 1 finds
  nothing, because the relationship hangs off Article 5.

A walk that crosses the India/international boundary says so, every time.

### Agentic orchestration that is a plan, not an improviser

The plan is deterministic. The tools are deterministic. The composition is
deterministic. A model appears in exactly one place — inside a retrieval step,
phrasing an answer over spans it was handed, behind the same citation gate it
was already behind.

That is an unusual shape for an "agent" and it is the point. The ordinary
pattern hands a model a tool list and lets it choose what to call, in what
order, with what arguments, and then summarise across everything it collected.
Each of those four freedoms is a new way to be wrong, and the last is the
worst: a model summarising across steps can blend two jurisdictions into one
confident sentence.

What orchestration actually buys, concretely:

1. **Cross-layer questions without conflating the layers.** *"What does Nagoya
   require and what must I do in India?"* is one question with two answers
   under two authorities. Single-shot retrieval has to pick a layer — that is
   the pre-filter working correctly. The orchestrator splits the question at
   its own coordinator, runs each half as a separate retrieval, and presents
   them as separate sections with their own badges and citations.
2. **Describe-and-ask in one turn.** The compile runs first, because the
   category decides what the answer to the question even is.
3. **Relationship questions**, routed to the graph rather than the retriever.

The first version of (1) appended "under Indian law" to the same string and
sent it twice — and both copies came back from the international layer, because
a matched concept already decided the layer and a suffix cannot outvote it.
Two identical answers under two different badges is a worse failure than not
splitting at all: it *looks* like separation is working when it is not. So it
is a real decomposition, and a clause that will not decompose cleanly is asked
once and labelled with the layer it actually resolved to.

`MAX_STEPS` bounds the plan **before anything runs** — there is no loop
deciding whether to continue, so the plan is finite the moment it is built and
can be printed with `--dry-run`. Every run leaves a trace: the tool, why the
planner chose it, elapsed time, layer, groundedness, and what it cited. The UI
ships the trace in a collapsible block, because an agent whose steps cannot be
inspected is one you have to take on trust.

### Escalation to a human, with a brief they can act on

The system's own limits are the best signal that a person is needed. It already
knows when it abstained, when a blocker has no available fix, when a taxon was
genuinely ambiguous, and when a category's governing instrument is not in the
corpus. Those are the moments to hand over, and they are facts, not judgements
— **no model decides whether to escalate.**

`data/facilitators.yaml` holds 12 institutional routes, each carrying the
provision that establishes the office and a verbatim anchor, verified at load
exactly like a compliance rule: patent agent (Patents Act s.126), NBA (BDA s.8),
State Biodiversity Board (s.22), ASU licensing authority (D&C Rules r.154), GI
Registry (GI Act s.5), Trade Marks Registry (TM Act s.3), PPV&FR Authority,
Copyright Office, Designs Office, TKDL access cell, FSSAI (FSS Act s.4) — plus
the Ministry of Ayush facilitation desk, which carries **no citation and says
so**, because a ministry desk is administrative rather than statutory. FSSAI was
on that uncited list until the Food Safety and Standards Act, 2006 was ingested;
closing the gap was a matter of adding the source, never of relaxing the gate.

Contact details ship deliberately unset. "Take this to a patent agent
registered under Section 126" is durable and checkable; a phone number a
prototype invented is neither.

The packet states what was asked, what the system determined and on what
authority, what it could **not** determine and why, and what to put in front of
the facilitator. Its reference id is a content digest, so the same session
produces the same reference twice.

**Nothing is transmitted.** There is no outbound call, no queue, no ticket, and
nothing reaches disk unless the user names a file. Escalation is exactly where
a careless implementation breaks the privacy promise — "we'll forward this to
an expert for you" is how a proprietary formulation leaves the building.

`--redact` goes further and removes the product name, the ingredient names as
typed, and their resolved botanical names, throughout the whole packet — not
just from the line that obviously listed them. Redacting only the resolution
log is not redaction: a rule statement interpolates the resolved taxa, so the
recipe walks straight back in through the findings. The banner says precisely
what redaction does *not* remove, too: the findings still state the
formulation's legal characteristics, because a referral without those is no use
to anyone.

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

### What the groundedness number is, and the bug that made it meaningless

Groundedness is the **mean entailment of the sentences you are actually
shown**, measured against the spans of the provisions cited beneath them. What
the gate *removed* is reported next to it as a separate count, not folded in.

It used to be neither of those things, and the result was visible to any user:
the fraction of sentences clearing 0.55, divided by a denominator that also
counted the dropped ones. The gate **shows** a sentence at 0.34 but that score
only **counted** it at 0.55, so every sentence landing in between was displayed
and scored nothing. Measured on one question across three runs of the local
model, the same question returned **0.750, 0.200 and 0.000** — and the 0.000 run
still printed two sentences the gate had judged supported enough to print.

Two defects, compounding. A metric whose denominator includes sentences its own
numerator refuses to count is not measuring the answer; it is reporting a
pass-rate against an invisible stricter bar. And collapsing a continuous
measure to a binary threw away exactly what a confidence indicator exists to
carry — 0.54 and 0.00 are not the same situation, and the old formula reported
them identically.

The strict number is still computed and still available (`entailed_fraction`).
It just stopped being averaged into one figure that meant neither thing.

### It remembers the last three turns, and says what it assumed

"What are their pros and cons" has no noun in it. Retrieved cold it scores
nothing and the assistant abstains — on a question whose subject the previous
turn established perfectly well.

So a follow-up is resolved against the last **three substantive** questions.
Not the last three *messages*: a chain of pronouns would fill the window and
push the actual subject out of it, so follow-ups are skipped when choosing the
anchors. The expanded query carries the earlier questions **and the statutory
vocabulary of the concepts they matched** — which is the same register bridge
the concept lexicon provides within one turn, applied across turns. A user says
"GI", the statute says "geographical indication", and that substitution is what
lets the follow-up land on the provisions the previous answer cited.

```
you > What's the difference between a patent, GI, and trademark for an Ayurvedic product?
      groundedness 0.46 · 1 dropped by the gate

you > what are their pros and cons
      Reading that as a follow-up to: "What's the difference between a patent, GI…"
      cites GI Act s.9 · Trade Marks Act s.9 · Patents Act s.3    groundedness 0.83
```

Deciding *whether* a message is a follow-up turns on whether it names anything
at all, not on the pronoun alone. "Can I advertise that my product cures
diabetes" contains "that" and is eight words long, so on the pattern and the
length it read as a follow-up — which meant it could never be the anchor for
the real follow-up that came next, and a bare "why?" then retrieved cold and
abstained. It names advertising, a product, curing and diabetes; it is a
question in its own right. That test is `subject_tokens()`.

**The assumption is always printed.** Resolving a pronoun is a guess, and a
guess the user cannot see is one they cannot correct.

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
vocabulary, the provisions that govern it, and the compliance rules that decide it.
Matching is ordered-subsequence within a proximity window — "file abroad" must
match "file a patent abroad", but not "file" … forty words … "abroad". Concept
ids are corpus-verified at load exactly like rules: a concept pointing at a
provision that does not exist fails loudly rather than silently degrading search.
It can also pin a clause, so a question about traditional knowledge is answered
with s.3(p) rather than a recitation of all sixteen exclusions.

```
ayurlex eval

  recall@1            1.00  (17/17)
  recall@5            1.00  (17/17)
  abstention accuracy 1.00  (2/2)
```

**Read that honestly:** 17 items is a seed, not an evaluation, and the lexicon
was written while looking at these questions. The number that matters is the
same measurement on *held-out* questions, which is the next job (see below).

### Answer generation, and why adding an LLM adds no new way to be wrong

- **Ollama (default).** A local model that may only paraphrase the supplied
  extracts. Its output goes through the citation gate exactly like a compiler finding.
- **Extractive (fallback).** Selects and quotes the operative clause. It cannot
  hallucinate because it never writes a sentence — everything it emits is a
  verbatim span or fixed connective text.
- **Claude (optional).** Same contract, if `ANTHROPIC_API_KEY` is set.

The gate has four exact-match paths, and each one was added because a real
model failed it during this build:

| Check                                               | The failure that motivated it                                                                                                                                                                       |
| --------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Numbers and section refs                            | invented deadlines and penalties                                                                                                                                                                    |
| **Quoted text must be verbatim**              | the model wrote that s.3(p) *defines an invention as "…new, involves an inventive step…"* — words that appear nowhere in the section, presented inside quotation marks as if read off the page |
| **Named instruments must be in the extracts** | it suggested the "Plant Variety Rights Act" as an alternative — plausible, adjacent, not retrieved, and invisible to a numeric check because it has no digits                                      |
| **The gate window equals the prompt window**  | verifying against 5 hits when the model saw 3 let a weakly-ranked hit legitimise a cross-reference the model never had                                                                              |

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

Whoever translates faces the same four guards: the output must be in the right
script, must not be degenerate, must carry every section number and Act name
verbatim, and must carry every citation marker. Fail any one and the English is
returned with a note saying why, in the user's language. An answer the user
cannot check is worse than an answer in the wrong language.

#### Bhashini

Bhashini is the Government of India's national language infrastructure, and its
IndicTrans2 models are simply better at these pairs than anything that fits in
the local range — writing *into* Tamil is the job where `qwen2.5:1.5b` and
`mistral:7b` both collapse into repetition loops. So `rag/bhashini.py` routes
both directions through it when it is available.

It is the one path in this system that sends text off the machine, so it is
built to be visible and optional:

- **Off unless configured.** No `BHASHINI_USER_ID` / `BHASHINI_API_KEY`, no
  call — the local path is untouched and nothing leaves the box.
  `AYURLEX_BHASHINI=0` turns it off even when credentials are set.
- **The UI says which state it is in.** The status line reads *runs offline* or
  *translation via Bhashini*, and `/api/health` serves the same fact. A user
  deciding whether to describe a proprietary formulation is entitled to know
  before they type. `ayurlex bhashini` prints it, and `--probe` confirms
  the pipeline actually resolves.
- **Nothing is written to disk, in or out.** The no-disk rule is untouched.
- **No guard is relaxed for it.** Being the national infrastructure makes
  Bhashini a better translator, not a trusted one.
- **It fails soft.** An unreachable service falls back to the local model, and
  then to the untranslated query. A network hiccup is a degradation, never an
  error the user sees.

One implementation note, because it is the whole reason this works: a real NMT
system faithfully translates "Section 21", which is precisely what the
terminology lock forbids. So the immutable tokens and citation markers are
masked out before the text is sent and restored afterwards, which makes the
lock hold *by construction* rather than by inspection — and the guards still
run afterwards to catch a mask the service loses.

### Where it refuses

- **Outside the corpus.** A question about US or EPO law that no Indian concept
  covers is abstained on by name, because retrieval would otherwise happily
  return some Indian section about oppositions and sound confident about it.
  This is checked *before* the definitional widening below, so "what is the EPO
  opposition period" does not slip through as a definition question.
- **Weak retrieval.** Nothing scoring high enough to rely on → abstain.
- **Contested taxon.** *Brahmi* returns both candidates and a warning, never a
  silent pick.

### Scope guardrails

Checked before retrieval, in `rag/retriever.py`, and pinned by
`tests/test_guardrails.py`. Each refusal names its reason:

| Asked                                         | Response                                                            |
| --------------------------------------------- | ------------------------------------------------------------------- |
| Another country's law ("trademark in Japan")  | refuses, unless it names India or is about filing abroad from India |
| Off-topic ("capital of France")               | refuses when no word of the question appears in the corpus          |
| Clinical ("dose of brahmi for my child")      | refuses and points to a registered practitioner                     |
| Evading the law ("without getting caught")    | refuses; offers what compliance requires                            |
| Prompt injection ("ignore your instructions") | refuses before any model sees it                                    |

### Where it deliberately does not refuse

"What is Ayurveda?" used to abstain — while the corpus held 387 pages of AYUSH
reference material that answers it. Refusing the easiest question a user will
ask makes the whole assistant look broken. A definitional question now widens
to that background material, inverts the authority weighting (a request for
description wants the descriptive corpus, not "What are *not* inventions"), and
the answer is **labelled as background, not law**.

### Extraction that respects legal structure

Chunks split at **section** level and never below, so a proviso or an
*Explanation* can never be orphaned from its parent — a chunk holding only the
main clause produces a confidently wrong answer, because provisos invert
meaning. The Biological Diversity Act s.7 rule tests its proviso rather than
ignoring it, which is why a practising vaidya is not told to file an intimation
the statute exempts them from.

Three extraction problems in the shipped PDFs, each solved deterministically and
documented in `sources/ingest.py`:

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
- **One stray number truncates an instrument.** The Biological Diversity
  (Amendment) Act, 2023 runs to s.43, but s.38 substitutes three whole sections
  into the principal Act and quotes them: `"55B. Any authority or officer...`.
  A scan that accepts that as the next section then rejects the real ss.39–43
  for going backwards. Five provisions vanish and nothing says so. A forward
  jump is now provisional — if the next few candidates resume from where the
  mark already was, it was an interpolation — and where a run of them defeats
  that, the instrument declares its own last section.
- **Untitled short-title provisions.** `1. (1) This Act may be called...` has no
  rubric, so a pattern demanding a capital letter after the number drops s.1 —
  and with it the commencement clause, which is what says when any of the rest
  began to bind anyone.
- **Number and rubric on separate lines.** The FSSAI compendia set the number in
  its own column, so half the regulations read `1. Short title` and half read
  `2.  Definitions.-` in the same document. Ingested as plain gazette, the
  operative requirements for health supplements, nutraceuticals and novel foods
  were simply absent.
- **Schedule rows are not provisions.** A Schedule is a numbered list
  (`14. Vitamin B12 ... 1 µg`) and a line-based splitter cannot tell one from a
  regulation number. Letting them through grows a record cited as *Regulation
  14 of the FSS (Nutraceuticals) Regulations, 2016* whose text is a vitamin
  limit — a wrong citation. The Schedules are ingested as **pages** instead:
  retrievable, and correctly attributed.

Result: 157 of 163 Patents Act sections; 101 of 101 FSS Act sections;
3,491 provisions across 35 instruments.

### The prior-art layer is real outcome data

`About TKDL.pdf` ships the official annexure of patent applications **actually
revoked, refused or withdrawn** after TKDL prior art was cited against them.
`sources/priorart.py` extracts 85 of those records with application numbers and
page provenance. When a formulation resembles one, the compiler cites an
application a patent office already killed on that ground — checkable evidence,
not an asserted verse citation.

### The resolver — multilingual that does work, not decoration

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
jurisdiction outside that list prints `ABSTAIN — primary-source corpus for this jurisdiction not ingested` and names exactly what it would need. Inventing a US
or EU provision to fill a cell would be the very failure the system exists to
prevent, and a reader who catches one fabricated cell rightly discards
everything else.

The national and international layers never mix in one answer. Retrieval picks
one layer and pre-filters to it, so an answer cannot quote Section 21 of the
Biological Diversity Act and Article 5 of the Nagoya Protocol as though they
were the same authority. The one exception is non-citable reference material,
which is labelled background and never cited as a rule.

Also out of scope, on purpose: drafting patent specifications (skeletons and
annexures, not claims), legal advice, and outcome prediction.

## Status

```
14/14 compliance rules VERIFIED against primary sources
13 citations re-verified directly from the source PDFs — no drift
252/252 tests passing · 17/17 scope guardrails (foreign law, off-topic, clinical, evasion, injection)
10/10 identical C-BOM digests
3,491 provisions from 35 instruments · 17/17 retrieval gold set · 2/2 abstentions
held-out set (31 + 8 out-of-scope, never tuned against): recall@5 0.81 · recall@1 0.48 · 8/8 abstentions
3,392 graph nodes · 4,643 edges · 0 unverified curated links
12/12 escalation routes verified against their establishing provision
questions answerable in 11 languages · runs with zero network calls
Bhashini translation available, off unless configured
```

## Next

1. **Raise recall@1, and keep the held-out set honest.** `ayurlex eval`
   reports three sets: the original 17 (written with the lexicon, a smoke
   test), a dev set (held out once at 0.50 recall@5, then fixed against —
   now 0.93), and a fresh held-out set written before those fixes (0.81
   recall@5, 0.48 recall@1). The right section is usually in the top five but
   not first. Once the held-out misses are fixed against, that set becomes
   dev and a new one must be written. Target: 300+ items. Items
   written by someone who has not seen the lexicon are what make the number
   mean anything — plus the three ablation charts (dense-only vs hybrid vs
   hybrid+concepts; with and without the concept layer on lay phrasing).
2. **Rule breadth** — trade marks, GI, PPV&FR and the Drugs and Cosmetics ASU
   licensing route. The corpus for all four is already ingested; each needs the
   §PROVISION_VERIFICATION pass.
3. **Citation-gate upgrade** — swap the lexical coverage path in `entailment_score`
   for a cross-encoder NLI model and tune the thresholds on a labelled set.
4. **Grow the curated graph links.** Thirteen are anchor-verified; Madrid,
   Hague, Budapest and the EU THMPD route are the next four, and each needs its
   corpus ingested first.
5. **Sealed mode** and the on-prem compose file.

## License

Code is [MIT](LICENSE). The PDFs in `Dataset/` are third-party primary
sources under their publishers' own terms and are not covered by it.

## Author

Built by Varnit Kalra.

---

*Informational compliance analysis generated from primary statutory sources.
Not legal advice; does not replace a registered patent agent or advocate.*
