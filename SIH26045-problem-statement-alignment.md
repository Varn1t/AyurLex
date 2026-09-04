# SIH26045 — problem statement, and where this build stands against it

The official problem statement, retrieved from the SIH 2026 catalogue, plus a
line-by-line audit of what the repo now covers, what it does not, and the exact
sources for the gaps.

---

## 1. The problem statement, verbatim

| Field | Value |
|---|---|
| **PS ID** | **SIH26045** |
| **Title** | IP-SAKTI Sahayak — a multilingual, RAG-based (source-cited) AI assistant for Intellectual Property and regulatory guidance in Ayurveda, across national and international regimes. |
| **Organisation** | Ministry of Ayush |
| **Department** | **All India Institute of Ayurveda** |
| **Category** | Software |
| **Theme** | Listed as "Toys & Games" in the third-party catalogue — this is a scraping artefact (the neighbouring rows are shifted too). Confirm the real theme on `sih.gov.in` before printing it anywhere. |

**Dataset link (as given in the PS):** "The corpus can be assembled from open,
authoritative public sources; representative examples: Traditional Knowledge
Digital Library (TKDL) — tkdl.res.in; Statutes & rules — India Code,
indiacode.nic.in; IP India public databases (patents/InPASS, trade marks,
designs, GI Registry) — ipindia.gov.in"

### Background (verbatim)

> Ayurveda rests on a vast corpus of codified and community-held traditional
> knowledge (TK) and on therapeutics derived from plant, microbial and animal
> sources. Protecting and commercialising an Ayurvedic product means navigating
> several overlapping regimes at once: patents, geographical indications (GI),
> trademarks, copyright, designs, trade secrets and plant-variety rights; the
> Access-and-Benefit-Sharing duties that flow from India's sovereignty over its
> biological resources; and the drug-regulatory framework that decides whether a
> formulation is a classical medicine, a proprietary medicine, a new drug, a
> phytopharmaceutical, a food or a cosmetic. Practitioners, researchers, AYUSH
> startups and MSMEs and cultivators routinely struggle with this. The result is
> twofold: legitimate Ayurvedic innovation is under-protected and
> under-commercialised, while India's traditional knowledge remains exposed to
> misappropriation abroad. Recent shifts — the 2024 patent and biodiversity
> rules, the WIPO Treaty on Genetic Resources and Associated Traditional
> Knowledge (2024) and a fast-moving advertising and regulatory landscape — make
> authoritative, plain-language guidance more necessary than ever, yet no such
> tool exists for the AYUSH community.

### Description (verbatim, condensed to its operative requirements)

> The assistant answers IPR questions specific to Ayurveda with accuracy, source
> citation and jurisdictional clarity, keeping the national and the international
> layers distinct **through an explicit jurisdiction switch so that answers are
> never conflated**. Because intellectual property for an Ayurvedic product is
> inseparable from how the product is regulated, the assistant **first helps
> classify the formulation**. It asks the minimum clarifying questions to
> determine whether the product is a classical/generic medicine (formulation and
> method drawn from a First-Schedule authoritative text), a patent-or-proprietary
> medicine, a new or non-classical drug requiring proof of safety and
> effectiveness, a phytopharmaceutical, an Ayurveda-Aahar / nutraceutical, or a
> cosmetic — and then states what each category requires and its very different
> IP and ABS posture. […] It must cite the specific statute, rule, treaty article
> or record it relies on; clearly state that it provides information and not
> legal advice; keep its corpus current as the law changes; and **never fabricate
> authority**.

**National coverage required:** Patents Act (and the 2024 Rules); GI, Trade
Marks, **Designs**, **Copyright** and Plant-Variety regimes; Biological
Diversity Act **as amended in 2023, with the 2024 Rules**; and the allied drug,
advertising, labelling and food/cosmetic regimes — Drugs and Cosmetics Act,
Drugs and Magic Remedies Act, and the **FSSAI Ayurveda-Aahar regulations**.

**International coverage required:** TRIPS; the Convention on Biological
Diversity and the Nagoya Protocol; the WIPO GRATK Treaty; the PCT; the **Madrid**
and **Hague** systems; the **Budapest Treaty**; and the **herbal-product
market-access regimes of key export markets**.

### Expected solution (verbatim, operative list)

