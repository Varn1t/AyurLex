"""Chapters 5-15: the engineering."""
from __future__ import annotations

from scripts.documentation_content import _table


def ch_architecture(s: dict) -> str:
    return f"""
<h1>5 &nbsp; System architecture</h1>
<p class="kicker">HOW IT WORKS UNDER THE HOOD</p>

<p class="lead">Eleven modules in four layers. The rule that organises all of
them: <b>data flows upward through verification gates, and no layer may assert
something a lower layer has not already proved.</b></p>

<h2>5.1 &nbsp; The layers</h2>

<pre>
  INTERFACE      web chat UI (SSE streaming)  ·  CLI  ·  HTTP API
                 web/chat.html                   cli.py   server.py
                          |
  ------------------------+------------------------------------------
  ORCHESTRATION  PLANNER         deterministic plan, typed tools, trace
                 CHAT            intent routing, session state, follow-ups
                          |
  ------------------------+------------------------------------------
  REASONING      RULES           rules as data
                 OBLIGATIONS     who must do what, and when
                 JURISDICTIONS   jurisdiction matrix
                 CLASSIFICATION  regulatory category
                 GRAPH           knowledge graph
                 ESCALATION      route to a human
                 RESOLVER        name -> taxon
                 RAG             retrieval
                          |
  ------------------------+------------------------------------------
  VERIFICATION   CITATION GATE   ·  loader gates  ·  schema
                          |
  ------------------------+------------------------------------------
  EVIDENCE       SOURCES         corpus: {s['provisions']:,} provisions, page-anchored
                 Dataset/ {s['pdfs']} primary-source PDFs ({s['dataset_mb']} MB)
</pre>

{_table(["Module", "Job", "Location", "Lines"], [
    ("<b>Sources</b>", "Structure-aware extraction from primary PDFs; "
     "authority ranks; BM25 index", "<code>sources/</code>", "1,209"),
    ("<b>Rules</b>", "Law as code &mdash; versioned, date-effective, "
     "declarative YAML, corpus-bound at load", "<code>compliance/</code>", "743"),
    ("<b>Citation gate</b>", "Citation verifier; an unverified sentence does not "
     "ship", "<code>citations/</code>", "243"),
    ("<b>Obligations</b>", "Obligation checklist generator",
     "in <code>compliance/engine.py</code>", "&mdash;"),
    ("<b>Jurisdictions</b>", "Jurisdiction bridge, with explicit abstention",
     "<code>jurisdictions/</code>", "123"),
    ("<b>Classification</b>", "Regulatory classification into the six "
     "categories", "<code>classification/</code>", "408"),
    ("<b>Knowledge graph</b>", "Relational knowledge graph and multi-hop walks",
     "<code>graph/</code>", "631"),
    ("<b>Planner</b>", "Agentic orchestration: plan, tools, trace",
     "<code>planner/</code>", "613"),
    ("<b>Escalation</b>", "Escalation to a human facilitator; referral packet",
     "<code>escalation/</code>", "584"),
    ("<b>RESOLVER</b>", "Any script or language &rarr; canonical taxon",
     "<code>core/resolver.py</code>", "204"),
    ("<b>RAG layer</b>", "Hybrid retrieval, concept lexicon, grounded "
     "answers, chat, streaming", "<code>rag/</code>", "3,032"),
])}

<h2>5.2 &nbsp; Request lifecycle: the ASK path</h2>

<p>This is the path a legal question takes. Note where the model appears, and
where it does not.</p>

<pre>
 1  detect language          Unicode block, then romanised-Indic function words
 2  concept match            data/legal_concepts.yaml -- lay phrasing to
                             statutory vocabulary; ordered-subsequence within a
                             proximity window
 3  polarity guard           first-person duty question? -> extractive path,
                             no model  (see 8.4)
 4  out-of-corpus check      names a jurisdiction we do not hold? -> ABSTAIN,
                             no model call at all
 5  layer routing            IN or INTL, decided by the concepts' own
                             jurisdictions; a PRE-FILTER, not a post-filter
 6  taxon expansion          RESOLVER: giloy -> Tinospora cordifolia
 7  retrieval                BM25 + LSA dense + taxon, fused by reciprocal
                             rank fusion, reranked on heading match and
                             authority rank
 8  weak-retrieval check     nothing scoring high enough? -> ABSTAIN
 9  CITATIONS STREAM FIRST   ~0.1s, before a single word of prose
10  draft                    the local model, shown ONLY the top 3 extracts
11  citation gate             every sentence checked against those same 3
                             extracts; numbers, quotations and instrument
                             names take exact-match paths
12  localise                 terminology lock: section numbers, Act names and
                             terms of art are never translated
13  final                    verified text replaces the draft; what was
                             dropped is shown, not silently deleted
</pre>

<div class="box">
<p class="last"><b>Steps 3, 4 and 8 can end the request before the model is
ever called.</b> That is the design: the fastest and safest answers are the
ones where no generation happens. Abstention costs 0.0 seconds.</p>
</div>

<h2>5.3 &nbsp; Request lifecycle: the COMPILE path</h2>

<p>No language model is involved at any step. Measured warm: <b>~30 ms</b>.</p>

<pre>
 1  parse            ingredients, dosage form, claims, markets, filing intent
 2  RESOLVER         every ingredient -> canonical binomial, or an explicit
                     refusal to guess where synonymy is contested
 3  build facts      a typed FactTable; every fact records why it holds
 4  Classification      regulatory category from six tri-state facts, or the one
                     question that would settle it
 5  Rules            declarative rules evaluated against the facts; only
                     VERIFIED rules may emit
 6  Citation gate          each finding's sentences checked against its own cited
                     span; a finding that fails is SUPPRESSED and the
                     suppression is printed
 7  Obligations           obligations, each with who discharges it and when
 8  Jurisdictions             jurisdiction matrix; a jurisdiction with no ingested
                     corpus prints ABSTAIN and names what it would need
 9  C-BOM            signed, digest-stable artifact
</pre>

<h2>5.4 &nbsp; Where each interface enters</h2>

{_table(["Surface", "Entry point", "Notes"], [
    ("Web chat", "<code>server.py</code> &rarr; <code>/api/chat/stream</code>",
     "Server-sent events. Citations are sent before any prose"),
    ("Terminal chat", "<code>cli.py chat</code>", "Same session object"),
    ("One-shot", "<code>cli.py ask</code>", "Scriptable"),
    ("Compile", "<code>cli.py compile &lt;fixture&gt;</code>",
     "<code>--autofix</code>, <code>--html</code>, <code>--out</code>"),
    ("Graph", "<code>cli.py graph</code> / <code>path</code>, "
     "<code>/api/graph/*</code>", "Deterministic; no model"),
    ("Escalation", "<code>cli.py escalate</code>, <code>/api/escalate</code>",
     "Generates a packet; transmits nothing"),
    ("Orchestrator", "<code>cli.py plan --dry-run</code>",
     "Prints the plan before it runs"),
    ("Verification", "<code>scripts/verify_provisions.py</code>",
     "Re-extracts every anchor from the PDFs; fails on drift"),
])}
"""


