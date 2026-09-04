# IP-SAKTI Sahayak — judge demo script

Every question below was run end to end against this machine's stack
(`qwen2.5:1.5b` via Ollama, **3094 provisions across 29 instruments**, 14/14
rules verified) and the observed behaviour is written next to it. Timings are
from that run — a cold first question costs more, so do the pre-flight.

The problem statement this is built against is **SIH26045** (Ministry of Ayush /
All India Institute of Ayurveda). Read
[SIH26045-problem-statement-alignment.md](SIH26045-problem-statement-alignment.md)
before you present — it has the PS verbatim, the coverage audit and the honest
list of what is not built yet.

**Golden rule:** ask the questions in §2 and §3. The ones in §5 have been
measured and are known to embarrass you.

---

## 1. Pre-flight (5 minutes before you present)

```bash
python cli.py serve                 # web chat UI at http://127.0.0.1:8000
```

Then, in order:

1. Open `http://127.0.0.1:8000` and **hard-refresh** (Ctrl+Shift+R).
2. Check the header badge reads `3094 provisions · 14/14 rules verified` on the
   first line and `qwen2.5:1.5b · runs offline` on the second. A **red dot**
   means Ollama isn't up — the app still works, but it will quote provisions
   extractively instead of writing prose.
3. Ask one throwaway question (any of §2) to page the model in. The server warms
   the model at boot on a background thread, but paying the load cost on a
   throwaway is safer than paying it on question one.
4. Have this file open on your phone, not on the projected screen.

---

## 2. The core run (about 6 minutes, in this order)

The order matters — it walks from "grounded answer" to "it refuses" to "it
compiles", which is the actual argument of the project.

### Q1 — a grounded answer with click-to-source

> **Can I patent a traditional ayurvedic formulation?**

Expect: "No — it falls under traditional knowledge and is not an invention",
citing **The Patents Act, 1970, Section 3** with a groundedness pill around
`0.50`. Takes ~2s.

**Do this:** click the citation. The dialog opens the full provision, scrolled
to the exact sentence the answer leaned on, highlighted, with the source PDF
name and page number. *Say:* "the answer is not the product — the provision
behind it is."

### Q2 — it takes the question in Hindi, and resolves the plant

> **क्या मैं गिलोय का पेटेंट करा सकता हूँ**

Expect: citing **Patents Act Section 3(p) — "What are not inventions"**, the
traditional-knowledge exclusion. You should also see a `resolved:` line mapping
**गिलोय / giloy → Tinospora cordifolia** and a `Hindi` language pill. ~5s.

Try the Tamil form too — same route, no translation involved:

> **கிலோய்க்கு (Giloy) என்னால் காப்புரிமை பெற முடியுமா?**

*Say:* "the question was Hindi, the statute is English, and the plant name had
to become a botanical taxon before either could be searched. The concept
lexicon carries the question in Hindi and Tamil, so this one never went near a
translation model at all."

**Be straight about the language pill.** Everything the *system* says — the
framing, the abstention, the 'this is background, not law' warning — is in the
user's language, from a hand-written table, deterministically. The quoted
statute stays in English on purpose: a translated quote is a paraphrase, and a
paraphrase is not authority. The model's *explanation* is localised only when a
model that can actually write the language is installed; with the 1.5B model
that ships for speed, the answer says so in Hindi rather than emitting
plausible-looking nonsense. If a judge asks, that is the honest trade and it is
one command away:

```
ollama pull gemma3:4b        # then restart the server
```

### Q3 — it refuses instead of improvising ⭐ *the most important question*

> **what is the EPO opposition period**

Expect: **instant** (0.0s — no model call at all) abstention:

> "I don't have authority in the ingested corpus to answer that. Rather than
> assemble something plausible from loosely related provisions, I'd rather say
> so. **Why:** the question is about EPO law. The corpus covers Indian primary
> sources plus TRIPS, the CBD and Nagoya Protocol, the WIPO GRATK Treaty, the
> PCT and US FDA botanical-drug guidance — none of which govern it."