> A deployable, multilingual assistant built on retrieval-augmented generation
> grounded in a curated, **version-tracked** corpus of statutes, rules, treaties,
> pharmacopoeial standards, registry records and case law, so that every answer
> is traceable to a source and hallucination is minimised. The solution should
> provide: a **jurisdiction toggle** (India vs international) with the two
> answer-sets kept visibly separate; **routing across IP types** together with
> the **formulation-classification flow**; an **ABS-compliance helper** and a
> **TKDL / prior-art pointer**; mandatory source citations with a **confidence
> indicator** and a path to **escalate to a human IP facilitator**;
> **multilingual delivery** (leveraging national language infrastructure such as
> **Bhashini**); and guardrails, a standing 'information, not legal advice'
> disclaimer and privacy, audit and security aligned to the **Digital Personal
> Data Protection** regime and to recognised AI-application standards. A
> **relational knowledge graph** and **agentic, multi-source orchestration**
> deepen multi-step reasoning and the build can be **staged** — a
> citation-grounded retrieval MVP first, then the graph and agentic layers, then
> paid-source connectors and the full multilingual and voice experience.

> The output should be evaluable on **answer accuracy, citation correctness, safe
> abstention on out-of-scope or uncertain queries and multilingual quality**.

**Read that last sentence twice before the demo.** Safe abstention is a *scored
criterion*, not a limitation to apologise for. The deliberate refusal is a
feature the PS asks for by name.

---

## 2. Corpus coverage — measured

**3,094 provisions across 29 instruments** (was 1,712 across 14). Counts are
from `corpus/provisions.jsonl`; rebuild with `python samhita/ingest.py`.

By jurisdiction: India 1,990 · WHO 684 · PCT 213 · CBD 79 · WTO 73 · US 34 ·
WIPO 21.

### India layer — 1,990 provisions

| Instrument | Provisions | PS requires it |
|---|---|---|
| Drugs and Cosmetics **Rules**, 1945 | 469 | ✅ yes |
| Drugs and Cosmetics **Act**, 1940 | 70 | ✅ yes — **split out this pass** |
| Patents Act 1970 | 175 | ✅ yes |
| Trade Marks Act 1999 | 168 | ✅ yes |
| Patents Rules 2003 | 134 | ✅ yes |
| Copyright Rules 1957 | 108 | ✅ yes |
| **Copyright Act 1957** (to Act 7 of 2017) | 108 | ✅ **added this pass** |
| **Designs Act 2000** | 48 | ✅ **added this pass** |
| Plant Varieties & Farmers' Rights Act 2001 | 98 | ✅ yes |
| GI Act 1999 | 87 | ✅ yes |
| Biological Diversity Act 2002 | 64 | ⚠️ pre-2023 text |
| **Patents (Amendment) Rules 2024** | **46** | ✅ **added this pass** |
| Drugs and Magic Remedies Act 1954 | 18 | ✅ yes |
| TKDL documentation (rank 6, background) | 97 | ✅ yes |
| AYUSH primers — Ayurveda/Unani/Siddha/Sowa-Rigpa (rank 6) | 290 | ✅ yes |

### International layer — 420 provisions

| Instrument | Jurisdiction tag | Provisions | Source |
|---|---|---|---|
| Regulations under the PCT | `PCT` | 144 | wipo.int |
| **TRIPS Agreement** | `WTO` | 73 Articles | wto.org |
| **Patent Cooperation Treaty** | `PCT` | 69 Articles | wipo.int |
| **Convention on Biological Diversity** | `CBD` | 43 Articles | cbd.int |
| **Nagoya Protocol** | `CBD` | 36 Articles | cbd.int |
| **FDA Botanical Drug Development guidance** | `US` | 34 pages | fda.gov |
| **WIPO GRATK Treaty 2024** | `WIPO` | 21 Articles | wipo.int |

### WHO layer — 684 provisions

| Instrument | Jurisdiction tag | Provisions | Rank |
|---|---|---|---|
| WHO International Standard Terminologies on Ayurveda | `WHO` | 594 | 6 — background, not citable as law |
| WHO Benchmarks for the Practice of Ayurveda | `WHO` | 87 | 5 — official guidance |
| Panchakarma standardisation review | `IN` | 10 | 7 — commentary |
| Ayurveda/allopathy integration paper | `WHO` | 3 | 7 — commentary |

Background material is deliberately **exempt from the jurisdiction pre-filter**:
it is never cited as authority for a legal answer, and the WHO standard
terminology has to be able to answer "what is vamana?" whichever layer the
conversation is in.

Every article count matches the instrument's real structure — TRIPS has 73
articles, the Nagoya Protocol 36, the PCT 69. That is the check that the parser
is reading the treaty and not the table of contents.

### Still missing — with the exact source to fetch