def ch_corpus(s: dict) -> str:
    rows = [(t[:52], j, f"rank {rk}", u, f"{n:,}")
            for (aid, t, j, rk, u), n in s["instrument_rows"]]
    ranks = ", ".join(f"rank {k}: {v:,}" for k, v in s["ranks"])
    return f"""
<h1>6 &nbsp; The corpus: sourcing, extraction, and the problems solved</h1>
<p class="kicker">SOURCES &mdash; EVIDENCE THAT RESPECTS LEGAL STRUCTURE</p>

<p class="lead">{s['provisions']:,} provisions from {s['instruments']}
instruments, extracted from {s['pdfs']} primary-source PDFs ({s['dataset_mb']}
MB) shipped in the repository. Every record carries its source file, page
range, the date it was retrieved, its authority rank, its jurisdiction, and the
unit its instrument actually numbers by.</p>

<h2>6.1 &nbsp; Authority ranks, and why they are not decoration</h2>

<p>Rank decides what a record may be used for. Distribution: {ranks}.</p>

{_table(["Rank", "Kind", "May be cited as law?"], [
    ("1", "Statute", "Yes"),
    ("2", "Rules made under a statute", "Yes"),
    ("3", "Notification", "Yes"),
    ("4", "Case law / registry outcome", "Yes, as evidence"),
    ("5", "Official regulator guidance", "Yes, as guidance &mdash; labelled"),
    ("6", "Pharmacopoeial / classical / reference", "<b>No</b> &mdash; "
     "labelled <i>background, not law</i>"),
    ("7", "Commentary", "<b>No</b>"),
])}

<p>A definitional question ("What is Ayurveda?") deliberately widens to the
rank-6 material, inverts the authority weighting &mdash; a request for a
description wants the descriptive corpus, not "What are <i>not</i> inventions"
&mdash; and the answer is <b>labelled as background, not law</b>. Refusing the
easiest question a user will ask makes the whole assistant look broken; letting
a primer stand in for a statute is worse. The rank is what lets it do both.</p>

<h2>6.2 &nbsp; The instruments</h2>

{_table(["Instrument", "Regime", "Rank", "Unit", "Provisions"], rows)}

<h2>6.3 &nbsp; Three extraction problems, each solved deterministically</h2>

<p>These are the failures that make PDF-to-provision harder than it looks, and
each was found by checking a count against the instrument's real structure.</p>

<h3>Footnotes read as sections</h3>
<p>India Code sets footnotes at 9pt at the foot of the page, renumbered per
page. A linear extraction reads <i>"3. Cl. (a) omitted by Act 33 of 2021&hellip;"</i>
as Section 3 and <b>overwrites the real one</b>. Font size and y-position
separate them. Those footnotes are then kept as <code>amendment_notes</code>,
because they carry the commencement dates.</p>

<h3>Substituted sections vanish</h3>
<p>A substituted section carries its amendment bracket first:
<code>3[39. Residents not to apply&hellip;</code>. Without an optional prefix
in the pattern, Patents Act s.39 and s.43 disappear entirely &mdash; and s.39
is the foreign-filing permit, one of the four blockers the demonstration
turns on.</p>

<h3>Two-column and two-up treaty typesetting</h3>
<p>The page extractor originally sorted lines by vertical position only, which
interleaves the columns of UN typesetting; and the article number, set on its
own line, was being deleted as a page number. <b>The Nagoya Protocol yielded
zero provisions.</b> A per-page reading-order detector fixed it; it now yields
its true 36.</p>

<h3>Broken ToUnicode maps</h3>
<p>Em dashes and curly quotes both extract as U+FFFD. Repaired by rule, with
<code>text_raw</code> keeping the untouched extraction for audit.</p>

<h2>6.4 &nbsp; Two structural rules that prevent wrong answers</h2>

<div class="box">
<p><b>Chunks split at section level and never below.</b> A proviso or an
<i>Explanation</i> can never be orphaned from its parent, because provisos
invert meaning. Biological Diversity Act s.7 carries a proviso exempting local
communities, growers and cultivators, and vaids and hakims practising
indigenous medicine &mdash; the rule tests that proviso rather than ignoring
it, which is why a practising vaidya is not told to file an intimation the
statute exempts them from.</p>
<p class="last"><b>Cite the instrument's own unit.</b> Treaties number
Articles, the PCT Regulations number Rules, Indian statutes number Sections,
prose material has only pages. "Section 27 of TRIPS" is a wrong citation. This
is enforced as a corpus invariant by
<code>tests/test_citation_units.py</code>: an instrument titled <i>Rules</i>
must number Rules, no instrument may mix units, and the id prefix must match
the label the reader is shown &mdash; so a source registered without its unit
fails the suite rather than shipping a wrong citation.</p>
</div>

<h2>6.5 &nbsp; Treaty force, stated rather than inferred</h2>

<p>Each treaty record carries a <code>force_note</code> that is displayed with
its citations. TRIPS reads: <i>"Binds India as a WTO Member. Not directly
enforceable in Indian courts; given effect through the Patents Act and allied
legislation."</i> That sentence is a property of the instrument in the corpus,
not something a model generated &mdash; and it is exactly the distinction an
IP-literate reader will look for.</p>

<h2>6.6 &nbsp; Real outcome data, not asserted precedent</h2>

<p>The official TKDL annexure lists patent applications actually revoked,
refused or withdrawn after TKDL prior art was cited against them.
{s['tkdl']} of those records are extracted with their application numbers and
page provenance. When a formulation resembles one, the compiler cites an
application a patent office already killed on that ground &mdash; checkable
evidence, not an asserted verse citation. The Drugs and Magic Remedies Schedule
is likewise extracted as {s['dmr']} named conditions, so "cures diabetes" is
matched against the Schedule rather than against a guess.</p>
"""


def ch_retrieval(s: dict) -> str:
    return f"""
<h1>7 &nbsp; Retrieval: the stack, and the number that forced it</h1>
<p class="kicker">WHY NOT JUST EMBEDDINGS</p>

<h2>7.1 &nbsp; Three retrievers, fused</h2>

<ol>
<li><b>BM25.</b> Strong on exact statutory phrasing, which matters more here
than in most domains: the words of a section are the thing being searched
for.</li>
<li><b>LSA dense.</b> Latent-semantic vectors learned from this corpus by
truncated SVD over TF-IDF, computed with a randomised range finder. Real
semantics; trains in about a second; needs no download; keeps the whole stack
air-gapped. It is <i>not</i> a transformer embedding, and the document says so
&mdash; BGE-M3 or multilingual-e5 is a drop-in replacement at
<code>DenseIndex.encode_query</code>.</li>
<li><b>Taxon expansion.</b> The query goes through RESOLVER first, so a
question about &#2327;&#2367;&#2354;&#2379;&#2351; also searches for
<i>Tinospora cordifolia</i>. The statutes are keyed on binomials; without this
step a vernacular question retrieves nothing at all.</li>
</ol>

<p>Fused with reciprocal rank fusion, then reranked on query-term coverage,
heading match, authority rank and structural signals.</p>

<h2>7.2 &nbsp; The measurement that changed the design</h2>

<div class="warn">
<p><b>That stack alone scored 2 out of 9 on the first question set.</b></p>
<p class="last">The failure was not tuning. It was <b>register</b>. "Can I
patent my family formulation?" and "What are not inventions" share no content
words at all, and no embedding fixes that reliably &mdash; because the gap is
not semantic distance, it is that a citizen and a statute use different
vocabularies for the same concept.</p>
</div>

<p>So <code>data/legal_concepts.yaml</code> maps lay phrasing (including
Devanagari and Tamil) to statutory vocabulary, the provisions that govern it,
and the compliance rules that decide it. {s['concepts']} concepts, curated as data
reviewable by a domain expert who does not read Python.</p>

<ul>
<li><b>Matching is ordered-subsequence within a proximity window.</b> "file
abroad" must match "file a patent abroad", but not "file" &hellip; forty words
&hellip; "abroad". Deliberately not fuzzy: a concept match applies a large
boost to specific provisions, so a loose match would be worse than none.</li>
<li><b>Concept ids are corpus-verified at load</b>, exactly like rules. A
concept pointing at a provision that does not exist fails loudly rather than
silently degrading search.</li>
<li><b>A concept can pin a clause</b>, so a traditional-knowledge question is
answered with s.3(p) rather than a recitation of all sixteen exclusions.</li>
</ul>

<p class="small"><b>Two one-line omissions cost two whole regimes.</b> The
lexicon had no lay phrase for the bare word "trademark" or the bare "GI". The
result: "Can I trademark the name of my ayurvedic churna?" <i>abstained</i>
despite 168 ingested sections of the Trade Marks Act, and the
patent-vs-GI-vs-trademark comparison scored 0.00 while citing only the Patents
Act. Both are fixed and both are now demonstration questions. The lesson is in
the repository's contributor notes: most "the model is bad" symptoms are
actually a missing <code>lay</code> phrase.</p>

<h2>7.3 &nbsp; The jurisdiction pre-filter</h2>

<p>Retrieval picks <b>one</b> layer and pre-filters to it, so an answer cannot
quote Section 21 of the Biological Diversity Act and Article 5 of the Nagoya
Protocol as though they were the same authority. The layer is decided by the
jurisdictions of the matched concept's own provisions &mdash; which is why a
concept may not mix Indian and international provisions in one entry.</p>

<p>The one exception is non-citable background material, deliberately exempt
from the pre-filter: the WHO standard terminology has to be able to answer
"what is vamana?" whichever layer the conversation is in, and it is never
cited as authority for a legal answer.</p>

<div class="box">
<p class="last"><b>Filters run before scoring, never after.</b> Retrieving a
repealed or out-of-layer provision and then filtering it out of the display is
still a correctness failure &mdash; it has already displaced a good result from
the top-k.</p>
</div>

<h2>7.4 &nbsp; Measured retrieval performance</h2>

{_table(["Operation", "Measured", "Notes"], [
    ("Corpus + rules load (cold)", "0.76 s", "Once, at process start"),
    ("BM25 + LSA index build", "1.07 s", "Once, at process start"),
    ("Knowledge graph build", "0.27 s", "Once, at process start"),
    ("Single retrieval", "~8 ms", "Mean over mixed queries"),
    ("Graph path (BFS)", "&lt; 0.1 ms", "Mean over 50 runs"),
    ("Full compile, warm", "~30 ms", "No model in this path"),
    ("Abstention", "0.0 s", "No model call is made at all"),
])}

<h2>7.5 &nbsp; The gold set, described honestly</h2>

<pre>
python cli.py eval

  recall@1            1.00  (17/17)
  recall@5            1.00  (17/17)
  abstention accuracy 1.00  (2/2)
</pre>

<div class="warn">
<p class="last"><b>Read that honestly.</b>
Seventeen items is a seed, not an evaluation, and the concept lexicon was
written while looking at these questions. The number that would mean something
is the same measurement on <i>held-out</i> items written by someone who has not
seen the lexicon &mdash; plus the ablation (dense-only vs hybrid vs
hybrid+concepts). That is the top item on the roadmap, and Chapter 20 lists it
as a limitation rather than burying it.</p>
</div>
"""