*Say:* "it names the reason it can't answer, and it names what it does have.
That is the difference between a system with a corpus and a system with a
vibe."

This is the sharpest moment in the demo, because the PS scores it: SIH26045
lists **"safe abstention on out-of-scope or uncertain queries"** as an explicit
evaluation criterion. The refusal is a requirement being met, not a limitation
being confessed.

### Q4 — the compile ⭐⭐ *the centrepiece*

> **my churna contains amla, haritaki and bibhitaki and I market it as "cures diabetes"**

(Also the second suggestion chip, so you can click it instead of typing.)

Expect, in about **0.1 seconds** — no LLM involved, this is the rule engine:

- **Resolved:** amla → *Emblica officinalis*, haritaki → *Terminalia chebula*,
  bibhitaki → *Terminalia bellirica*
- **4 blockers · 2 warnings · 1 opportunity · 4 obligations**, C-BOM digest
  `c32de2b3af1d5493`
- Blockers across **all four lanes**:
  - `ACCESS` — Biological Diversity Act **s.6(1)** (NBA approval before an IPR application)
  - `BRAND` — Drugs and Magic Remedies Act **s.3(d) read with the Schedule** (diabetes is a scheduled disease)
  - `PATENT` — Patents Act **s.3(e)** (mere admixture)
  - `PATENT` — Patents Act **s.3(p)** (traditional knowledge)
- An **opportunity** finding: s.3(p) re-read as *evidence of traditional use*
- **What you must do** — a 4-row obligations table (s.21(1) benefit sharing,
  s.6(1) NBA approval, s.7 SBB intimation, s.10(4)(d)(D) disclosure of origin),
  each with who discharges it and when
- **Jurisdiction matrix** — IN / BLOCKER / "Excluded as claimed" / next action

*Say:* "it stopped answering questions and started compiling. Same input a
patent agent would take, and it took a tenth of a second because the rules are
deterministic — the language model is not in this path."

### Q5 — the recompile (say this immediately after Q4)

> **apply the fixes**

Expect: **Blockers 4 → 0**, the fixes named in order —
`OBTAIN_NBA_APPROVAL`, `REWRITE_TO_NON_SCHEDULED_CLAIM`, `ESTABLISH_SYNERGY` —
and a **new C-BOM digest** (`8a5f1713a8c8f803`). It closes with: *"That is a
recompile, not a promise — the rules were re-run against the patched facts."*

*Say:* "it didn't tell me the blockers cleared. It re-ran the rules against the
patched facts and showed me which ones actually did."

*Two things a sharp judge may notice, and the answers:* the cleared list is
**cumulative** — each line shows everything cleared so far, not just that one
fix. And **`ESTABLISH_SYNERGY` appears twice** because two separate blockers
(s.3(e) mere admixture and s.3(p) traditional knowledge) both propose it, so it
is applied once per finding. Clearing s.3(p) also retires the
`REG.TRADITIONAL_USE_ASSET` opportunity, which is why the opportunity count
drops to zero.

### Q6 — the closer: it knows what is law and what isn't

> **What is Ayurveda?**

Expect: a real answer from *Ayurveda at a Glance*, but the citation block is
headed **"Background material (not law)"** and carries a *background, not law*
pill.

*Say:* "same corpus, different authority rank. It will not let a primer stand
in for a statute."

---

## 3. Backup questions (all measured, safe to ask)

| Question | What comes back | Groundedness |
|---|---|---|
| **What does Section 7 of the Biological Diversity Act require?** | Quotes s.7 prior-intimation duty correctly | **1.00** |
| **I am a vaidya, do I need to inform the state biodiversity board** | Correct: only for commercial utilisation / bio-survey | **1.00** |
| **What is the TKDL and how is it used against patent applications?** | TKDL as defensive prior art, cites the TKDL document | **1.00** |
| **Must I disclose the source and geographical origin of biological material in my patent specification?** | Yes, cites Patents Act s.10 | **1.00** |
| **What is benefit sharing under Section 21 of the Biological Diversity Act?** | Equitable sharing, cites BDA s.21 | 0.75 |
| **What is prior art and how does traditional knowledge count as prior art?** | Cites the TKDL document (flagged as background) | 0.83 |
| **What licence do I need to manufacture an ayurvedic drug?** | Concrete: **Form 25-D**, fee, cites Drugs & Cosmetics Act | 0.33 |
| **how do I file a patent in Japan** | Instant abstention naming Japan | — (abstains) |