| Gap | PS names it | Where to get it |
|---|---|---|
| Designs **Rules** 2001 (the Act is now ingested) | yes, explicitly | ipindia.gov.in → Designs resources |
| **Biological Diversity (Amendment) Act 2023** | yes, explicitly | India Code / MoEFCC gazette, in force 1 Apr 2024 |
| **Biological Diversity Rules 2024** | yes, explicitly | MoEFCC gazette, notified 22 Oct 2024, in force 22 Dec 2024 |
| **FSSAI Ayurveda-Aahar regulations** | yes, explicitly | fssai.gov.in — note it serves an interstitial page to non-browser clients, so the PDF must be fetched from a browser session |
| **Madrid Protocol** (marks) | yes | wipo.int madrid legal texts |
| **Hague Agreement** (designs) | yes | wipo.int hague legal texts |
| **Budapest Treaty** (micro-organism deposits) | yes | wipo.int |
| **EU herbal market access** (Directive 2004/24/EC, THMPD) | "key export markets" | eur-lex.europa.eu |
| Case law | "…and case law" | indiankanoon / SCC |
| Registry records (InPASS, GI Registry) | yes | ipindia.gov.in |

The four WIPO texts and the Indian amendments were attempted this pass; WIPO has
reorganised its document paths (the old `/export/sites/` URLs 404) and India Code
serves its PDFs behind unpredictable handles. The PCT was obtained from
`wipo.int/documents/d/pct-system/docs-en-texts-pct.pdf`, and the same
`/documents/d/<system>/` pattern is the place to look for Madrid and Hague.
WIPO Lex serves Indian legislation as signed, time-limited URLs — that is how the
Patents (Amendment) Rules 2024 was obtained, and the signature expires, so the
link must be re-derived from the WIPO Lex page each time.

---

## 3. Feature audit against the expected solution

| PS requirement | Status | Detail |
|---|---|---|
| Citation-grounded RAG, never fabricate authority | ✅ **done** | Every sentence verified against retrieved spans; unsupported sentences dropped before display; extractive fallback quotes the provision when the draft fails the gate |
| **Safe abstention on out-of-scope queries** | ✅ **done** | Names the reason and the regime; no model call at all when out of corpus |
| Mandatory source citation to the specific provision | ✅ **done** | Click-to-source opens the provision at the cited page with the relied-on span highlighted |
| **Confidence indicator** | ✅ **done** | Groundedness score on every answer |
| **Jurisdiction separation, "never conflated"** | ✅ **done this pass** | India and international are retrieved as separate layers with a pre-filter, and the answer carries a visible layer badge |
| Jurisdiction **toggle** (a user control) | ⚠️ **partial** | Routing is automatic and visible; there is no manual switch yet |
| Routing across IP types | ✅ **done** | 20 curated concepts route patents / GI / trade marks / plant variety / ABS / advertising |
| ABS-compliance helper | ✅ **done** | The compiler raises BDA s.6(1), s.7, s.21 with obligations and fixes |
| TKDL / prior-art pointer | ✅ **done** | TKDL corpus + a TKDL adverse-outcome rule |
| Treaty force stated, not blurred | ✅ **done this pass** | Each treaty record carries a note — e.g. TRIPS "binds India as a WTO Member, not directly enforceable in Indian courts" |
| **Formulation-classification flow** | ✅ **built this pass** | `vargikarana/` classifies into all six PS categories — classical / patent-or-proprietary / new drug / phytopharmaceutical / Ayurveda-Aahar / cosmetic — from six tri-state facts, asks only the questions that would change the answer, and states each category's regulatory, IP and ABS posture with the provisions that define it. Data lives in `data/formulation_classes.yaml`, verified against the corpus by the same gate as the rules |
| Classification asks the *minimum* clarifying questions | ✅ done | Facts are read from what the user already said; only a genuinely open fact is asked about, one at a time, and a bare yes/no answers it |
| Escalate to a human IP facilitator | ❌ not built | |
| Multilingual delivery | ⚠️ partial | Hindi/Devanagari detection, translation and taxon resolution work; Bhashini not integrated |
| Version-tracked corpus | ⚠️ partial | Every record carries `retrieved_on`, `effective_from/to` and amendment notes; no diffing across corpus versions |
| DPDP / privacy / audit | ⚠️ partial | Sessions are in-process and ephemeral, nothing written to disk — a strong privacy story, but no audit log |
| "Information, not legal advice" disclaimer | ✅ done | Standing in the composer footer |
| Knowledge graph, agentic orchestration | ❌ not built | The PS explicitly allows staging these after the MVP |
| Paid-source connectors with logged consent | ❌ not built | Also explicitly a later stage |

---

## 4. What was fixed this pass, and what is still wrong

### Fixed