def ch_trust(s: dict) -> str:
    return """
<h1>8 &nbsp; The trust machinery</h1>
<p class="kicker">THE CITATION GATE &mdash; HOW HALLUCINATION IS MADE STRUCTURALLY HARD</p>

<p class="lead"><i>Pram&#257;&#7751;a</i> is a valid means of knowledge;
<i>&#347;abda-pram&#257;&#7751;a</i> is textual authority. This module accepts a
sentence only on textual authority.</p>

<h2>8.1 &nbsp; What the model is allowed to do</h2>

<p>Exactly three things: parse messy input into the typed schema, phrase
explanations of decisions the rule engine has already made, and translate.
<b>It never decides a legal outcome.</b> Every legal outcome is a declarative
rule firing on resolved facts.</p>

<p>Stated precisely, because overclaiming here would be the same sin the module
exists to prevent: the citation gate is a <b>strict lexical entailment gate</b>. Numeric
and citation tokens take an exact-match path; prose takes a content-word
coverage path against the cited span. It runs offline, deterministically, with
no model weights &mdash; which is also what lets the whole compiler run
air-gapped. It is <b>not</b> a neural NLI model. Swapping the prose path for a
cross-encoder is a drop-in change at <code>entailment_score</code>, and the
thresholds are the ones that would need tuning on a labelled set when that
lands.</p>

<h2>8.2 &nbsp; The four exact-match paths, and the failure that motivated each</h2>

<p>Every one of these was added because a real model failed it during this
build. They are worth knowing individually, because each is a different shape
of hallucination.</p>

""" + _table(["Check", "The failure that motivated it"], [
    ("<b>Numbers and section references</b>",
     "Invented deadlines and penalties. Numeric hallucination is the "
     "highest-risk failure mode in legal RAG, so numbers never get the benefit "
     "of fuzzy coverage. Comma-grouped numbers are matched whole &mdash; "
     "splitting '5,000' into '5' and '000' lets it pass on any span "
     "containing a 5"),
    ("<b>Quoted text must be verbatim</b>",
     "The model wrote that s.3(p) <i>defines an invention as \"&hellip;new, "
     "involves an inventive step&hellip;\"</i> &mdash; words that appear "
     "nowhere in the section, presented inside quotation marks as if read off "
     "the page. A fabricated <i>quotation</i> is a worse failure than a bad "
     "paraphrase: a paraphrase the reader can weigh, a quotation they cannot"),
    ("<b>Named instruments must be in the extracts</b>",
     "It suggested the 'Plant Variety Rights Act' as an alternative &mdash; "
     "plausible, adjacent, not retrieved, and invisible to a numeric check "
     "because it has no digits. Every distinctive word of the name must be "
     "present; ANY-match is useless, since 'rights' appears in almost any "
     "statute"),
    ("<b>The gate window equals the prompt window</b>",
     "Verifying against 5 hits when the model was shown 3 let a weakly-ranked "
     "hit legitimise a cross-reference the model never had. The gate now "
     "verifies against exactly the spans the model saw"),
]) + """

<p>What survives is displayed; what was dropped is shown to the user with the
reason, rather than quietly deleted. If the entire draft fails, the system
falls back to quoting the retrieved provision verbatim. <b>A duller true answer
beats fluent prose that cannot be checked.</b></p>

<h2>8.3 &nbsp; Where the system refuses</h2>

<ul>
<li><b>Outside the corpus.</b> A question about US or EPO law that no Indian
concept covers is abstained on <i>by name</i>, and the abstention names what
the corpus does hold. This is checked <i>before</i> the definitional widening,
so "what is the EPO opposition period" cannot slip through as a definition
question.</li>
<li><b>Weak retrieval.</b> Nothing scoring high enough to rely on. The floor
is set by what the top hit <i>is</i>, not by one flag: a statutory section is a
tight self-contained chunk and a real match scores well above 0.10, while
regulator guidance is ingested as whole pages of continuous prose and its best
hit is diffuse by construction. Holding guidance to the statutory floor made
the assistant abstain on a WHO benchmark question <i>while holding the page
that answers it</i> &mdash; not caution, a miscalibrated threshold.</li>
<li><b>Contested taxon.</b> <i>Brahmi</i> denotes <i>Bacopa monnieri</i> in
some regions and <i>Centella asiatica</i> in others. It resolves to neither and
raises a warning naming both. That is not a limitation &mdash; botanical
synonymy is genuinely contested for several Ayurvedic drugs, and surfacing the
ambiguity is more correct than resolving it.</li>
</ul>

<h2>8.4 &nbsp; The polarity guard &mdash; where the citation gate cannot help</h2>

<div class="warn">
<p><b>This is the most important paragraph in the document.</b></p>
<p class="last">"Do I need NBA approval before filing?" has an answer whose
entire content is its polarity. The citation gate cannot check polarity: it
verifies that a sentence is <i>carried by</i> spans of the cited provision, and
"you do not need approval" is built from the same words as the provision that
requires it.</p>
</div>

<p>Measured on the local 1.5B model, <b>three of four such questions came back
inverted</b>, each at groundedness 1.00:</p>

""" + _table(["Question", "The model said", "The provision says"], [
    ("Do I need NBA approval before applying for a patent?",
     "\"No, you do not need approval\"",
     "s.6(1): <i>\"No person shall apply for any intellectual property right "
     "&hellip; <b>without obtaining the previous approval</b> of the National "
     "Biodiversity Authority\"</i>"),
    ("Do I need permission before filing outside India?",
     "\"No &hellip; however you must comply with Section 39\"",
     "s.39: <i>\"<b>No person resident in India shall</b>, except under the "
     "authority of a written permit &hellip;\"</i>"),
    ("Do I need FDA approval to sell in the US?",
     "\"No, you do not need FDA approval\"",
     "FDA guidance p.8: <i>\"Any person who wishes to market a new drug in the "
     "United States <b>must submit an NDA and obtain Agency approval prior to "
     "marketing</b>\"</i>"),
]) + """

<p>A lexical contradiction test was tried first and does not work: every
statutory span carries both mandatory language and a proviso, so <i>shall</i>
and <i>except</i> appear together in all of them and discriminate nothing.
Measured across five such questions, the mandatory/exemption signature was
identical every time.</p>

<p><b>So the model is taken out of this class of question entirely.</b>
<code>turns_on_polarity()</code> claims first-person duty questions &mdash; "do
I need", "must I", "am I required", "is prior approval required" &mdash; and
routes them to the extractive answerer, which quotes the provision. The
interface says so: <i>"Quoted, not paraphrased &mdash; this question turns on
whether a duty applies."</i></p>

<p>The pattern is deliberately first-person, and the distinction is the
interesting part. <i>"What does the Nagoya Protocol require?"</i> asks what a
duty <b>contains</b>, which the model answers well and keeps. <i>"Can I patent
X?"</i> is answered by a prohibition, which the model also gets right.
Twenty-one tests pin exactly which questions the guard claims and which it must
leave alone.</p>

<div class="box">
<p class="last"><b>The lesson generalises, and it is the sentence to say out
loud:</b> a groundedness score is a <i>traceability</i> score, not a
correctness score. It says every sentence is tied to the cited text. It never
said the model kept the direction of the duty.</p>
</div>
"""