### Alternative compiles, if a judge wants to drive

- **`my formulation contains sarpagandha, ashwagandha and giloy and I want to patent it abroad`**
  → adds a **Patents Act s.39** blocker (foreign filing without permission),
  with fixes `FILE_IN_FIRST` / `OBTAIN_FFL_PERMIT`. Shows the engine reacting to
  *filing intent*, not just ingredients. 4 blockers → 0 after fixes.
- **`my taila contains kuth, red sanders and ashwagandha and I want to patent it`**
  → **"red sanders" resolves to nothing**, and the engine raises a warning with
  the fix `CONFIRM_TAXON_WITH_USER` rather than guessing a species. Good answer
  to "what if it doesn't recognise an ingredient?"
- Add `and the label says "cures diabetes and cancer"` to any of these to fire
  the advertising lane.

**The claim must be in quotes.** "sell it as a cure for diabetes" *without*
quotes parses no marketing claim and the BRAND lane will not fire. This is the
single most likely way to fumble the compile demo live.

---

## 3a. The international layer (added for SIH26045's "international regimes")

SIH26045 requires the national and international regimes to be answerable and
**kept visibly separate so answers are never conflated**. Both layers are now
ingested, retrieved separately, and every answer carries a layer badge —
`India layer — national law` or `International layer — treaty & foreign
regulator` — plus a jurisdiction tag on each citation (`WTO`, `CBD`, `WIPO`,
`PCT`, `US`).

All four below were measured end to end.

| Question | What comes back | Groundedness |
|---|---|---|
| **what does the Nagoya Protocol require for benefit sharing** | `INTL` badge; **Nagoya Protocol Article 7 and Article 5** (`CBD`) — and *not* BDA s.21, which is the point | **1.00** ⭐ |
| **can I file a PCT application for my formulation** | `INTL`; **PCT Article 11 and Article 25** (`PCT`) | 0.75 |
| **what is the new WIPO treaty on genetic resources and traditional knowledge** | `INTL`; **WIPO GRATK Treaty Article 3** (`WIPO`) — quotes the disclosure duty: country of origin, and the Indigenous Peoples or local community | 0.67 |
| **is India obliged under TRIPS to allow patents on plants** | `INTL`; **TRIPS Article 27** (`WTO`) | 0.60 |

**Do this on the Nagoya question**, it is the best 20 seconds in the demo:

1. Ask it. Note the blue **International layer** badge and that every citation
   is tagged `CBD`.
2. Point at the italic line under the citation: *"India is a Party.
   Access-and-benefit-sharing duties are given domestic effect through the
   Biological Diversity Act and its Rules."*
3. Then ask the Indian counterpart: **What is benefit sharing under Section 21
   of the Biological Diversity Act?** — green **India layer** badge, only Indian
   citations.

*Say:* "same subject, two regimes, two separate answers. Before this the
retriever put Section 21 of the Indian Act and Article 5 of the Protocol in one
answer — and 'India is a Party to Nagoya' and 'you can sue on Nagoya in Delhi'
are very different statements. The separation is a retrieval pre-filter, not a
label added afterwards."

On the TRIPS answer, the note under the citation reads *"Binds India as a WTO
Member. Not directly enforceable in Indian courts; given effect through the
Patents Act and allied legislation."* That sentence is on the instrument in the
corpus, not generated — a judge with an IP background will look for exactly
that distinction.

---

## 3b. The classification flow ⭐ *the newest and most PS-specific beat*