1. **Multi-regime comparison questions.** "What's the difference between a
   patent, GI, and trademark for an Ayurvedic product?" scored **groundedness
   0.00** with three sentences stripped by the gate, citing only the Patents
   Act. Cause: the concept lexicon had no lay phrase for bare `"trademark"` or
   bare `"GI"`, so only the traditional-knowledge concept matched and retrieval
   was boosted onto the Patents Act alone. Now matches all three concepts and
   cites Trade Marks s.9, GI s.9 and Patents s.3 together — **g 0.00 → 0.571**.

2. **"Can I trademark the name of my ayurvedic churna?"** used to **abstain**
   despite 168 ingested sections of the Trade Marks Act — same root cause. Now
   answers from s.9 and s.11, **g 0.667**.

3. **International questions were unanswerable by construction.** The corpus
   was Indian-only, so anything about the US, WIPO or a treaty abstained. The
   PS requires international coverage, so this was a real gap and not honest
   restraint. 420 international provisions added.

4. **Treaty articles were being mis-cited.** The citation builder hardcoded
   `"Section {n}"`, which would render TRIPS Article 27 as "Section 27" — a
   wrong citation, the one thing the system may never emit. Records now carry
   their own unit (Article / Rule / Section / page).

5. **Two-column treaty PDFs ingested as nothing.** The page extractor sorted
   lines by vertical position only, which interleaves the columns of the UN
   typesetting — and the article number, set on its own line, was being deleted
   as a page number. The Nagoya Protocol yielded **0** provisions; it now yields
   its true **36**.

### Fixed this pass — the polarity guard

**The inverted-polarity bug is closed.** Three of four measured "do I need X?"
questions came back from the local 1.5B model with the polarity inverted:

| Question | The model said | The provision says |
|---|---|---|
| Do I need NBA approval before applying for a patent? | "No, you do not need approval" | s.6(1): "No person shall apply for any intellectual property right … **without obtaining the previous approval** of the National Biodiversity Authority" |
| Do I need permission before filing outside India? | "No … however you must comply with Section 39" | s.39: "**No person resident in India shall**, except under the authority of a written permit …" |
| Do I need FDA approval to sell in the US? | "No, you do not need FDA approval" | FDA guidance p.8: "Any person who wishes to market a new drug in the United States **must submit an NDA and obtain Agency approval prior to marketing**" |

Each of those passed the citation gate with **groundedness 1.00**, because the
gate verifies that a sentence is *carried by spans of the cited provision* — and
"you do not need approval" is built from the same words as the provision that
requires it. **The gate cannot check polarity.**

A lexical contradiction test was tried first and does not work: every statutory
span carries both mandatory language and a proviso, so `shall` and `except`
appear together in all of them and discriminate nothing. Measured across five
such questions, the mandatory/exemption signature was identical every time.

So the model is taken out of this class of question. `turns_on_polarity()` in
[rag/answer.py](rag/answer.py) claims first-person duty questions — "do I need",
"must I", "am I required", "is prior approval required" — and routes them to the
extractive answerer, which quotes the provision. The UI says so: *"Quoted, not
paraphrased — this question turns on whether a duty applies."*

The pattern is deliberately first-person. *"What does the Nagoya Protocol
require?"* asks what a duty **contains**, which the model answers well
(groundedness 1.00) and keeps. *"Can I patent X?"* is answered by a
prohibition, which the model also gets right. 21 tests in
[tests/test_polarity_guard.py](tests/test_polarity_guard.py) pin which
questions the guard claims and which it must leave alone.

**Keep saying the honest version of this**: a high groundedness score is a
*traceability* score, not a correctness score. It says every sentence is tied to
the cited text; it never said the model kept the direction of the duty.

### Also fixed this pass

- **The Drugs and Cosmetics Act and its Rules were one instrument.** That
  single India Code PDF holds both, and section numbering restarts at the
  boundary — so the Act's own definitions, including s.3(h) "patent or
  proprietary medicine" and s.3(aaa) "cosmetic", were swallowed into a record
  labelled **"Section 38"**, and every rule of the 1945 Rules was cited as a
  *section* of the Act. Both are wrong citations. They are now two instruments
  (70 sections, 469 rules) split on a page range, and Rule 158 is cited as
  "Rule 158". The classification flow depends on citing s.3(h) correctly, so
  this was a prerequisite rather than a tidy-up.
- **Clause labels longer than two letters could not be pin-cited.** The clause
  index capped at `[a-z]{1,2}`, so the Act's `(aaa)` and `(aab)` definitions
  were unreachable. Widened to three.
- **Sub-chunked provisions lost their unit.** A long rule split into parts came
  back labelled "Section", so `Rule 158#part2` would have been cited as a
  section.