def ch_compiler(s: dict) -> str:
    rule_rows = [(f"<code>{rid}</code>", sev, lane, prov, ver)
                 for rid, sev, lane, prov, ver in s["rule_rows"]]
    return f"""
<h1>9 &nbsp; The compliance compiler</h1>
<p class="kicker">RULES &middot; OBLIGATIONS &middot; JURISDICTIONS &middot; C-BOM</p>

<p class="lead"><b>In:</b> a formulation &mdash; ingredients in any Indian
language or script, process, dosage form, indications, marketing claims, target
markets, filing intent. <b>Out:</b> a Compliance Bill of Materials &mdash;
every statutory duty triggered, every blocker with the exact provision that
causes it, the minimum change that clears each blocker, and a jurisdiction
matrix. Signed, versioned, diffable, and reproducible byte for byte.</p>

<h2>9.1 &nbsp; Law as data</h2>

<p>A rule is YAML: a <code>when</code> predicate over facts, a severity, a
lane, a statement template, one or more citations each with a verbatim
<code>anchor</code>, an optional obligation, and autofixes that declare which
facts they set. It is reviewable by a domain expert who does not read Python,
and it is versioned in git alongside the code.</p>

<p><b>The load step is a gate, not a parse.</b> A rule is admitted only if
every citation resolves to a real extracted provision <i>and</i> every anchor
is a verbatim substring of it. A rule failing either check is demoted to
UNVERIFIED and the engine refuses to let it emit &mdash; and that abstention is
printed in the report rather than hidden. An unverified rule can match the
facts perfectly and still emit nothing.</p>

{_table(["Rule", "Severity", "Lane", "Provision", "Status"], rule_rows)}

<p class="small">{s['rules_verified']} of {s['rules']} VERIFIED.
<code>python scripts/verify_provisions.py</code> re-extracts every anchor
directly from the source PDFs and fails on drift; 13 citations currently
re-verify with no drift, and the fourteenth resolves its citation from a fact
at emit time.</p>

<h2>9.2 &nbsp; Facts are tri-state, on purpose</h2>

<p>A fact is True, False, or <b>not yet known</b>. "No disease claim was made"
and "nobody has said whether a disease claim was made" are different
situations, and only one of them is safe to act on. An unestablished fact
cannot satisfy a condition &mdash; the engine abstains rather than defaulting.
A missing fact is <i>asked about</i>, never assumed.</p>

<h2>9.3 &nbsp; The moment the whole argument rests on</h2>

<p>Two rules fire on the same facts and cite <b>the same provision</b> with
opposite consequences:</p>

<pre>
[BLOCKER]     IN.PAT.S3P.TK_EXCLUSION      [PATENT lane]
              Patents Act, 1970 -- Section 3(p)
              ...excluded from patentability in India.

[OPPORTUNITY] REG.TRADITIONAL_USE_ASSET    [REGULATORY lane]
              Patents Act, 1970 -- Section 3(p), read as evidence of
              traditional use
              The same documented traditional use that excludes this
              composition from patentability is an evidentiary asset in
              the regulatory lane.
</pre>

<p>A chatbot answers one question at a time and never notices. A compiler
modelling both lanes over one citation graph cannot miss it, and
<code>tests/test_engine.py::test_same_provision_is_blocker_and_opportunity</code>
asserts it so it cannot silently regress.</p>

<p><b>And the trade-off runs both ways.</b> Applying
<code>ESTABLISH_SYNERGY</code> to clear the s.3(p) blocker also <i>removes</i>
the traditional-use opportunity. That is a strategic consequence the compiler
surfaces without being asked &mdash; and it is the kind of thing a founder pays
an advisor to notice.</p>

<h2>9.4 &nbsp; Autofix is a recompile, not a promise</h2>

<p><code>--autofix</code> applies each available fix to a <i>copy</i> of the
facts and <b>re-runs the rules</b>, then diffs the findings. It does not report
that the blockers cleared; it re-derives them and shows which ones actually
did. On the demonstration formulation, 4 blockers &rarr; 0, with the fixes
named in order and a new C-BOM digest.</p>

<h2>9.5 &nbsp; Obligations and the jurisdiction matrix</h2>

<p>The obligations step emits the obligations a set of findings triggers, each with the duty,
<b>who discharges it</b>, and <b>when</b> &mdash; because "Section 21 applies to
you" is not actionable and "agree benefit-sharing terms as a condition of the
NBA approval, before the application" is.</p>

<p>The jurisdiction step builds the jurisdiction matrix. Its most important behaviour is what it
does for a jurisdiction whose primary sources are not ingested: it prints
<code>ABSTAIN &mdash; primary-source corpus for this jurisdiction not
ingested</code> and names exactly what it would need. Inventing a US or EU
provision to fill that cell would be the very failure the system exists to
prevent.</p>

<h2>9.6 &nbsp; The C-BOM, and reproducibility</h2>

<pre>
python cli.py reproduce fixtures/triphala_classical.json --runs 10

  10 runs -> 1 distinct C-BOM digest(s)
  PASS -- reproducible build
</pre>

<p>The digest is taken over the findings, obligations, matrix and resolution
log &mdash; excluding wall-clock metadata, so ten identical runs produce ten
identical digests. It <i>includes</i> the as-of date and the law version,
which is correct: the same formulation under different law is a different
analysis, and the artifact should say so.</p>

<p>That property is what makes this a build artifact rather than a
conversation. It can be attached to a filing, diffed against last quarter's
run, and re-derived by a third party from the same inputs.</p>

<h2>9.7 &nbsp; Time travel</h2>

<p><code>cli.py timetravel &lt;fixture&gt; 2002-01-01 2004-01-01
2026-08-31</code> compiles the same formulation under the law as at several
dates. Rules carry <code>effective_from</code> / <code>effective_to</code> and
the engine honours them. Chapter 20 is candid about the limit of this: the
rule-level dating works, but provision-level commencement data is not yet in
the corpus.</p>
"""