SIH26045 does not ask for an IP chatbot. It asks for an assistant that
**classifies the formulation first**, "because intellectual property for an
Ayurvedic product is inseparable from how the product is regulated". This is
the part of the problem statement most teams will skip.

Run it as a three-turn conversation. Timing is instant — no model is involved.

**Turn 1** — the Q4 compile (the second suggestion chip). Alongside the
findings you now get a **Classification** block in amber:

> **Classification — one thing still needed**
> 1. Is both the formula and the method of preparation taken from a classical
>    text listed in the First Schedule (for example the Ayurvedic Formulary of
>    India), or is the combination your own?
>
> *The category decides the IP posture: the same herbs are unpatentable
> traditional knowledge as a classical churna and a defensible invention as a
> standardised fraction.*

*Say:* "it read four facts off what I typed — churna, so not a purified
fraction; 'cures diabetes', so a disease claim — and it is asking only for the
one fact it still needs. That is the problem statement's 'minimum clarifying
questions', literally."

**Turn 2** — type **no** (it is your own combination, not a classical formula).
It asks the next single question: *are all the ingredients named in the
authoritative books?*

**Turn 3** — type **yes**. The block turns blue and decides:

> **Regulatory category: Patent or proprietary ASU medicine**
> because the ingredients are all named in the authoritative books but the
> formula is not.
>
> **Requires** — licensed as an ASU drug; where the indication is not a textual
> one, safety and effectiveness data are required.
> **IP posture** — intermediate. A claim to the combination alone invites both
> s.3(p) and s.3(e); a patent becomes arguable only on evidence of synergy.
> **ABS posture** — s.6(1), s.7 and s.21 apply, and s.10(4)(d)(D) requires the
> source and geographical origin of each biological material.
>
> **What defines this category:** Drugs and Cosmetics Act, 1940 — Section 3 ·
> Drugs and Cosmetics Rules, 1945 — Rule 158

*Say:* "same three herbs. If the answer to turn 2 had been yes, this would be a
classical medicine and the honest advice would be 'you cannot patent this,
protect the brand instead'. The category is the advice, and it took a
millisecond because it is a decision table, not a model."

**Try the other end of the range**, in a fresh question:

> **my product is a standardised extract with 5% withanolides from ashwagandha for treating arthritis**

Decides immediately — **Phytopharmaceutical drug**, citing Rule 2(eb) and Rule
122E — with the IP posture reversed: *"the strongest patent position of any
category here… the claimed invention is no longer the traditional
combination."*

*Say:* "that is the whole argument of the problem statement in two questions.
Standardise the fraction and you move from unpatentable traditional knowledge to
a defensible invention — and pick up a clinical evidence burden instead."

One more worth having ready, because it shows the system declaring a gap rather
than bluffing. Note the phrasing: classification is reached either by
describing a formulation (two or more ingredients) or by asking for it — "what
category", "classify my product". A bare description with neither goes to
ordinary retrieval, so lead with the question:

> **what category is my product — a tulsi and giloy drink sold as a health supplement, our own blend, no disease claim**

Decides **Ayurveda Aahara / nutraceutical**, and prints in amber: *"The Food
Safety and Standards (Ayurveda Aahara) Regulations, 2022 are not in the
ingested corpus, so the FSSAI requirements above are named without a citation
and must be confirmed against the regulation itself."*

---

## 3c. The polarity guard

> **Do I need approval from the National Biodiversity Authority before applying for a patent?**

Watch the status line: it reads **"this answer turns on whether a duty applies —
quoting the provision instead of paraphrasing it"**, and there is no *drafting*
stage at all. The answer quotes s.6(1): *"No person shall apply for any
intellectual property right … without obtaining the previous approval of the
National Biodiversity Authority"*, and the footer says **"Quoted, not
paraphrased"**.

*Say, and this is the strongest single sentence available about the
architecture:* "before this guard, that question came back 'No, you do not need
approval' — at groundedness 1.00. The gate checks that every sentence is
carried by the cited text; it cannot check that the model kept the direction of
the duty. So a groundedness score is a traceability score, not a correctness
score, and questions whose entire answer is a yes-or-no do not go near the
model."