- **Three more instruments were citing the wrong unit.** The Patents Rules
  2003, the Copyright Rules 1957 and the Patents (Amendment) Rules 2024 all
  predate the `unit` field, so 288 provisions were being cited as "Section 71
  of the Patents Rules, 2003". Now "Rule 71".
  [tests/test_citation_units.py](tests/test_citation_units.py) turns this into
  a corpus invariant — an instrument titled *Rules* must number Rules, a treaty
  must number Articles, an Act must number Sections, no instrument may mix
  units, and the id prefix must match the label the reader is shown — so a
  Source registered without its unit fails the suite rather than shipping a
  wrong citation.
- **A pinned clause that yields a stub now falls back to the section.** s.3(h)
  reads "patent or proprietary medicine means,— (i) in relation to
  Ayurvedic…", so the clause body is cut at that "(i)" and the pin quoted 45
  characters that said nothing. A pin producing under 150 characters now quotes
  the section and drops the pin from the label rather than citing a clause it
  is not really quoting.

### Still open — honest list

- **Temporal filtering is scaffolding, not a guarantee.** `in_force()` checks
  `effective_from` / `effective_to`, and the pre-filter runs before scoring as
  the design requires — but **0 of 3,094 records carry either field**, so it
  currently passes everything. 1,379 records do carry `w.e.f.` dates in their
  amendment notes, and `commencement_dates()` exists to parse them, but wiring
  it up naively would be *worse* than leaving it: notes are collected per page,
  so a footnote dating one inserted clause would date the whole provision, and
  an as-of query for 2004 would exclude the whole of Patents Act s.3, in force
  since 1970. Closing this needs provision-level commencement data. The PS asks
  for a "version-tracked" corpus that "keeps current as the law changes", so
  this is a real partial, and it is written up in the function's own docstring
  so the next reader does not mistake the scaffolding for a working filter.
- **Ayurveda-Aahara is classified but not cited.** The category is identified
  and its posture stated, and it declares in the answer that the FSSAI
  regulation is not in the corpus — rather than papering the gap over with a
  loosely related provision.
- **The jurisdiction switch is automatic, not a control.** Routing and the
  visible layer badge are done; the PS's word is "toggle".
- **No escalation path to a human IP facilitator.** Named in the expected
  solution; not built.
- **Bhashini not integrated.** Hindi/Tamil/Telugu concept matching and
  localised scaffolding work; the national language infrastructure does not.
- **No knowledge graph or agentic orchestration.** The PS explicitly allows
  staging these after the citation-grounded MVP.

---

## 5. Sources

- [SIH 2026 problem statement catalogue (PS 26045, p.66–67)](https://sih-2026-problem-statements.shaikrohit187.workers.dev/public/pdfs/SIH_2026_All_PS.pdf)
- [SIH 2026 problem statements listing](https://github.com/NoBugNinja/Smart-India-Hackathon-SIH-2026-Problem-Statements)
- [Smart India Hackathon](https://sih.gov.in/)
- [TRIPS Agreement (WTO)](https://www.wto.org/english/docs_e/legal_e/27-trips.pdf)
- [Convention on Biological Diversity](https://www.cbd.int/doc/legal/cbd-en.pdf)
- [Nagoya Protocol](https://www.cbd.int/abs/doc/protocol/nagoya-protocol-en.pdf)
- [WIPO GRATK Treaty, GRATK/DC/7 (24 May 2024)](https://www.wipo.int/edocs/mdocs/tk/en/gratk_dc/gratk_dc_7.pdf)
- [Patent Cooperation Treaty](https://www.wipo.int/documents/d/pct-system/docs-en-texts-pct.pdf)
- [Regulations under the PCT](https://www.wipo.int/documents/d/pct-system/docs-en-texts-pct-regs.pdf)
- [PCT legal texts index](https://www.wipo.int/en/web/pct-system/texts/index)
- [FDA Botanical Drug Development — Guidance for Industry](https://www.fda.gov/media/93113/download)
- [The Patents (Amendment) Rules, 2024 — WIPO Lex](https://www.wipo.int/wipolex/en/legislation/details/23105)
- [The Designs Act 2000 — IP India](https://ipindia.gov.in/the-designs-act-2000)
- [Biological Diversity Rules 2024 — commentary](https://www.lexorbis.com/simplifying-and-expediting-the-approval-procedures-of-access-and-usage-of-biological-resources-the-biological-diversity-rules-2024/)
- [Protecting India's Traditional Knowledge — WIPO Magazine](https://www.wipo.int/en/web/wipo-magazine/articles/protecting-indias-traditional-knowledge-37721)