def ch_classification(s: dict) -> str:
    return f"""
<h1>10 &nbsp; Classify before advising</h1>
<p class="kicker">THE PART MOST IP ASSISTANTS SKIP</p>

<p class="lead">This is not meant to be an IP chatbot. It is an
assistant that <b>classifies the formulation first</b>, "because intellectual
property for an Ayurvedic product is inseparable from how the product is
regulated".</p>

<p>It is right to. The IP posture of an Ayurvedic product is decided by which
regulatory category it falls into, not by what it contains. <b>The same three
herbs are unpatentable traditional knowledge as a classical churna and a
defensible invention as a standardised phytopharmaceutical fraction.</b> Same
plants, opposite advice.</p>

<h2>10.1 &nbsp; How it decides</h2>

<p>{s['categories']} categories, held as data in
<code>data/formulation_classes.yaml</code>, tested <b>in file order, narrowest
first</b> &mdash; and the order is the legal order. Drug-or-not is settled
before the purified-fraction question, because a phytopharmaceutical is a
species of drug, and a standardised extract in a face cream with no disease
claim is a cosmetic.</p>

<p>Six tri-state facts decide it: purified fraction, classical-text
formulation, authoritative ingredients, disease claim, cosmetic use, food
positioning. Facts are read off what the user already said; <b>only a genuinely
open fact is asked about, one at a time</b>, and a bare yes or no answers it.
That is minimum clarifying questions, literally. No
model is involved, and the decision is instant.</p>

<h2>10.2 &nbsp; The six categories and their postures</h2>

{_table(["Category", "IP posture"], [
    ("<b>Phytopharmaceutical drug</b>",
     "The strongest patent position of any category here. Standardisation, a "
     "defined fraction and a demonstrated effect are the facts that answer both "
     "the s.3(p) traditional-knowledge objection and the s.3(e) mere-admixture "
     "objection &mdash; because the claimed invention is no longer the "
     "traditional combination. Cost: a clinical evidence burden"),
    ("<b>Classical / generic ASU medicine</b>",
     "The weakest. Codified traditional knowledge, squarely within s.3(p), and "
     "TKDL exists to make that stick. The honest advice is 'you cannot patent "
     "this &mdash; protect the brand, or the region, instead'"),
    ("<b>Patent or proprietary ASU medicine</b>",
     "Intermediate. A claim to the combination alone invites both s.3(p) and "
     "s.3(e); a patent becomes arguable only on evidence of synergy"),
    ("<b>New / non-classical drug</b>",
     "Depends on what is novel &mdash; and the safety-and-effectiveness burden "
     "is the dominant constraint"),
    ("<b>Ayurveda Aahara / nutraceutical</b>",
     "Food positioning, FSSAI route. Declared without a citation, because the "
     "2022 Regulations are not in the corpus &mdash; and the answer says so"),
    ("<b>Cosmetic</b>",
     "No disease claim; a different licensing route entirely, and a common "
     "and expensive misclassification"),
])}

<p>Every category must state all three postures &mdash; what it
<b>requires</b>, its <b>IP</b> posture and its <b>ABS</b> posture &mdash; and
<code>tests/test_classification.py</code> enforces that. Every provision id in
the file is verified against the corpus at load by the same gate as a rule.</p>

<h2>10.3 &nbsp; The demonstration, in three turns</h2>

<pre>
Turn 1  "my churna contains amla, haritaki and bibhitaki and I market it
         as 'cures diabetes'"

  -> Four facts read straight off the sentence: it is a churna, so not a
     purified fraction; a disease claim was made; not cosmetic; not food.
     ONE question remains, and it is asked:

     "Is both the formula and the method of preparation taken from a
      classical text listed in the First Schedule, or is the combination
      your own?"

Turn 2  "no"       -> asks the single next question that would change the
                      answer: are all the ingredients named in the
                      authoritative books?

Turn 3  "yes"      -> DECIDED: Patent or proprietary ASU medicine
                      Requires -- licensed as an ASU drug; where the
                        indication is not a textual one, safety and
                        effectiveness data are required
                      IP       -- intermediate; a patent is arguable only
                        on evidence of synergy
                      ABS      -- s.6(1), s.7 and s.21 apply, and
                        s.10(4)(d)(D) requires source and geographical
                        origin of each biological material
                      Defined by: Drugs and Cosmetics Act, 1940 s.3 and
                        Drugs and Cosmetics Rules, 1945 r.158
</pre>

<p>Had the answer to turn 2 been <i>yes</i>, this would be a classical medicine
and the honest advice would be the opposite. <b>The category is the advice</b>,
and it took a millisecond because it is a decision table, not a model.</p>

<h2>10.4 &nbsp; A detail worth knowing, because it is a real bug class</h2>

<p>A pinned clause is used only when the clause body is substantive. Drugs and
Cosmetics Act s.3(h) reads <i>"patent or proprietary medicine means,&mdash; (i)
in relation to Ayurvedic&hellip;"</i>, so the clause splitter cuts at that
"(i)" and the pin quoted 45 characters that said nothing. A pin yielding under
150 characters now falls back to the section and drops the pin from the label,
rather than citing a clause it is not really quoting.</p>
"""