The guard is first-person only, and that distinction is worth demonstrating
back-to-back:

- **do I need** … → guarded, provision quoted
- **what does the Nagoya Protocol require** → *not* guarded, the model answers
  it at groundedness 1.00, because that asks what the duty contains rather than
  whether it binds you

---

## 4. Questions judges are likely to ask you

**"How do you know it isn't hallucinating?"**
Three mechanisms, in order. Retrieval is restricted to the ingested corpus.
Every drafted sentence is then verified against the retrieved statutory spans,
and unsupported sentences are **dropped before you see them** — the UI shows a
"sentences removed by the citation gate" note when that happens. What survives
gets a groundedness score. If the whole draft fails, it falls back to quoting
the provision verbatim rather than shipping fluent prose.

**"What happens when it doesn't know?"**
It abstains and names the reason — Q3. It does not assemble an answer from
loosely related provisions.

**"Is this just ChatGPT with a system prompt?"**
No, and the compile is the proof: 1712 provisions ingested from primary-source
PDFs with page numbers, 14 deterministic rules (all 14 verified against the
statutory text), and the compile path returns in ~0.1s **without calling a
language model at all**. The model only phrases answers on the ask path; it
never decides a finding.

**"Does it need the internet? Where does my formulation go?"**
Nothing leaves the machine — the model runs locally under Ollama. Chat sessions
are in-process and ephemeral by design: **nothing you type is written to disk**,
and restarting the server forgets it. That is deliberate, because the first
objection from industry is "why would I upload my proprietary formulation?"

**"Why such a small model?"**
Because the model isn't doing the legal reasoning — the rule engine is. The
model phrases and translates; the citations and findings are deterministic. It's
swappable (mistral, llama3.1, llama3.2 and llama3 are already pulled on this
machine).

**"Is it reproducible?"**
Yes — every compile emits a C-BOM digest over the findings. Same facts, same
digest (`c32de2b3af1d5493` for the Q4 formulation, every time); patch a fact and
the digest changes. You can re-run Q4 to show the same digest twice.

**"Which laws are in there?"**
**22 instruments, 2,178 provisions**, in two separately-retrieved layers.

*India (1,758):* Patents Act 1970, Patents Rules 2003 **and the Patents
(Amendment) Rules 2024**, Drugs & Cosmetics Act 1940 & Rules 1945, Trade Marks
Act 1999, GI Act 1999, Biological Diversity Act 2002, Copyright Rules 1957,
Plant Varieties & Farmers' Rights Act 2001, Drugs and Magic Remedies Act 1954 —
plus the TKDL documentation and the AYUSH primers (Ayurveda / Unani / Siddha /
Sowa-Rigpa), which are rank-separated as background rather than law.

*International (420):* **TRIPS** (73 Articles), the **Convention on Biological
Diversity** (43), the **Nagoya Protocol** (36), the **WIPO GRATK Treaty 2024**
(21), the **PCT** (69) and its **Regulations** (144), and **US FDA
botanical-drug guidance** (34 pages).

Each count matches the instrument's real structure — TRIPS genuinely has 73
articles, the Nagoya Protocol 36, the PCT 69. That is the check that the parser
read the treaty and not its table of contents.

**"What's missing?"** Answer it straight, it lands better than hedging: the
Designs Act, the Copyright Act itself (we hold only the Rules), the Biological
Diversity Amendment 2023 and Rules 2024, the FSSAI Ayurveda-Aahar regulations,
and the Madrid / Hague / Budapest treaties. Every one is a public PDF and the
ingest is one registry entry plus a re-run —
[SIH26045-problem-statement-alignment.md](SIH26045-problem-statement-alignment.md)
lists the exact sources. The formulation-classification flow the PS describes
(classical / patent-or-proprietary / new drug / phytopharmaceutical /
Ayurveda-Aahar / cosmetic) is the largest piece not yet built.