def ch_graph(s: dict) -> str:
    st = s["graph_stats"]
    nodes = [(k, f"{v:,}") for k, v in st["by_node_kind"].items()]
    edges = [(k, f"{v:,}") for k, v in st["by_edge_kind"].items()]
    return f"""
<h1>11 &nbsp; The relational knowledge graph</h1>
<p class="kicker">MULTI-HOP REASONING RETRIEVAL STRUCTURALLY CANNOT DO</p>

<p class="lead">The questions an AYUSH founder actually asks are multi-hop, and
retrieval is single-hop by construction.</p>

<div class="box">
<p class="last"><i>"India is a Party to the Nagoya Protocol &mdash; so what do
<b>I</b> have to do?"</i> No single provision answers that. The answer is a
path: Nagoya Article 5 is given domestic effect by Biological Diversity Act
s.21; s.6 is the control point an applicant actually meets; the rule that fires
on your facts cites it; and <code>OBTAIN_NBA_APPROVAL</code> clears that rule.
A retriever scores those four nodes independently and returns whichever wins. A
graph walks the chain.</p>
</div>

<h2>11.1 &nbsp; What is in it</h2>

<p><b>{s['graph_nodes']:,} nodes, {s['graph_edges']:,} edges.</b></p>

{_table(["Node kind", "Count"], nodes)}
{_table(["Edge kind", "Count"], edges)}

<h2>11.2 &nbsp; Why it adds no new way to be wrong</h2>

<p>Almost every edge is <b>derived</b>, not authored, and therefore cannot be
wrong: a provision belongs to the instrument it was extracted from; a rule
cites what its own already-anchor-verified YAML declares; a concept governs the
provisions listed against it; a category is defined by the provisions that
define it; a rule reads the facts named in its <code>when</code> block; a
provision cross-refers to whatever section number appears in its own text; a
taxon carrying a schedule flag reaches the provision that flag belongs to.</p>

<p>The only <b>authored</b> edges are the {s['links']} cross-instrument links in
<code>data/graph_links.yaml</code> &mdash; treaty obligation to the domestic
provision that gives it effect &mdash; because "the Biological Diversity Act
implements India's CBD access-and-benefit-sharing obligations" is a legal
proposition, not a string match, and an assistant that asserts it must be able
to show why.</p>

<p>So every authored link is held to the rule-loader gate: <b>both endpoints must
resolve to real extracted provisions, and every declared anchor must be
verbatim in its endpoint.</b> A link that fails is dropped and reported.
<code>python cli.py graph --stats</code> prints the failures. Currently:
<b>{len(s['graph_problems'])}</b>.</p>

<p class="small"><b>What these edges do not say.</b> <i>implemented_by</i> means
the domestic provision is the route through which the international obligation
has effect in India. It does not make the two interchangeable, and the graph
never lets an answer cite them as one authority &mdash; the jurisdiction
pre-filter still separates the layers. A walk crossing the boundary says so,
every time, because "India is a Party to Nagoya" and "you can sue on Nagoya in
Delhi" are very different statements.</p>

<h2>11.3 &nbsp; Two design decisions that were wrong first</h2>

<h3>Containers are never walked through</h3>
<p>An instrument holds every one of its provisions, so allowing a walk to pass
<i>through</i> one makes any two sections of the Patents Act two hops apart via
"is a provision of / contains" &mdash; a path that is true, useless, and
crowds out the real one. Containers can start or end a walk; they are never a
step in the middle of it. <b>Membership is not a relationship.</b></p>

<h3>A bare name means the instrument, not its first article</h3>
<p>"Nagoya Protocol" is a substring of the instrument title <i>and</i> of all 36
article labels. Unranked lookup returned Article 1 &mdash; and a walk from
Article 1 finds nothing, because the relationship hangs off Article 5. Lookup
is now ranked by node kind and then by label length; and it is deliberately not
fuzzy, because a graph query that matched loosely would walk from the wrong
node and render a confident, well-cited path between two things the user never
asked about.</p>

<h2>11.4 &nbsp; What it looks like</h2>

<pre>
you > how does the Nagoya Protocol connect to the Biological Diversity Act

Nagoya Protocol on Access to Genetic Resources...
  -> contains  ... -- Article 5
  -> is given domestic effect in India by
       The Biological Diversity Act, 2002 -- Section 21
       The Protocol's fair-and-equitable benefit-sharing obligation is
       discharged in India through Section 21, under which the National
       Biodiversity Authority determines benefit sharing as a condition
       of approval.
       [The_Biological_Diversity_Act_2002.pdf p.10]
  -> is a provision of  The Biological Diversity Act, 2002
  ! This walk crosses the India / international boundary. The layers are
    separate authorities: the treaty binds India as a State, the Indian
    provision is what binds you.
</pre>

<p>Instant, and <b>no model is in this path at all</b>. Every line is fixed
connective text over an edge note from the curated file or a provision heading
from the corpus &mdash; nothing here is generated, so nothing here can be
hallucinated. And a query with no path returns that as a real answer: <i>"the
corpus asserts no relationship between them, and I will not invent one."</i></p>
"""


def ch_orchestration(s: dict) -> str:
    return """
<h1>12 &nbsp; Agentic orchestration that is a plan</h1>
<p class="kicker">DELIBERATELY NOT AN AGENT THAT IMPROVISES</p>

<div class="box">
<p class="last"><b>The plan is deterministic. The tools are deterministic. The
composition is deterministic.</b> A model appears in exactly one place &mdash;
inside a retrieval step, phrasing an answer over spans it was handed, behind
exactly the same citation gate it was already behind.</p>
</div>

<h2>12.1 &nbsp; Why this shape, and not the usual one</h2>

<p>The ordinary agentic pattern hands a model a tool list and lets it decide
what to call, in what order, with what arguments, and then lets it write a
summary over everything it collected. Every one of those four freedoms is a new
way to be wrong, and <b>the last one is the worst</b>: a model summarising
across steps can blend authority from two jurisdictions into one confident
sentence, which is the single failure this whole system exists to prevent.</p>

<p>An agentic layer is only safe here if it cannot do that. So the composition
<b>assembles</b> sections rather than summarising across them, and no sentence
in the output spans two steps &mdash; there is no code path that writes across
sections.</p>

<h2>12.2 &nbsp; What orchestration actually buys</h2>

<p>Not autonomy. Three concrete things a single-shot pipeline cannot do:</p>

<h3>1. Cross-layer questions, answered without conflating the layers</h3>
<p><i>"What does the Nagoya Protocol require and what must I do in India under
the Biological Diversity Act?"</i> is one question with two answers under two
different authorities. Single-shot retrieval <b>must</b> pick one layer &mdash;
that is the pre-filter working exactly as designed. The orchestrator splits the
question at its own coordinator, assigns each half by the instruments it names,
runs each as a separate retrieval with its own gate and its own citations, and
presents them as separate sections with their own badges.</p>

<div class="warn">
<p class="last"><b>The first version of this was wrong, and instructively
so.</b> It appended "under Indian law" to the same string and sent it twice
&mdash; and <i>both copies came back from the international layer</i>, because
a matched concept had already decided the layer and a suffix cannot outvote it.
Two identical answers under two different badges is a <b>worse</b> failure than
not splitting at all: it looks like the separation is working when it is not.
So it is now a real decomposition, and a clause that will not decompose cleanly
is asked once and labelled with the layer it actually resolved to.</p>
</div>

<h3>2. Describe-and-ask in one turn</h3>
<p><i>"My churna contains amla, haritaki and bibhitaki &mdash; can I patent it
and sell it in the US?"</i> is a compile <b>and</b> two legal questions. The
compile runs first, because its output &mdash; the resolved taxa, the category,
the findings &mdash; is the context the questions need. And the ingredient list
is stripped from the retrieval query for the ask step: three plant names
dominate a query and drown the question the user actually asked.</p>

<h3>3. Relationship questions</h3>
<p>Routed to the knowledge graph rather than to the retriever, because they are a walk.</p>

<h2>12.3 &nbsp; The safety properties, stated as properties</h2>

""" + _table(["Property", "How it is guaranteed"], [
    ("<b>It always terminates</b>",
     "The whole plan is built before any step executes. There is no loop "
     "deciding whether to keep going, so the plan is finite the moment it is "
     "built &mdash; and can be printed with <code>--dry-run</code> before it "
     "runs"),
    ("<b>It is bounded</b>",
     "<code>MAX_STEPS</code> caps the plan as a list, not as a stopping "
     "condition. A twenty-part question yields at most six steps"),
    ("<b>It cannot merge jurisdictions</b>",
     "Composition assembles per-step sections; no sentence spans two steps"),
    ("<b>It is auditable</b>",
     "Every step records its tool, why the planner chose it, its arguments, "
     "elapsed time, layer, groundedness and citation count. The interface "
     "ships that trace in a collapsible block"),
    ("<b>It is deterministic to plan</b>",
     "The same question yields the same plan every time; a test asserts it"),
    ("<b>It is not a new default</b>",
     "The routing test is narrow &mdash; two or more retrieval or graph steps. "
     "An ordinary single question, a compile, or a follow-up keeps the simpler "
     "path it already had"),
]) + """

<h2>12.4 &nbsp; What a run looks like</h2>

<pre>
[1/2] Answer  ·  International layer -- treaty & foreign regulator
      ·  groundedness 0.67
      ... Nagoya Article 7 and Article 5, tagged CBD ...

[2/2] Answer  ·  India layer -- national law  ·  groundedness 1.00
      ... Biological Diversity Act s.3, quoted, not paraphrased ...

The sections above are separate authorities and were retrieved separately.
A treaty article binds India as a State; the Indian provision is what binds
you. They are not combined into a single answer here, and should not be
combined into one when you act on them.

PLAN -- 2 step(s), cap 6
  1. ask  (the question spans both layers; this half names the international
           instrument and is retrieved there)
       query: what does the Nagoya Protocol require for benefit sharing
  2. ask  (and this half names the Indian instrument, so the two authorities
           are never pooled into one answer)
       query: what must I do in India under the Biological Diversity Act

TRACE
  1. ask [INTL]  ok g=0.67  5.93s  3 citation(s)
  2. ask [IN]    ok g=1.00  0.03s  3 citation(s)
</pre>

<p class="small">Note step 2's 0.03 s: the polarity guard claimed <i>"what must
I do"</i> and quoted the provision instead of paraphrasing it. The two
mechanisms compose without either knowing about the other.</p>
"""


def ch_escalation(s: dict) -> str:
    return f"""
<h1>13 &nbsp; Escalation to a human IP facilitator</h1>
<p class="kicker">THE SYSTEM'S OWN LIMITS ARE THE BEST SIGNAL A PERSON IS NEEDED</p>

<p class="lead">This is not a "contact us" button. The system already knows
when it abstained, when a blocker has no available fix, when a taxon was
genuinely ambiguous, and when a category's governing instrument is not in the
corpus. Those are exactly the moments to hand over &mdash; and they are
<b>facts</b>, not judgements.</p>

<h2>13.1 &nbsp; Deterministic triggers</h2>

<p><b>No model decides whether to escalate.</b> Every trigger reads a fact the
system already computed for another purpose &mdash; which is the point: an
escalation trigger that needed its own inference would be a new way to be
wrong.</p>

{_table(["Trigger", "Meaning"], [
    ("BLOCKER_PRESENT", "The compile produced blockers that stop the filing or "
     "the claim as it stands"),
    ("NO_FIX_AVAILABLE", "A blocker has no autofix on these facts, so clearing "
     "it requires a judgement the rule engine cannot make"),
    ("ABSTAINED", "The assistant had no authority in the corpus for the "
     "question asked"),
    ("CLASSIFICATION_UNDECIDED", "The regulatory category is still open, and "
     "the category decides the whole IP posture"),
    ("CLASSIFICATION_UNCITED", "The category was decided, but the instrument "
     "governing it is not in the corpus"),
    ("AMBIGUOUS_TAXON", "An ingredient resolves to more than one species and "
     "the system refuses to pick"),
    ("TKDL_ADVERSE_OUTCOME", "The formulation resembles an application already "
     "refused, revoked or withdrawn on TKDL prior art"),
    ("FOREIGN_JURISDICTION", "A target market is outside the corpus, so its "
     "matrix row is an abstention"),
    ("FOREIGN_FILING", "Filing outside India is intended, engaging s.39 and "
     "the foreign-filing permit"),
    ("USER_REQUESTED", "You asked to be put in front of a person"),
])}

<p class="small">Lane tags (PATENT_LANE, ACCESS_LANE, &hellip;) are kept
separate from triggers and used only for routing. A lane says which office a
finding belongs to; it is never a reason a human is needed. Mixing the two put
the string "ACCESS_LANE" in front of the user as an explanation, which is how
the distinction was found.</p>

<h2>13.2 &nbsp; A routing table with a statutory basis</h2>

<p>{s['routes']} institutional routes in <code>data/facilitators.yaml</code>,
{s['routes_cited']} of them carrying the provision that establishes the office
plus a verbatim anchor, verified at load exactly like a compliance rule. A route
whose anchor has drifted from the primary source is dropped and reported.</p>

{_table(["Route", "Established by"], [
    ("Registered patent agent", "Patents Act, 1970 &mdash; s.126"),
    ("National Biodiversity Authority", "Biological Diversity Act, 2002 &mdash; s.8"),
    ("State Biodiversity Board", "Biological Diversity Act, 2002 &mdash; s.22"),
    ("State Licensing Authority for ASU drugs",
     "Drugs and Cosmetics Rules, 1945 &mdash; r.154 (Form 25-D)"),
    ("Geographical Indications Registry", "GI Act, 1999 &mdash; s.5"),
    ("Trade Marks Registry", "Trade Marks Act, 1999 &mdash; s.3"),
    ("PPV&amp;FR Authority", "PPV&amp;FR Act, 2001 &mdash; s.3"),
    ("Copyright Office", "Copyright Act, 1957 &mdash; s.10"),
    ("Designs Office (CGPDTM)", "Designs Act, 2000 &mdash; s.3"),
    ("TKDL access cell", "TKDL documentation &mdash; <i>background material, "
     "not law</i>, and labelled so"),
    ("FSSAI", "Food Safety and Standards Act, 2006 &mdash; s.4"),
    ("Ministry of Ayush / AIIA facilitation desk",
     "<b>No citation</b> &mdash; an administrative route, not a statutory "
     "office, and the route says so"),
])}

<p><b>Contact details ship deliberately unset.</b> "Take this to a patent agent
registered under Section 126" is durable and checkable by anyone reading the
repository; a phone number a prototype invented is neither, and goes stale in a
month. A deploying department fills in its own desk, officer and service
level.</p>

<h2>13.3 &nbsp; The referral packet</h2>

<p>Plain text, so it survives being pasted anywhere and can be read on a phone.
It states: why this is being escalated, in sentences a founder can read; who to
take it to and what each office is <i>for</i>; what to bring; what the system
determined and on what authority; what it could <b>not</b> determine and why;
the obligations already identified; and every citation with its PDF and page.
Its reference id is a content digest, so the same session produces the same
reference twice and two referrals are distinguishable.</p>

<h2>13.4 &nbsp; Privacy is the design constraint here, not a feature</h2>

<div class="box">
<p><b>Nothing is transmitted.</b> There is no outbound call, no queue, no
ticket. The packet is rendered for the user to copy or export deliberately, and
nothing reaches disk unless the user names a file.</p>
<p class="last">Escalation is precisely where a careless implementation breaks
the privacy promise the rest of the system makes. <i>"We'll forward this to an
expert for you"</i> is how a proprietary formulation leaves the building.</p>
</div>

<h3>Redaction, and its stated limit</h3>

<p><code>--redact</code> removes the product name, the ingredient names as the
user typed them, and their resolved botanical names &mdash; from <b>every
line</b> of the packet, applied once at the end rather than at each source,
because the source that gets forgotten is the one that leaks.</p>

<p class="small"><b>Redacting only the resolution log is not redaction</b>, and
a test proves it: a rule statement interpolates the resolved taxa &mdash;
<i>"the invention is based on biological resources obtained from India (Emblica
officinalis, Terminalia bellirica&hellip;)"</i> &mdash; so the recipe walks
straight back into the brief through the findings.</p>

<p>And the banner says what redaction does <b>not</b> remove: the findings
still state the formulation's legal characteristics, for example that it
matches a documented classical combination, because a referral without those is
not actionable. A privacy claim a user over-reads is worse than one they can
calibrate.</p>
"""