**"Is this legal advice?"**
No — the footer says so, and say it out loud once: informational compliance
analysis from primary sources, not a substitute for a registered patent agent or
advocate.

---

## 5. Do NOT ask these (measured, and they misfire)

The citation gate protects the *citations*, not the local model's phrasing. When
retrieval lands on the wrong section, a 1.5B model can still write a confident
wrong sentence — and on these specific questions, it does.

| Don't ask | What actually happens |
|---|---|
| *What does Section 3(p) of the Patents Act say?* | Retrieves ss.162/64/49, not s.3 — the answer is about revocation and is **wrong**, even though the groundedness pill reads 1.00. **Use Q2 instead**, which reaches s.3(p) correctly. |
| *Who can apply for a patent in India?* | Answers about s.39 foreign filing instead. Wrong question answered. |
| *What is a mere admixture under Section 3(e)?* | Groundedness **0.00**, cites the AYUSH primers. **The Q4 compile states the s.3(e) finding properly** — use that. |
| *Can I register a geographical indication for a herbal product?* | Returns a dangling fragment starting "Additionally, generic names…". |
| *What is the term of a patent in India?* | Right answer, but cites the AYUSH primers alongside the Act — looks sloppy on screen. |

**Five questions came off this list** and are now safe to ask:

- *Can I trademark the name of my ayurvedic churna?* used to **abstain** despite
  168 ingested sections of the Trade Marks Act. Now answers from s.9 and s.11,
  groundedness **0.667**. Cause: the concept lexicon had no lay phrase for the
  bare word "trademark".
- *What's the difference between a patent, GI, and trademark for an Ayurvedic
  product?* used to score **0.00** with three sentences stripped by the gate,
  citing only the Patents Act. Now cites **Trade Marks s.9, GI s.9 and Patents
  s.3** together, groundedness **0.571**.
- **Three duty questions that used to answer with the polarity inverted** —
  *"Do I need NBA approval before applying for a patent?"*, *"Do I need
  permission before filing outside India?"* and *"do I need FDA approval to
  sell in the US market?"* — all three said **"No"** against provisions saying
  the opposite, at groundedness 1.00. They are now claimed by the polarity
  guard (§3b) and quote the provision instead. Ask them.

If a judge asks one of the remaining ones unprompted, the honest and strong
answer is: *"that one exposes the retrieval, not the gate — the citations are
still real and you can open them, but the phrasing drifted. That's why the
compile path doesn't use the model at all."* Then pivot to Q4.

**If a judge presses on the FDA case specifically**, the sharp answer is the
one worth rehearsing: *"groundedness is a traceability score, not a correctness
score. It says every sentence is supported by spans in the cited provision; it
does not check that the model kept the polarity. A 1.5B model negates. That is
an argument for a bigger model on this path — it's one environment variable —
and for the deterministic compile path, where no model is involved at all."*

---

## 6. If something breaks

- **Send button does nothing / no suggestion chips / header stuck on "loading…"**
  The page's JavaScript failed to parse. Hard-refresh (Ctrl+Shift+R) first; if
  it persists, open the browser console — a single syntax error in
  `web/chat.html` disables the whole script, chips included.
- **Red dot in the header, answers arrive as bare quotations.** Ollama is down.
  `ollama serve`, then re-ask. The ask path degrades to extractive quoting and
  the compile path is unaffected — say so rather than restarting the demo.
- **First question hangs for 30+ seconds.** The model is paging in. The elapsed
  counter next to the "drafting…" line is ticking, so it is visibly working —
  narrate the pre-flight instead of clicking again.
- **A compile returns no findings.** The ingredient list didn't parse. It needs a
  trigger word — `contains`, `containing`, `made of`, `with` — followed by at
  least two ingredients. Fall back to clicking the second suggestion chip.
- **Everything is broken.** `python cli.py serve` again in a fresh terminal; the
  corpus and rules load from disk in seconds and no state is lost, because there
  was never any state on disk to lose.