def ch_multilingual(s: dict) -> str:
    return """
<h1>14 &nbsp; Multilingual delivery and the terminology lock</h1>
<p class="kicker">MULTILINGUAL THAT DOES WORK, NOT DECORATION</p>

<h2>14.1 &nbsp; RESOLVER: names before law</h2>

<p>A vaidya types <b>&#2327;&#2369;&#2337;&#2370;&#2330;&#2368;</b> or
<b>Amrutha</b> or <b>Giloy</b> or <b>Guduchi</b> or <b>gulvel</b>; all five land
on <i>Tinospora cordifolia</i> <b>before any legal reasoning runs</b>, because
the statutory schedules are keyed on botanical names. Resolution order is exact
&rarr; transliteration-normalised &rarr; fuzzy (propose only) &rarr;
escalate.</p>

<p>It refuses to guess where guessing would be wrong. <b>Brahmi</b> resolves to
neither <i>Bacopa monnieri</i> nor <i>Centella asiatica</i> and raises a warning
naming both, with the fix <code>CONFIRM_TAXON_WITH_USER</code>. An unrecognised
ingredient likewise raises a warning rather than a guess.</p>

<h2>14.2 &nbsp; Detection, and where translation stops</h2>

<p>Language is detected by Unicode block first &mdash; unambiguous for the
Indic scripts &mdash; and then by a small, high-precision function-word test
for romanised Indic typed on a QWERTY keyboard, which is how a great many users
actually write Hindi. Eleven languages: Hindi, Tamil, Telugu, Kannada,
Malayalam, Bengali, Gujarati, Punjabi, Odia, Urdu and English.</p>

<p>The corpus is English, so an Indic-script query is <b>translated to English
for retrieval only</b> &mdash; never for the answer, never cited. And the
concept lexicon carries Devanagari and Tamil entries and is checked <i>first</i>,
so <i>&#2325;&#2381;&#2351;&#2366; &#2350;&#2376;&#2306;
&#2327;&#2367;&#2354;&#2379;&#2351; &#2325;&#2366;
&#2346;&#2375;&#2335;&#2375;&#2306;&#2335; &#2325;&#2352;&#2366;
&#2360;&#2325;&#2340;&#2366; &#2361;&#2370;&#2305;</i> is answered with no
translation model in the loop at all: the lexicon matches and the resolver
turns &#2327;&#2367;&#2354;&#2379;&#2351; into <i>Tinospora cordifolia</i>.</p>

<h2>14.3 &nbsp; The terminology lock</h2>

<p>The answer comes back in the user's language, under a lock that overrides
the translator:</p>

<ul>
<li><b>Section numbers, rule numbers, form numbers, Act names and years are
never translated.</b></li>
<li><b>Terms of art</b> &mdash; <i>prior art</i>, <i>specification</i>,
<i>benefit sharing</i> &mdash; keep their English form with a short gloss.
Machine-translating "prior art" into Tamil produces a phrase no examiner
recognises, and a user who writes it on a form <b>has been actively harmed by
the translation</b>.</li>
<li><b>Quoted statutory text stays in its original language.</b> A translated
quote is a paraphrase, and a paraphrase is not authority.</li>
</ul>

<h2>14.4 &nbsp; What is honestly claimed, and what is not</h2>

<div class="box">
<p>Everything the <i>system</i> says in its own voice &mdash; the framing, the
abstention, the "background, not law" warning, the classification questions
&mdash; is in the user's language, from a hand-written table, deterministically.
That part cannot degrade, because no model produces it.</p>
<p class="last">The <i>model's explanation</i> is localised only when a model
that can actually write the language is installed. With the 1.5B model that
ships for speed, the answer <b>says so in the user's language</b> rather than
emitting plausible-looking nonsense. That is one command away
(<code>ollama pull gemma3:4b</code>), and it is the honest trade.</p>
</div>

<p><b>Bhashini carries both directions when it is configured.</b> Its
IndicTrans2 models are better at these pairs than anything that fits in the
local range, and the query-translation step is where the small local models
fail worst and most silently. It is off unless credentials are set, because it
is the one path in this system that sends text off the machine; the health
endpoint and the UI status line report which state it is in. Its output faces
the same four guards as a local model's, and the immutable tokens are masked
before the text is sent so the terminology lock holds by construction rather
than by inspection &mdash; a good translator will faithfully render "Section
21" into Tamil, which is exactly what the lock forbids.</p>
"""


def ch_memory(s: dict) -> str:
    return """
<h1>15 &nbsp; Conversation memory, and what the score measures</h1>
<p class="kicker">TWO USER-VISIBLE DEFECTS, AND WHAT REPLACED THEM</p>

<h2>15.1 &nbsp; The confidence indicator could read 0.00 on text it displayed</h2>

<p>Groundedness was the fraction of sentences clearing the 0.55 entailment
threshold, divided by a denominator that <i>also</i> counted the sentences the
gate had dropped. But the gate <b>shows</b> a sentence at 0.34. So every
sentence landing between 0.34 and 0.55 was printed and scored nothing.</p>

<div class="warn">
<p class="last"><b>Measured.</b> "Can I patent a traditional ayurvedic
formulation" across three runs of the same model returned <b>0.750, 0.200 and
0.000</b> &mdash; and the 0.000 run still displayed two sentences that the gate
had judged supported enough to print.</p>
</div>

<p>Two defects, compounding:</p>

<ul>
<li>A metric whose <b>denominator includes sentences its own numerator refuses
to count</b> is not measuring the answer. It is reporting a pass-rate against
an invisible, stricter bar.</li>
<li>Collapsing a continuous measure to a binary <b>throws away exactly what a
confidence indicator exists to carry</b>. 0.54 and 0.00 are not the same
situation, and the old formula reported them identically.</li>
</ul>

<p><b>Groundedness is now the mean entailment of the sentences actually
shown</b>, measured against the spans of the provisions cited beneath them. It
answers the question a reader is actually asking: <i>how well is the text in
front of me carried by the provision it cites?</i> What the gate <b>removed</b>
is reported beside it as a separate count &mdash; a reader who cannot tell the
two apart has been given one number that means neither. The strict fraction is
still computed and available as <code>entailed_fraction</code>.</p>

<p class="small">Across the same three runs the question now returns 0.615,
0.592 and 0.595. It also no longer reaches 1.00 for a paraphrase &mdash; only
quotation does, and the extractive path is the one that quotes. That is
honest: a quotation is fully carried; a paraphrase is partially.</p>

<h2>15.2 &nbsp; It remembers the last three turns, and says what it assumed</h2>

<p><i>"What are their pros and cons"</i> has no noun in it. Retrieved cold it
scores nothing and the assistant abstains &mdash; on a question whose subject
the previous turn established perfectly well.</p>

<p>A follow-up is now resolved against the last <b>three substantive</b>
questions. Not the last three <i>messages</i>: a chain of pronouns would fill
the window and push the actual subject out of it, so follow-ups are skipped
when choosing the anchors. The expanded query carries the earlier questions
<b>and the statutory vocabulary of the concepts those turns matched</b> &mdash;
the same register bridge the concept lexicon provides within one turn, applied
across turns. A user says "GI", the statute says "geographical indication", and
that substitution is what lets the follow-up land on the provisions the
previous answer actually cited.</p>

<pre>
you > What's the difference between a patent, GI, and trademark for an
      Ayurvedic product?
      groundedness 0.46 · 1 dropped by the gate

you > what are their pros and cons
      Read as a follow-up to: "What's the difference between a patent,
      GI, and trademark for an Ayurvedic product?"

      cites GI Act s.9 · Trade Marks Act s.9 · Patents Act s.3
      groundedness 0.83
</pre>

<h3>Deciding what counts as a follow-up</h3>

<p>The test is whether a message <b>names anything at all</b>, not whether it
contains a pronoun. <i>"Can I advertise that my product cures diabetes"</i>
contains the word "that", matches the anaphora pattern, and is eight words
long &mdash; so on the pattern and the length alone it read as a follow-up,
which meant it could never be the <b>anchor</b> for the real follow-up that
came next. A bare <i>"why?"</i> then retrieved cold and abstained. It names
advertising, a product, curing and diabetes; it is a question in its own right.
That test is <code>subject_tokens()</code>, and there is a regression test for
exactly this sentence.</p>

<div class="box">
<p class="last"><b>The assumption is always printed.</b> Resolving a pronoun is
a guess, and a guess the user cannot see is one they cannot correct. Silently
answering the wrong earlier question is exactly the failure a confident chatbot
makes.</p>
</div>
"""


def chapters_two(s: dict):
    return [
        ("5 · System architecture", ch_architecture(s)),
        ("6 · The corpus", ch_corpus(s)),
        ("7 · Retrieval", ch_retrieval(s)),
        ("8 · The trust machinery", ch_trust(s)),
        ("9 · The compliance compiler", ch_compiler(s)),
        ("10 · Classify before advising", ch_classification(s)),
        ("11 · The knowledge graph", ch_graph(s)),
        ("12 · Agentic orchestration", ch_orchestration(s)),
        ("13 · Escalation to a human", ch_escalation(s)),
        ("14 · Multilingual delivery", ch_multilingual(s)),
        ("15 · Conversation memory and the score", ch_memory(s)),
    ]
