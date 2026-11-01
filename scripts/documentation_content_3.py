"""Chapters 16-24: the deployment case, the limitations, and the question bank."""
from __future__ import annotations

from scripts.documentation_content import _table


def ch_stack(s: dict) -> str:
    return f"""
<h1>16 &nbsp; Technology choices, and why each one</h1>
<p class="kicker">WHY THIS STACK RATHER THAN THE OBVIOUS ONE</p>

<p class="lead">The dependency list is five libraries plus a web server. That
is a deliberate result, not an accident of scope: every dependency in a system
that must run inside a regulated organisation's network is something a security review has to
clear.</p>

{_table(["Choice", "Why", "What was rejected, and why"], [
    ("<b>Local LLM under Ollama</b> (default "
     "<code>qwen2.5:1.5b</code>)",
     "Nothing leaves the machine. No API key, no network call, no vendor "
     "dependency, no per-query cost. It is the answer to the first question an "
     "manufacturer asks: why would a manufacturer paste a proprietary "
     "formulation into somebody else's API?",
     "A hosted frontier API. Better prose, but it makes the privacy story "
     "impossible and creates a per-query cost at national scale. The interface "
     "is swappable &mdash; <code>ANTHROPIC_API_KEY</code> enables a hosted "
     "backend behind the same gate &mdash; but it is not the default"),
    ("<b>1.5B parameters, not 8B</b>",
     "Measured on this machine (CPU-bound, no usable GPU): qwen2.5:1.5b "
     "<b>14 s</b>, llama3.2:3b 42 s, llama3.1:8b 79 s per answer. The model is "
     "a phrasing layer over text the retriever already found, so speed leads",
     "A 79-second pause is a broken experience regardless of how "
     "well the sentence reads. One environment variable switches it; on a GPU, "
     "use the 8B"),
    ("<b>Deterministic rule engine</b> for every legal outcome",
     "Auditable, reproducible, diffable, and it returns in ~30 ms. A finding "
     "can be traced to a YAML line and a gazette page",
     "An LLM deciding findings. It cannot be audited, cannot be reproduced, "
     "and cannot be defended to a regulator"),
    ("<b>LSA dense retrieval</b> (truncated SVD over TF-IDF)",
     "Real semantics learned from this corpus. Trains in about a second, needs "
     "no download, keeps the stack air-gapped, and adds no model weights to "
     "review",
     "A transformer embedding (BGE-M3, multilingual-e5) is better and is a "
     "drop-in replacement at one function. It was not shipped because it adds "
     "a ~2 GB download to an air-gapped install, and the measured bottleneck "
     "was register, not embedding quality (&sect;7.2)"),
    ("<b>PyMuPDF</b> for extraction",
     "Gives font size and glyph position, which is what separates a 9pt "
     "footnote from a section heading &mdash; the defect that silently "
     "overwrote real sections (&sect;6.3)",
     "pdfplumber / PyPDF2: plain text extraction loses the layout signals the "
     "footnote and two-column problems depend on"),
    ("<b>Pydantic</b> for the schema",
     "Makes an uncited finding <i>unrepresentable</i>, not merely discouraged. "
     "The validator is the guarantee",
     "Plain dataclasses. The guarantee would then be a convention"),
    ("<b>YAML for rules, concepts, categories, links and routes</b>",
     "Reviewable by a domain expert who does not read Python. A vaidya or a "
     "patent agent can audit the law without auditing the code &mdash; which "
     "is the only way this scales to more regimes",
     "Rules in Python. Faster to write, impossible to hand to a lawyer"),
    ("<b>FastAPI + server-sent events</b>",
     "Streaming matters when a local model takes tens of seconds. Citations "
     "stream FIRST, at ~0.1 s, so the authority is on screen while the model "
     "is still writing about it",
     "A blocking POST. Ninety seconds of blank screen reads as broken"),
    ("<b>A single HTML file for the UI</b>",
     "No build step, no <code>node_modules</code>, no bundler; the whole "
     "interface is auditable in one file and deployable by copying it",
     "React/Vue. A build toolchain is a supply-chain surface and a deployment "
     "dependency for very little gain here"),
    ("<b>BM25 in-process, no vector database</b>",
     "3,491 provisions is small. An in-process index removes a service, a "
     "port, a backup story and a failure mode",
     "Postgres+pgvector, Qdrant, Elasticsearch: all correct at 10&#8311; "
     "documents and all overhead at 10&#179;"),
])}

<h2>16.1 &nbsp; The full dependency list</h2>

<pre>
pydantic>=2.0      typed schema; the uncited-finding validator
pyyaml>=6.0        rules, concepts, categories, graph links, facilitators
pymupdf>=1.24      PDF extraction with font and position metadata
rapidfuzz>=3.0     taxon resolution, fuzzy tier (propose-only)
numpy>=1.26        the LSA index
fastapi>=0.110     HTTP API
uvicorn>=0.27      ASGI server
pytest>=8.0        tests
</pre>

<p>No vector database, no orchestration framework, no agent framework, no
embedding service, no cloud SDK. {s['loc']:,} lines of Python, of which
{s['test_loc']:,} are tests.</p>

<div class="box">
<p class="last"><b>On AI-generated code.</b> This was written with AI assistance,
as most software now is, and that is not a defence of anything &mdash; the
defence is that the design decisions in this document are ours and can be
argued line by line. Every non-obvious choice in the codebase carries a comment
saying <i>why</i>, and most of those comments name the specific failure that
forced it: the footnote that overwrote Section 3, the treaty that extracted to
zero provisions, the two words missing from the concept lexicon that cost two
whole regimes, the model that fabricated a quotation, the metric that reported
0.00 on text it had displayed. Those are not comments anyone can generate
without having hit the bug. Chapter 22 answers this question directly.</p>
</div>
"""


def ch_security(s: dict) -> str:
    return """
<h1>17 &nbsp; Security, privacy, reliability and load</h1>
<p class="kicker">EDGE CASES, FAILURE MODES, AND HEAVY DATA</p>

<h2>17.1 &nbsp; Privacy, by architecture rather than by policy</h2>

""" + _table(["Property", "How"], [
    ("<b>Nothing a user types reaches disk</b>",
     "Chat sessions are in-process and ephemeral. Restarting the server "
     "forgets them. There is no database, so there is no database to breach, "
     "subpoena, or forget to encrypt"),
    ("<b>No network egress at runtime</b>",
     "The model runs locally under Ollama. No API key, no telemetry, no "
     "outbound call. This can be verified with a packet capture rather than "
     "taken on trust"),
    ("<b>Escalation transmits nothing</b>",
     "The referral packet is rendered for the user to carry. There is no "
     "queue, no ticket, no send"),
    ("<b>Redaction removes the recipe</b>",
     "<code>--redact</code> strips product and ingredient names from every "
     "line of a referral while preserving the legal posture and every citation"),
    ("<b>The corpus is public law</b>",
     "The only bulk data at rest is primary-source legislation. There is no "
     "personal data to classify under DPDP"),
]) + """

<p class="small"><b>What is not built:</b> an audit log. Sessions are ephemeral
by design, which is a strong privacy position and a weak audit position. A
government deployment will need per-query audit under a stated retention
policy, and that is a deliberate deployment decision rather than a default
&mdash; see Chapter 18.</p>

<h2>17.2 &nbsp; Behaviour under edge cases</h2>

""" + _table(["Edge case", "Behaviour"], [
    ("Question outside the corpus (EPO, Japan, US patent law)",
     "Abstains instantly, names the regime and names what the corpus does "
     "hold. <b>No model call at all</b> &mdash; 0.0 s"),
    ("Retrieval too weak to rely on",
     "Abstains. The floor is set per authority rank, because a statutory "
     "section and a page of guidance prose score differently by construction"),
    ("An ingredient that resolves to nothing (e.g. 'red sanders')",
     "Warning plus the fix <code>CONFIRM_TAXON_WITH_USER</code>. It does not "
     "guess a species"),
    ("An ingredient with contested synonymy ('brahmi')",
     "Resolves to neither candidate, returns both, and raises a warning"),
    ("The model writes an unsupported sentence",
     "Dropped before display, with the drop count shown and the removed text "
     "quoted"),
    ("The whole draft fails the gate",
     "Falls back to quoting the retrieved provision verbatim"),
    ("A first-person duty question",
     "Never reaches the model; the provision is quoted"),
    ("<b>Ollama is down or absent</b>",
     "The assistant degrades to the extractive backend &mdash; quotation of "
     "the retrieved provision, instantly, with no model. The compile, graph, "
     "classification and escalation paths are <b>unaffected</b>, because none "
     "of them ever used a model"),
    ("A rule's anchor drifts from the source PDF",
     "The rule is demoted to UNVERIFIED at load and refused permission to "
     "emit; the abstention is printed"),
    ("A curated graph link or facilitator route fails verification",
     "Dropped and reported in <code>graph --stats</code> / "
     "<code>facilitators</code>"),
    ("An empty or malformed formulation",
     "Parses no ingredients and asks, rather than inventing a constituent that "
     "was never mentioned"),
    ("A twenty-part question",
     "The plan is capped at six steps before anything runs"),
]) + """

<h2>17.3 &nbsp; Reliability under load</h2>

<p>The honest framing: this is a <b>read-mostly, CPU-bound, stateless</b>
workload over a small immutable corpus, and that makes the scaling story
unusually simple.</p>

""" + _table(["Component", "Cost", "Scaling behaviour"], [
    ("Corpus + rules + indices",
     "~0.76 s + 1.07 s + 0.27 s at process start",
     "Paid once per worker. Immutable and shared, so N workers are N "
     "independent read-only copies"),
    ("Retrieval", "~8 ms", "Linear in corpus size; trivially parallel"),
    ("Compile (no model)", "~30 ms",
     "Pure function of the facts. Horizontally scalable without limit"),
    ("Graph path", "&lt; 0.1 ms", "BFS over 4,643 edges, in memory"),
    ("Classification / escalation / graph", "milliseconds",
     "No model, no I/O"),
    ("<b>LLM generation</b>", "<b>14 s (1.5B, CPU)</b>",
     "<b>The only real bottleneck.</b> Serialised per worker on CPU; batched "
     "and 10&ndash;50&times; faster on a GPU"),
]) + """

<div class="box">
<p class="last"><b>The load answer that matters:</b> the paths that must never
fail &mdash; compile, classify, graph, escalate, abstain &mdash; do not touch
the model at all, so they scale with CPU cores and are unaffected by generation
queueing. Under load, the system degrades to <i>quoting provisions instantly</i>
rather than to <i>timing out</i>. There is no shared mutable state, so a worker
can be killed and replaced at any time with no recovery step.</p>
</div>

<h2>17.4 &nbsp; Attack surface</h2>

<ul>
<li><b>Prompt injection.</b> The model never decides an outcome, and its
output is gated against the retrieved spans. The worst a crafted input achieves
on the ask path is a dropped sentence. The compile, classification, graph and
escalation paths have no prompt to inject into.</li>
<li><b>Corpus poisoning.</b> The corpus is built from PDFs in the repository
by a script; <code>verify_provisions.py</code> re-extracts every rule anchor
from those PDFs and fails on drift. Tampering with an extracted record without
tampering with the PDF is detected.</li>
<li><b>Input size.</b> Requests are bounded; the plan is capped; the ingredient
parser caps at fifteen items and rejects items over four words.</li>
<li><b>Dependency surface.</b> Eight libraries, no build toolchain, no
<code>node_modules</code>, no runtime download.</li>
</ul>
"""


def ch_deployment(s: dict) -> str:
    return """
<h1>18 &nbsp; Feasibility, deployment and scaling to national use</h1>
<p class="kicker">IS THIS DEPLOYABLE FOR A REAL DEPARTMENT</p>

<h2>18.1 &nbsp; Why the deployment shape is unusually favourable</h2>

<p>The properties that make government software hard are mostly absent here.
There is <b>no personal data</b> at rest, <b>no external dependency</b> at
runtime, <b>no database</b>, <b>no shared mutable state</b>, and the entire
knowledge base is <b>public primary legislation</b> that ships with the
artifact. What is left is a stateless read-mostly service over an immutable
index.</p>

<p>That means the same binary runs in all three deployment shapes an adopter
would actually want:</p>

""" + _table(["Shape", "Who it is for", "What it needs"], [
    ("<b>Air-gapped desktop</b>",
     "A manufacturer or patent agent with a formulation they will not put on "
     "anyone's network",
     "One machine. Ollama plus eight Python libraries. No network at all"),
    ("<b>On-premise, inside the department</b>",
     "AIIA, a State Licensing Authority, an NBA or SBB desk",
     "A container per worker behind a load balancer; a GPU node if generation "
     "latency matters. No egress rules to negotiate"),
    ("<b>National, cloud-hosted</b>",
     "AYUSH MSMEs, cultivators, practitioners, at scale",
     "The same containers, autoscaled. Sessions stay in-process, so workers "
     "are interchangeable and need no session affinity beyond a sticky cookie"),
]) + """

<h2>18.2 &nbsp; The staged path</h2>

<p>The build is deliberately staged. The stages below are
ordered by what unblocks the most users per unit of effort.</p>

<h3>Stage 1 &mdash; Corpus completion (weeks, not months)</h3>
<p>The named gaps are all public PDFs, and each is <b>one registry entry plus a
re-ingest</b> &mdash; the food layer and the 2023 Biological Diversity
amendment were closed exactly this way. What remains: the Designs Rules 2001,
the Madrid, Hague and Budapest treaties, and EU Directive 2004/24/EC. Each then
needs one
verification pass: check the provision count against the instrument's real
structure, and re-run <code>verify_provisions.py</code>. This is the single
highest-value work item, because it converts abstentions into answers.</p>

<h3>Stage 2 &mdash; Rule breadth</h3>
<p>The corpus for trade marks, geographical indications, plant varieties and
the ASU licensing route is <b>already ingested</b>; each regime needs its rules
written and verified. A rule is YAML with an anchor, so a domain expert can
draft one and the loader will refuse it if the anchor is wrong. This is where
the system scales <i>as an institution</i> rather than as software: the
bottleneck is expert review time, and the architecture is built so that expert
review does not require reading code.</p>

<h3>Stage 3 &mdash; Evaluation at credible scale</h3>
<p>Grow the gold set to 300+ <b>held-out</b> items written by people who have
not seen the concept lexicon, plus the three ablations. Chapter 20 explains why
the current 17/17 must not be quoted as an accuracy figure.</p>

<h3>Stage 4 &mdash; Institutional integration</h3>
<ul>
<li><b>Bhashini ASR and TTS</b> &mdash; translation is integrated already;
speech would reach the practitioners and cultivators who would rather talk than
type.</li>
<li><b>Live registry connectors</b> &mdash; InPASS, the GI Registry, the Trade
Marks register &mdash; behind the same citation discipline: a registry record
is rank-4 evidence with its own provenance, not a fact the model may assert.</li>
<li><b>Facilitator contact configuration.</b> The routes and their statutory
bases are already verified; a deploying department fills in its desks, officers
and service levels, and the escalation packet becomes a working referral.</li>
<li><b>Audit logging</b> under a stated retention policy, which is a
deliberate reversal of the current ephemeral default and should be a
department's decision rather than a developer's.</li>
</ul>

<h3>Stage 5 &mdash; Depth</h3>
<p>A cross-encoder NLI model to replace the lexical coverage path in the citation gate,
tuned on a labelled set; a transformer retriever where an air-gapped install is
not required; provision-level commencement data to make the temporal filter a
real guarantee rather than scaffolding.</p>

<h2>18.3 &nbsp; What scaling does <i>not</i> require</h2>

<div class="box">
<p class="last">No re-architecture. The corpus is immutable and shared; the
compile path is a pure function of its facts; sessions hold no server state
worth preserving. Scaling from one laptop to a national service is adding
workers and, if generation latency matters, adding GPUs &mdash; not changing
the design. The parts that would be hard to scale are precisely the parts that
were deliberately not built: there is no agent loop that can fail to terminate,
no vector database to shard, and no per-query API bill.</p>
</div>

<h2>18.4 &nbsp; Governance: keeping the corpus current</h2>

<p>The corpus has to keep current as the law
changes. The mechanism is in place and its limit is stated in Chapter 20.
Operationally: every record carries <code>retrieved_on</code> and its amendment
notes; adding or updating an instrument is a registry entry and a re-ingest;
and <code>verify_provisions.py</code> is the gate that catches an amendment
silently changing text a rule depends on. In a department deployment that
script belongs in CI, run on a schedule, so a drifted anchor becomes a ticket
rather than a wrong answer.</p>
"""


def ch_testing(s: dict) -> str:
    return f"""
<h1>19 &nbsp; How it was tested, and what broke</h1>
<p class="kicker">THE FAILURES ARE THE MOST USEFUL PART OF THIS DOCUMENT</p>

<h2>19.1 &nbsp; The test suite</h2>

<p><b>{s['tests']} automated tests, {s['test_loc']:,} lines.</b> They are not
mostly unit tests &mdash; the interesting ones are <i>invariants</i>, and they
exist because each pins a defect that had already shipped once.</p>

{_table(["Suite", "What it pins"], [
    ("<code>test_engine.py</code>",
     "Rule firing, autofix, and the same-provision blocker/opportunity pair "
     "that the whole design rests on"),
    ("<code>test_citation_units.py</code>",
     "A corpus invariant: an instrument titled <i>Rules</i> must number Rules, "
     "a treaty must number Articles, no instrument may mix units, and the id "
     "prefix must match the label the reader is shown. A source registered "
     "without its unit fails the suite rather than shipping a wrong citation"),
    ("<code>test_polarity_guard.py</code>",
     "21 tests pinning exactly which questions the guard claims and which it "
     "must leave alone"),
    ("<code>test_classification.py</code>",
     "Every category states all three postures; every provision id resolves"),
    ("<code>test_graph.py</code>",
     "Curated links verify; containers are never transited; a cross-layer walk "
     "is flagged; the graph is deterministic; sub-chunks are not nodes"),
    ("<code>test_escalation.py</code>",
     "Every route verifies; triggers are readable sentences not enum names; "
     "<b>redaction really removes the recipe</b>; the packet says nothing was "
     "transmitted"),
    ("<code>test_orchestrator.py</code>",
     "The plan is deterministic and bounded; a plain question stays one step; "
     "each section cites only its own layer; no sentence spans two steps"),
    ("<code>test_context.py</code>",
     "Follow-up resolution, the anchor-selection regression, and that "
     "groundedness is never 0.00 on displayed text"),
    ("<code>test_multilingual.py</code>",
     "Script detection, the terminology lock, taxon resolution across scripts"),
    ("<code>test_rag.py</code> / <code>test_llm.py</code>",
     "Retrieval, abstention, the citation gate's four exact-match paths"),
])}

<p>Beyond the suite, three commands are run before any claim is made:
<code>cli.py eval</code> (the gold set), <code>cli.py reproduce</code> (ten runs
&rarr; one digest), and <code>scripts/verify_provisions.py</code> (re-extract
every anchor from the PDFs and fail on drift).</p>

<h2>19.2 &nbsp; The failures that shaped the system</h2>

<p>Each of these was found by measurement, not by reasoning, and each changed
the design rather than being patched around.</p>

{_table(["Failure", "What it forced"], [
    ("<b>Retrieval scored 2/9 on the first question set.</b> Not a tuning "
     "problem &mdash; 'can I patent my family formulation' and 'what are not "
     "inventions' share no content words",
     "The concept lexicon: an explicit lay-to-statutory bridge, curated as "
     "data. It is now the highest-leverage file in the repository"),
    ("<b>Three of four duty questions came back with the polarity "
     "inverted</b>, each at groundedness 1.00",
     "The polarity guard, and the realisation that a groundedness score is a "
     "traceability score. A lexical contradiction test was tried first and "
     "does not discriminate at all"),
    ("<b>The model fabricated a quotation</b> &mdash; presenting words that "
     "appear nowhere in s.3(p) inside quotation marks",
     "Quotation marks get exact match. A fabricated quotation is worse than a "
     "bad paraphrase, because the reader cannot weigh it"),
    ("<b>The model named the 'Plant Variety Rights Act'</b> &mdash; plausible, "
     "adjacent, never retrieved, and invisible to a numeric check",
     "Named instruments take the exact-match path, with every distinctive word "
     "required"),
    ("<b>The Nagoya Protocol extracted to zero provisions.</b> Two-column "
     "typesetting interleaved, and the article number was deleted as a page "
     "number",
     "Per-page reading-order detection, and the habit of checking every "
     "provision count against the instrument's real structure"),
    ("<b>India Code footnotes overwrote real sections.</b> A 9pt footnote "
     "reading '3. Cl. (a) omitted by Act 33 of 2021' replaced Section 3",
     "Font-size and position filtering &mdash; and keeping the footnotes as "
     "amendment notes, because they carry commencement dates"),
    ("<b>The Drugs and Cosmetics Act and its Rules were one instrument.</b> "
     "Section numbering restarts at the boundary, so the Act's own definitions "
     "were swallowed into a record labelled 'Section 38', and every rule was "
     "cited as a section",
     "Two instruments split on a page range &mdash; and this was a "
     "prerequisite for classification, which depends on citing s.3(h) "
     "correctly"),
    ("<b>Two missing words in the lexicon cost two whole regimes.</b> No lay "
     "phrase for bare 'trademark' or bare 'GI'",
     "The trade-mark question <i>abstained</i> despite 168 ingested sections. "
     "Most 'the model is bad' symptoms are a missing lay phrase"),
    ("<b>The confidence indicator read 0.00 on text it had displayed</b>, and "
     "the same question returned 0.750 / 0.200 / 0.000 across three runs",
     "Groundedness became the mean entailment of what is shown, with the drop "
     "count reported separately (&sect;15.1)"),
    ("<b>A real question was misread as a follow-up</b> because it contained "
     "the word 'that', so it could never anchor the follow-up after it",
     "The follow-up test became 'does this message name anything', not 'does "
     "it contain a pronoun'"),
    ("<b>Cross-layer decomposition sent the same string twice</b> and both "
     "copies came back from the same layer",
     "A real decomposition &mdash; and the recognition that two identical "
     "answers under two different badges is worse than not splitting"),
    ("<b>The graph routed every path through instrument nodes</b>, making any "
     "two sections of an Act two useless hops apart",
     "Containers are never transited. Membership is not a relationship"),
    ("<b>Redaction leaked the recipe through the findings</b>, because rule "
     "statements interpolate the resolved taxa",
     "Redaction applied once, at the end, to every free-text line &mdash; and "
     "a test that fails if a taxon appears in a redacted packet"),
])}

<div class="box">
<p class="last"><b>What went wrong is on the record:</b> every one
of those is in the codebase as a comment next to the fix, and most are pinned
by a test. A project that cannot name its failures has either not measured or
is not telling you.</p>
</div>
"""


def ch_limits(s: dict) -> str:
    return """
<h1>20 &nbsp; Current limitations, stated plainly</h1>
<p class="kicker">WHAT THIS PROTOTYPE DOES NOT DO</p>

<p class="lead">This chapter exists because a limitation volunteered is
worth more than one a reader finds. Everything below is real, and none of it is
hidden elsewhere in the document.</p>

<h2>20.1 &nbsp; Evaluation</h2>

<div class="warn">
<p class="last"><b>17/17 is a smoke test, not an accuracy score.</b> The gold
set has seventeen items and the concept lexicon was written while looking at
them. It demonstrates that the pipeline works end to end; it does not measure
how well. The number that would mean something is the same measurement on
held-out items written by someone who has not seen the lexicon, plus the
dense-only / hybrid / hybrid+concepts ablation. Until then, no accuracy claim
should be made and none is made in this document.</p>
</div>

<h2>20.2 &nbsp; The generation layer is the weakest component</h2>

<p>A 1.5B model on CPU writes serviceable but not good prose, and on some
questions retrieval lands on the wrong section and the model writes a confident
wrong sentence over it. <b>The citations remain real and openable</b> &mdash;
that is what the gate protects &mdash; but the phrasing can drift. Known
examples, measured: asking directly what s.3(p) says retrieves ss.162/64/49 and
answers about revocation; "who can apply for a patent in India" answers about
foreign filing. The mitigations are a bigger model (one environment variable),
better retrieval for those phrasings, and the compile path, which uses no model
at all.</p>

<h2>20.3 &nbsp; Temporal filtering is scaffolding, not a guarantee</h2>

<p><code>in_force()</code> checks <code>effective_from</code> /
<code>effective_to</code>, and the pre-filter runs before scoring as the design
requires &mdash; but <b>no record currently carries either field</b>, so it
passes everything. 1,379 records carry <i>w.e.f.</i> dates in their amendment
notes, and a parser exists, but wiring it up naively would be <i>worse</i> than
leaving it: notes are collected per page, so a footnote dating one inserted
clause would date the whole provision, and an as-of query for 2004 would
exclude the whole of Patents Act s.3, in force since 1970. Closing this needs
provision-level commencement data. The rule-level dating that
<code>timetravel</code> uses does work.</p>

<h2>20.4 &nbsp; Corpus gaps that cost real answers</h2>

<ul>
<li><b>The 2002 and 2023 Biological Diversity texts are two records, not
one.</b> Both are ingested and an <code>AMENDED_BY</code> edge joins the
amended section to the section that rewrote it, so a reader is shown both. What
does not exist is a consolidated Act as amended &mdash; because nobody
published one, and synthesising it would mean citing a text Parliament never
enacted.</li>
<li><b>Madrid, Hague, Budapest; EU THMPD; case law; live registry records.</b>
Each part of the design brief.</li>
</ul>

<h2>20.5 &nbsp; Features in the design brief and not built</h2>

<ul>
<li><b>Bhashini speech.</b> Translation is integrated in both directions;
ASR and TTS are not, so the assistant reads and writes eleven languages but
does not yet listen or speak.</li>
<li><b>A manual jurisdiction toggle.</b> Routing is automatic and the layer is
badged, but the design calls for a "toggle" and there is no control.</li>
<li><b>Corpus version diffing.</b> Records are dated; there is no
"what changed between these two corpus versions" view.</li>
<li><b>An audit log.</b> Ephemeral sessions are a deliberate privacy choice and
a genuine audit gap.</li>
</ul>

<h2>20.6 &nbsp; Limits of the new layers</h2>

<ul>
<li><b>The graph's authored links stop at thirteen.</b> Madrid, Hague,
Budapest and the EU route each need their corpus ingested before a link could
be anchor-verified, and an unverified link is not admitted.</li>
<li><b>Orchestration decomposes on syntax, not meaning.</b> A cross-layer
clause is split at its own coordinator and each half assigned by the
instruments it names. A clause that will not decompose is asked once and
labelled &mdash; deliberately, because the alternative looked like separation
and was not.</li>
<li><b>The escalation directory ships without contact details.</b> The routes
and statutory bases are verified; the desks behind them are deployment
configuration.</li>
<li><b>The citation gate is a lexical gate, not a neural NLI model.</b> It is strict and
deterministic, and it will drop a correct paraphrase that shares few content
words with its source. The upgrade path is a cross-encoder at one function.</li>
</ul>

<h2>20.7 &nbsp; Deliberately out of scope</h2>

<p>Drafting patent specifications (the system produces skeletons and annexures,
never claims); legal advice; and outcome prediction. Each of those is either
someone's professional responsibility or a promise no evidence supports.</p>
"""


def ch_impact(s: dict) -> str:
    return f"""
<h1>21 &nbsp; Measurable impact</h1>
<p class="kicker">WHAT IS MEASURED, AND WHAT IS MODELLED</p>

<div class="warn">
<p class="last"><b>Read the two tables separately.</b> The first is measured on
this system. The second is a model built from stated assumptions and is
labelled as such. Presenting the second as if it were the first is the kind of
thing this project exists to avoid doing.</p>
</div>

<h2>21.1 &nbsp; Measured, on this machine</h2>

{_table(["What", "Measured", "How to reproduce"], [
    ("Full compliance analysis of a formulation",
     "<b>~30 ms</b>, no model involved",
     "<code>cli.py compile fixtures/triphala_classical.json</code>"),
    ("Blockers found on the demonstration formulation",
     "4 blockers, 3 warnings, 1 opportunity, 5 obligations, across all four "
     "lanes", "same command"),
    ("Autofix cycle: fix, recompile, prove",
     "4 blockers &rarr; 0, with a new digest",
     "<code>cli.py compile &lt;fixture&gt; --autofix</code>"),
    ("Reproducibility", "10 runs &rarr; 1 digest",
     "<code>cli.py reproduce &lt;fixture&gt; --runs 10</code>"),
    ("Citation drift", "13 anchors re-verified, 0 drift",
     "<code>scripts/verify_provisions.py</code>"),
    ("Abstention on an out-of-corpus question", "0.0 s, no model call",
     "ask about EPO opposition periods"),
    ("Answer with citations (local 1.5B, CPU)",
     "citations at ~0.1 s, prose at ~14 s", "any question in Chapter 23"),
    ("Multi-hop graph walk", "&lt; 0.1 ms",
     "<code>cli.py path &lt;a&gt; &lt;b&gt;</code>"),
    ("Corpus", f"{s['provisions']:,} provisions, {s['instruments']} instruments",
     "<code>cli.py rules</code>"),
    ("Runtime cost per query", "&#8377;0 &mdash; no API, no network",
     "packet capture"),
])}

<h2>21.2 &nbsp; Where the time actually goes today, and what changes</h2>

<p>The comparison that matters is not "chatbot vs this". It is <b>what an AYUSH
MSME does today</b> when it wants to know whether it can protect a
formulation.</p>

{_table(["Step today", "What it costs", "With this system"], [
    ("Work out which laws even apply",
     "Days of reading, or a paid consultation, and it is the step most "
     "founders get wrong",
     "One sentence describing the formulation. All four lanes are evaluated "
     "at once"),
    ("Find whether the composition is patentable",
     "Often discovered only after paying to file",
     "s.3(p) and s.3(e) findings with the provision text, immediately"),
    ("Discover the ABS precondition",
     "Frequently discovered <i>after</i> filing, when it is not correctable",
     "s.6(1) raised as a blocker <b>before</b> the application, with the fix "
     "and who grants it"),
    ("Check the marketing claim against the Schedule",
     "Often after the label is printed",
     f"Matched against {s['dmr']} scheduled conditions"),
    ("Decide the regulatory category",
     "Determines everything else, and is routinely assumed rather than decided",
     "Two clarifying questions, then the category with all three postures"),
    ("Find the right office to approach",
     "Trial and error",
     "A referral packet naming each office and the provision that establishes "
     "it"),
])}

<h2>21.3 &nbsp; An impact model &mdash; illustrative, from stated assumptions</h2>

<p class="small"><b>These are not measured figures.</b> They are arithmetic on
assumptions stated in full so that a reader can replace any of them. No field
study has been run; that is honest scope for a prototype and is listed as
future work.</p>

{_table(["Assumption (replaceable)", "Value used"], [
    ("Professional time to reach a first view on protectability",
     "2&ndash;4 hours of a patent agent's time"),
    ("Proportion of first-time AYUSH innovators who never seek that view "
     "because of cost or distance", "the majority &mdash; unquantified"),
    ("Time to produce the same four-lane analysis with this system",
     "under one second, plus the two clarifying questions"),
    ("Cost of discovering the s.6(1) ABS precondition after filing",
     "the filing itself, plus the delay"),
    ("Cost of a non-compliant label discovered after printing",
     "the print run, plus the recall"),
])}

<div class="box">
<p><b>The honest claim, and the one worth making:</b> the measurable effect is
not that this replaces a patent agent's judgement. It is that it moves the
<i>triage</i> step &mdash; which regimes apply, what is blocked, what is
missing, who to ask &mdash; from hours of professional time to under a second,
at zero marginal cost, and produces a brief that makes the professional hour
that follows substantially more useful.</p>
<p class="last">The second measurable effect is the one that matters
most: it makes the <b>ABS obligations</b> visible <i>before</i>
filing rather than after, which is the difference between a condition satisfied
and a right lost.</p>
</div>

<h2>21.4 &nbsp; How impact should actually be measured</h2>

<p>If this were deployed, these are the metrics worth instrumenting &mdash; and
none of them is a chatbot metric:</p>

<ul>
<li>Proportion of compiles where an ABS blocker was raised <b>before</b> a
filing decision.</li>
<li>Proportion of sessions reaching a decided regulatory category.</li>
<li>Abstention rate, and abstention <i>precision</i> &mdash; how often an
abstention was correct.</li>
<li>Citation-open rate: how often users actually open the provision behind an
answer. This is the real trust signal.</li>
<li>Escalation conversion: referrals generated, and how many reach the named
office.</li>
<li>Corpus coverage over time: abstentions attributable to a named missing
instrument, which is a work queue rather than a failure.</li>
</ul>
"""


def ch_qa(s: dict) -> str:
    def q(question, *paras):
        body = "".join(f"<p>{p}</p>" for p in paras)
        return f'<p class="q">{question}</p>{body}'

    return f"""
<h1>22 &nbsp; Anticipated questions, with answers</h1>
<p class="kicker">THE SCEPTIC'S QUESTION BANK</p>

<p class="lead">Answers are written to be said out loud in under a minute.
Where a question has a sharp version and a safe version, the sharp one is
given &mdash; because candour beats hedging.</p>

<h2>A &nbsp; Problem and differentiation</h2>

{q("What specific problem are you solving, and why does it matter in the real world?",
   "Protecting an Ayurvedic product means satisfying four bodies of law at "
   "once &mdash; patents, access-and-benefit-sharing, drug regulation and "
   "advertising &mdash; and getting any of them wrong is usually "
   "unrecoverable. Section 6(1) of the Biological Diversity Act makes NBA "
   "approval a <i>precondition to applying</i> for an IP right on an Indian "
   "biological resource; founders discover it after filing. Section 3(p) of "
   "the Patents Act excludes traditional knowledge; founders discover that "
   "after paying. The Drugs and Magic Remedies Schedule bans a diabetes claim; "
   "founders discover that after printing the label.",
   "The result is a double loss: legitimate "
   "Ayurvedic innovation is under-protected at home, while India's traditional "
   "knowledge stays exposed abroad. We compress the triage step &mdash; which "
   "regimes apply, what is blocked, what is missing, who to ask &mdash; from "
   "hours of professional time to under a second.")}

{q("How is this different from existing products or current practice?",
   "Four things exist today. A patent agent &mdash; authoritative, but costs "
   "money before you know whether there is anything worth drafting. TKDL "
   "&mdash; excellent defensive prior art, but it protects the commons, not "
   "the individual. Government PDFs &mdash; organised by instrument, when a "
   "founder's question spans four Acts they cannot name. And a general AI "
   "assistant &mdash; fluent, and will invent a section number without telling "
   "you.",
   "The difference is that this is a <b>compiler</b>, not a chatbot. Describe "
   "your formulation and it returns the statutory duties you have triggered, "
   "each blocker with the provision that causes it, and the minimum change "
   "that clears it &mdash; then re-runs the rules to prove which ones actually "
   "cleared. And a fabricated citation is structurally impossible: there is no "
   "code path from a rule to a finding that does not pass through the primary "
   "source text.")}

{q("Isn't this just ChatGPT with a system prompt?",
   f"No, and the compile is the proof. {s['provisions']:,} provisions ingested "
   f"from primary-source PDFs with page numbers, {s['rules']} deterministic "
   "rules all verified against the statutory text, and the compile path "
   "returns in about 30 milliseconds <b>without calling a language model at "
   "all</b>. The graph, the classifier and the escalation packet call no model "
   "either.",
   "The model does three things: parse messy input into a typed schema, "
   "phrase explanations of decisions the rule engine already made, and "
   "translate. It never decides a legal outcome. Turn Ollama off and the "
   "system still compiles, still classifies, still walks the graph, still "
   "escalates, and answers questions by quoting the provision.")}

{q("Why build your own approach rather than using standard tools &mdash; LangChain, a vector database, an agent framework?",
   "Because each of them would have made the guarantee we actually need "
   "impossible to state. Our claim is not 'it usually cites correctly' &mdash; "
   "it is that a finding without a citation cannot be serialised, a rule "
   "cannot cite a provision that was never extracted, and an anchor that is "
   "not verbatim in the source PDF fails at load. Those are four validators we "
   "wrote, in four places we control.",
   "A vector database at 3,491 documents is a service, a port and a backup "
   "story for no benefit. An agent framework would have given the model the "
   "one freedom we most needed to remove: summarising across steps, which is "
   "how two jurisdictions get blended into one confident sentence. We built "
   "the orchestrator deterministically for exactly that reason.")}

<h2>B &nbsp; Technology</h2>

{q("Why this specific tech stack?",
   "Local model under Ollama, because nothing may leave the machine &mdash; "
   "that is the answer to why a manufacturer would paste a proprietary "
   "formulation into this. A 1.5B model rather than 8B because we measured it: "
   "14 seconds versus 79 on this CPU, and the model is only a phrasing layer "
   "over text the retriever already found. PyMuPDF because it gives font size "
   "and glyph position, which is what separates a 9pt footnote from a section "
   "heading &mdash; without that, an India Code footnote silently overwrites "
   "Section 3. Pydantic because it makes an uncited finding unrepresentable "
   "rather than merely discouraged. YAML for the law because a vaidya or a "
   "patent agent has to be able to audit a rule without reading Python.",
   "Eight dependencies, no build toolchain, no vector database, no agent "
   "framework. Every one of those is something a security review "
   "would otherwise have to clear.")}

{q("Why LSA instead of a real embedding model?",
   "Honest answer: because it trains in a second, needs no download, and keeps "
   "the stack air-gapped &mdash; and because our measured bottleneck was not "
   "embedding quality. Retrieval scored 2 out of 9 on our first question set, "
   "and the failure was <i>register</i>: 'can I patent my family formulation' "
   "and 'what are not inventions' share no content words, and no embedding "
   "fixes that reliably. What fixed it was a curated lay-to-statutory concept "
   "lexicon.",
   "BGE-M3 is a drop-in replacement at one function, and we would ship it "
   "wherever an air-gapped install is not required. We say it is LSA rather "
   "than implying it is a transformer.")}

{q("Walk us through the architecture.",
   "Four layers. <b>Evidence</b>: 28 primary-source PDFs extracted into "
   "page-anchored provisions with authority ranks. <b>Verification</b>: the "
   "schema validator, the rule loader's corpus binding, and the citation gate's citation "
   "gate. <b>Reasoning</b>: the rule engine, the classifier, the retriever, "
   "the knowledge graph, the jurisdiction matrix, the escalation router. "
   "<b>Interface</b>: chat, CLI and HTTP.",
   "The organising rule is that data flows upward through gates and no layer "
   "may assert what a lower layer has not proved. On the ask path there are "
   "three places the request can end <i>before</i> the model is called: the "
   "polarity guard, the out-of-corpus check, and the weak-retrieval check. On "
   "the compile path the model is never called at all.")}

{q("Did you use AI-generated code, and can you defend every line?",
   "Yes, it was written with AI assistance &mdash; as most software now is "
   "&mdash; and that is not the interesting question. The interesting question "
   "is whether we can defend the design, and the answer is that every "
   "non-obvious decision in the codebase carries a comment naming the specific "
   "failure that forced it.",
   "The India Code footnote that overwrote Section 3. The Nagoya Protocol "
   "extracting to zero provisions because two-column typesetting interleaved "
   "and the article number was deleted as a page number. The model fabricating "
   "a quotation from s.3(p). Three of four duty questions coming back inverted "
   "at groundedness 1.00. A confidence score reading 0.00 on text it had "
   "displayed. Redaction leaking the recipe through the rule statements.",
   "Those are not comments anyone writes without hitting the bug. Ask us about "
   "any file and we will tell you what it does, why it is shaped that way, and "
   "what broke to make it that shape.")}

<h2>C &nbsp; Correctness and trust</h2>

{q("How do you know it isn't hallucinating?",
   "Three mechanisms, in order. Retrieval is restricted to the ingested "
   "corpus. Every drafted sentence is then verified against the retrieved "
   "statutory spans, and unsupported sentences are <b>dropped before you see "
   "them</b> &mdash; the interface shows the count and quotes what went. What "
   "survives gets a groundedness score. If the whole draft fails, it falls "
   "back to quoting the provision verbatim.",
   "Four checks take an exact-match path, and each was added because a real "
   "model failed it: numbers and section references, quoted text, named "
   "instruments, and the gate window equalling the prompt window. A fabricated "
   "quotation is worse than a bad paraphrase &mdash; a paraphrase the reader "
   "can weigh, a quotation they cannot.")}

{q("Your groundedness says 1.00. Does that mean the answer is correct?",
   "No, and this is the most important thing we learned. <b>A groundedness "
   "score is a traceability score, not a correctness score.</b> It says every "
   "sentence is carried by spans of the cited provision. It never said the "
   "model kept the direction of the duty.",
   "We measured it: three of four 'do I need X' questions came back "
   "<i>inverted</i> &mdash; including 'No, you do not need approval from the "
   "National Biodiversity Authority', against a section headed 'Application "
   "for intellectual property rights not to be made without approval', at "
   "groundedness 1.00. A lexical contradiction test does not help, because "
   "every statutory span carries both mandatory language and a proviso.",
   "So we took the model out of that class of question entirely. First-person "
   "duty questions are claimed by a guard and the provision is quoted instead. "
   "Duller, and correct.")}

{q("What happens when it doesn't know?",
   "It abstains and names the reason. Ask about EPO opposition periods and it "
   "returns instantly &mdash; no model call at all &mdash; saying it has no "
   "authority in the ingested corpus, that the question is about EPO law, and "
   "exactly what the corpus does cover.",
   "This is worth pausing on: the design brief lists <b>safe abstention "
   "on out-of-scope or uncertain queries</b> as an explicit evaluation "
   "criterion. The refusal is a requirement being met, not a limitation being "
   "confessed.")}

{q("Could it mix up Indian law and a treaty?",
   "It is prevented from doing so in two places. Retrieval picks one layer and "
   "<b>pre-filters</b> to it &mdash; before scoring, not after &mdash; so an "
   "answer cannot quote Biological Diversity Act s.21 and Nagoya Article 5 as "
   "one authority. And for a question that genuinely spans both, the "
   "orchestrator decomposes it and runs each half separately, with its own "
   "gate and its own citations; the composition assembles sections and never "
   "writes a sentence that spans two of them.",
   "Each treaty also carries a force note from the corpus: TRIPS reads 'binds "
   "India as a WTO Member; not directly enforceable in Indian courts'. That "
   "sentence is a property of the record, not something a model generated.")}

<h2>D &nbsp; Security, reliability and scale</h2>

{q("Does it need the internet? Where does my formulation go?",
   "Nothing leaves the machine. The model runs locally under Ollama &mdash; no "
   "API key, no telemetry, no outbound call, and you can verify that with a "
   "packet capture rather than taking our word for it. Chat sessions are "
   "in-process and ephemeral: <b>nothing you type is written to disk</b>, and "
   "restarting the server forgets it.",
   "That extends to the escalation feature, which is where it would be "
   "easiest to break the promise. The referral packet is generated for you to "
   "carry. There is no queue, no ticket, no send. And <code>--redact</code> "
   "strips the product name and every ingredient name from the whole packet "
   "while keeping the legal posture and every citation, so you can get a "
   "facilitator's view without disclosing the formulation at all.")}

{q("How does it behave under heavy load or on edge cases?",
   "The paths that must never fail &mdash; compile, classify, graph walk, "
   "escalate, abstain &mdash; do not touch the model at all, so they scale "
   "with CPU cores and are unaffected by generation queueing. Under load the "
   "system degrades to <i>quoting provisions instantly</i> rather than to "
   "timing out. There is no shared mutable state, so a worker can be killed "
   "and replaced with no recovery step.",
   "Edge cases are handled by refusing rather than guessing: an unrecognised "
   "ingredient raises a warning with the fix 'confirm the taxon with the "
   "user'; a contested name like <i>brahmi</i> returns both candidates and "
   "resolves to neither; a twenty-part question is capped at six planned steps "
   "before anything runs; and if Ollama is down the compile, graph and "
   "classification paths are entirely unaffected.")}

{q("Is this feasible to deploy at real scale for a government department?",
   "Unusually so, because the hard parts are absent. No personal data at rest, "
   "no external dependency at runtime, no database, no shared mutable state, "
   "and the whole knowledge base is public primary legislation that ships with "
   "the artifact. What is left is a stateless read-mostly service over an "
   "immutable index.",
   "The same build runs air-gapped on one desktop, on-premise inside a "
   "department, or autoscaled in the cloud. Scaling is adding workers &mdash; "
   "and GPUs if generation latency matters &mdash; not re-architecting. The "
   "parts that would be hard to scale are the ones we deliberately did not "
   "build: there is no agent loop that can fail to terminate, no vector store "
   "to shard, and no per-query API bill.")}

{q("How do you scale this from a prototype to national deployment?",
   "Five stages, in order of users unblocked per unit of effort. <b>One</b>: "
   "corpus completion &mdash; Madrid, Hague, Budapest, the Designs Rules "
   "2001, EU THMPD. Each is a public PDF, one registry entry and a re-ingest, "
   "and each converts abstentions into answers; the food layer and the 2023 "
   "Biodiversity amendment were closed exactly that way. <b>Two</b>: rule "
   "breadth for trade marks, GI, plant varieties, ASU licensing and the new "
   "food layer &mdash; the corpus for all five is already ingested.",
   "<b>Three</b>: a 300-item held-out gold set, because our current 17 is a "
   "smoke test. <b>Four</b>: institutional integration &mdash; Bhashini "
   "speech, live registry connectors, facilitator contact configuration, and "
   "audit logging under a stated retention policy. <b>Five</b>: depth &mdash; a cross-encoder "
   "NLI gate and provision-level commencement dates.",
   "The important structural point: stage two scales as an <i>institution</i>, "
   "not as software. A rule is YAML with an anchor the loader verifies, so a "
   "domain expert can draft one without reading code &mdash; and the loader "
   "refuses it if the anchor is wrong.")}

<h2>E &nbsp; Evidence, testing and limits</h2>

{q("How did you test it, and what failed during the build?",
   f"{s['tests']} automated tests, plus three commands we run before making "
   "any claim: the retrieval gold set, a ten-run reproducibility check, and a "
   "script that re-extracts every rule anchor from the source PDFs and fails "
   "on drift.",
   "What failed is the more useful answer. Retrieval scored 2/9 at first "
   "&mdash; a register problem, not a tuning problem. Three of four duty "
   "questions came back with the polarity inverted. The model fabricated a "
   "quotation and named an Act that was never retrieved. The Nagoya Protocol "
   "extracted to zero provisions. India Code footnotes overwrote real "
   "sections. Two missing words in the concept lexicon meant the trade-mark "
   "question abstained despite 168 ingested sections. Our confidence score "
   "reported 0.00 on text it had chosen to display. And our first redaction "
   "leaked the recipe back through the rule statements.",
   "Every one of those is a comment in the codebase next to the fix, and most "
   "are pinned by a test so they cannot silently return.")}

{q("What are the current limitations?",
   "Four that matter. <b>Our 17/17 gold set is a smoke test, not an accuracy "
   "score</b> &mdash; it has seventeen items and the concept lexicon was "
   "written while looking at them; the number that would mean something is a "
   "held-out set, and that is the top of our roadmap. <b>The generation layer "
   "is the weakest component</b>: on some phrasings retrieval lands on the "
   "wrong section and a 1.5B model writes a confident wrong sentence over it "
   "&mdash; the citations stay real and openable, but the phrasing drifts.",
   "<b>Temporal filtering is scaffolding, not a guarantee</b>: the mechanism "
   "runs before scoring as it should, but no record yet carries commencement "
   "data, so it passes everything &mdash; and wiring it up naively would be "
   "worse than leaving it, because a footnote dating one clause would date the "
   "whole provision. <b>And the citation gate verifies support, not "
   "composition</b>: a small model can weld two retrieved provisions into one "
   "claim, every phrase of which the spans carry. We report groundedness per "
   "answer rather than hiding it.",
   "Also not built, and in the design brief: Bhashini speech, a "
   "manual jurisdiction toggle, corpus version diffing, and an audit log.")}

{q("Your retrieval scores 1.00. Isn't that suspiciously perfect?",
   "It is, and we say so before anyone asks. Seventeen items, and the concept "
   "lexicon was written while looking at them &mdash; so it demonstrates the "
   "pipeline works end to end and measures nothing about how well. We make no "
   "accuracy claim anywhere in our documentation, and the honest number is the "
   "one we have not got yet: the same measurement on held-out questions "
   "written by someone who has not seen the lexicon, plus the dense-only "
   "versus hybrid versus hybrid-plus-concepts ablation.")}

{q("What is the measurable impact?",
   "Measured, on our machine: a full four-lane compliance analysis in about 30 "
   "milliseconds with no model involved; an autofix cycle that takes 4 "
   "blockers to 0 and proves it by recompiling; ten runs producing one digest; "
   "zero rupees per query because there is no API.",
   "The honest impact claim is about triage, not replacement. It moves 'which "
   "regimes apply, what is blocked, what is missing, who do I ask' from hours "
   "of professional time to under a second at zero marginal cost, and produces "
   "a brief that makes the professional hour that follows far more useful. And "
   "it surfaces the ABS precondition <i>before</i> filing rather than after "
   "&mdash; the difference between a condition satisfied and a right lost.",
   "We deliberately do not put a rupee figure on that. We have run no field "
   "study, and a number we cannot defend would undercut everything else in "
   "this project.")}

{q("Is this legal advice?",
   "No, and we say it out loud rather than only in a footer: this is "
   "informational compliance analysis generated from primary statutory "
   "sources. It does not replace a registered patent agent or an advocate "
   "&mdash; which is precisely why the escalation path exists and why it names "
   "the provision that establishes each office it points you to.")}

<h2>F &nbsp; Sharp questions</h2>

{q("What is the weakest part of your system?",
   "The generation layer, and it is not close. Everything deterministic "
   "&mdash; the compiler, the classifier, the graph, the escalation router "
   "&mdash; is auditable and reproducible. The 1.5B model writing prose over "
   "retrieved text is the component that can still produce a sentence we would "
   "not defend, and our architecture is shaped around containing it rather "
   "than trusting it: the gate drops what it cannot tie to a source, the "
   "polarity guard removes it from duty questions entirely, and no legal "
   "outcome passes through it at all.")}

{q("What would you do differently with three more months?",
   "In order: the held-out gold set, because everything else is unmeasurable "
   "without it. Then the Biodiversity Amendment 2023 and the FSSAI "
   "regulations, because those two gaps cost real answers today. Then rules "
   "for trade marks, GI and plant varieties, since the corpus is already "
   "ingested. Then a cross-encoder NLI gate to replace the lexical coverage "
   "path in the citation gate, tuned on a labelled set. Notably, none of that is "
   "re-architecture.")}

{q("Someone asks a question you know answers badly. What do you say?",
   "That it exposes the retrieval, not the gate. The citations are still real "
   "and you can open them and read the provision; what drifted was the "
   "phrasing on top. That is exactly why the compile path does not use the "
   "model at all. Then we show the compile.")}

{q("Why should we believe your numbers?",
   "Because they are re-derivable and we tell you the command. The corpus "
   "counts, the rule verification state, the graph size and the test count in "
   "this document are read from the running system by the build script "
   "&mdash; not typed into the prose &mdash; so the document cannot quietly "
   "disagree with the code. Every provision count was checked against the "
   "instrument's real structure: TRIPS genuinely has 73 articles, the Nagoya "
   "Protocol 36, the PCT 69. That check is how we found that the Nagoya "
   "Protocol was extracting to zero.")}
"""


def ch_demo(s: dict) -> str:
    return """
<h1>23 &nbsp; Demonstration run-sheet</h1>
<p class="kicker">SIX MINUTES, IN THIS ORDER</p>

<p class="lead">The order walks from "grounded answer" to "it refuses" to "it
compiles", which is the actual argument of the project. Every question below
has been run end to end and the observed behaviour is what is written.</p>

<h2>Pre-flight, five minutes before</h2>
<pre>
python cli.py serve                 # UI at http://127.0.0.1:8000
</pre>
<ol>
<li>Open it and <b>hard-refresh</b> (Ctrl+Shift+R).</li>
<li>Check the header reads the provision count and rules verified, and that
the dot is not red &mdash; red means Ollama is down. The app still works; it
quotes provisions extractively instead of writing prose.</li>
<li>Ask one throwaway question to page the model in.</li>
<li>Have this run-sheet on your phone, not on the projected screen.</li>
</ol>

<h2>The core run</h2>

""" + _table(["#", "Ask this", "What happens, and what to say"], [
    ("1", "<b>Can I patent a traditional ayurvedic formulation?</b>",
     "Cites Patents Act s.3 with a groundedness pill. <b>Click the "
     "citation</b> &mdash; the dialog opens the full provision scrolled to the "
     "sentence the answer leaned on, with the PDF name and page. <i>Say: "
     "\"the answer is not the product &mdash; the provision behind it is.\"</i>"),
    ("2", "<b>&#2325;&#2381;&#2351;&#2366; &#2350;&#2376;&#2306; "
     "&#2327;&#2367;&#2354;&#2379;&#2351; &#2325;&#2366; "
     "&#2346;&#2375;&#2335;&#2375;&#2306;&#2335; &#2325;&#2352;&#2366; "
     "&#2360;&#2325;&#2340;&#2366; &#2361;&#2370;&#2305;</b>",
     "Cites s.3(p), shows <i>giloy &rarr; Tinospora cordifolia</i> and a Hindi "
     "pill. <i>Say: \"the question was Hindi, the statute is English, and the "
     "plant name had to become a botanical taxon before either could be "
     "searched. This one never went near a translation model &mdash; the "
     "concept lexicon carries it in Hindi.\"</i>"),
    ("3", "<b>what is the EPO opposition period</b> &nbsp;&#9733;",
     "<b>Instant</b> abstention, no model call. It names the regime and names "
     "what the corpus does hold. <i>Say: \"that is the difference between a "
     "system with a corpus and a system with a vibe &mdash; and the problem "
     "statement scores safe abstention explicitly.\"</i>"),
    ("4", "<b>my churna contains amla, haritaki and bibhitaki and I market it "
     "as \"cures diabetes\"</b> &nbsp;&#9733;&#9733;",
     "~30 ms, no LLM. Resolves all three to binomials; 4 blockers across all "
     "four lanes; the classification block asks the <b>one</b> question it "
     "still needs; an obligations table; a jurisdiction matrix. <i>Say: \"it "
     "stopped answering questions and started compiling.\"</i>"),
    ("5", "<b>apply the fixes</b>",
     "Blockers 4 &rarr; 0, fixes named in order, new digest. <i>Say: \"it "
     "didn't tell me they cleared &mdash; it re-ran the rules against the "
     "patched facts and showed me which ones actually did.\"</i>"),
    ("6", "<b>escalate</b>",
     "A referral packet: why, to whom, with the provision establishing each "
     "office, what it could not determine. Then <b>escalate without the "
     "formulation</b> &mdash; same posture, recipe gone. <i>Say: \"nothing was "
     "transmitted. And no model decided to escalate &mdash; a blocker exists "
     "and a category is open.\"</i>"),
    ("7", "<b>how does the Nagoya Protocol connect to the Biological Diversity "
     "Act</b> &nbsp;&#9733;",
     "A cited walk, instantly, no model. <i>Say: \"no single provision answers "
     "that, so no retriever can. That edge is anchor-verified against the "
     "primary source by the same gate as a rule.\"</i>"),
    ("8", "<b>What's the difference between a patent, GI, and trademark&hellip;</b> "
     "then <b>what are their pros and cons</b>",
     "The follow-up prints <i>\"Read as a follow-up to&hellip;\"</i> and cites "
     "all three regimes. <i>Say: \"'their' names nothing. It reaches back "
     "three substantive turns and carries the statutory vocabulary forward "
     "&mdash; and it prints what it assumed, because a guess you can't see is "
     "one you can't correct.\"</i>"),
    ("9", "<b>What is Ayurveda?</b>",
     "A real answer, under a heading reading <b>\"Background material (not "
     "law)\"</b>. <i>Say: \"same corpus, different authority rank. It will not "
     "let a primer stand in for a statute.\"</i>"),
]) + """

<h2>Safe backup questions, all measured</h2>

""" + _table(["Question", "What comes back"], [
    ("What does Section 7 of the Biological Diversity Act require?",
     "Quotes the prior-intimation duty correctly"),
    ("I am a vaidya, do I need to inform the state biodiversity board",
     "Correct &mdash; and it applies the s.7 proviso that exempts practitioners"),
    ("Must I disclose the source and geographical origin of biological "
     "material in my patent specification?", "Yes; cites Patents Act s.10"),
    ("what does the Nagoya Protocol require for benefit sharing",
     "International layer badge; Nagoya Articles 7 and 5, tagged CBD &mdash; "
     "and <i>not</i> BDA s.21, which is the point"),
    ("is India obliged under TRIPS to allow patents on plants",
     "TRIPS Article 27, with the force note about direct enforceability"),
    ("Do I need approval from the National Biodiversity Authority before "
     "applying for a patent?",
     "The polarity guard claims it: the provision is quoted, and the footer "
     "says <i>\"Quoted, not paraphrased\"</i>"),
    ("my formulation contains sarpagandha, ashwagandha and giloy and I want to "
     "patent it abroad",
     "Adds a Patents Act s.39 blocker &mdash; the engine reacting to filing "
     "intent, not just ingredients"),
    ("my taila contains kuth, red sanders and ashwagandha",
     "'red sanders' resolves to nothing and raises a warning with "
     "<code>CONFIRM_TAXON_WITH_USER</code> rather than guessing"),
]) + """

<div class="warn">
<p><b>Two ways to fumble the compile, both avoidable.</b></p>
<p>The marketing claim <b>must be in quotes</b>. "sell it as a cure for
diabetes" without quotes parses no claim and the advertising lane will not
fire.</p>
<p class="last">The ingredient list needs a trigger word &mdash;
<i>contains</i>, <i>containing</i>, <i>made of</i>, <i>with</i> &mdash;
followed by at least two ingredients.</p>
</div>

<h2>If something breaks</h2>

<ul>
<li><b>Red dot, answers arrive as bare quotations.</b> Ollama is down. Run
<code>ollama serve</code>. Say so rather than restarting the demo &mdash; the
degradation <i>is</i> a feature and the compile path is unaffected.</li>
<li><b>First question hangs for 30 seconds.</b> The model is paging in. The
elapsed counter is ticking, so narrate the pre-flight instead of clicking
again.</li>
<li><b>The page is inert.</b> Hard-refresh; a single JavaScript syntax error
disables the whole script including the suggestion chips.</li>
<li><b>Everything is broken.</b> <code>python cli.py serve</code> in a fresh
terminal. The corpus and rules load from disk in seconds and no state is lost,
because there was never any state on disk to lose.</li>
</ul>
"""


def ch_appendix(s: dict) -> str:
    return f"""
<h1>24 &nbsp; Appendices</h1>
<p class="kicker">REPOSITORY MAP, COMMANDS, GLOSSARY, SOURCES</p>

<h2>A &nbsp; Repository map</h2>

<pre>
Dataset/              {s['pdfs']} primary-source PDFs ({s['dataset_mb']} MB), shipped
corpus/               generated -- rebuild, never hand-edit
  provisions.jsonl      {s['provisions']:,} page-anchored provisions
  tkdl_outcomes.jsonl   {s['tkdl']} real adverse patent outcomes
  dmr_schedule.json     {s['dmr']} scheduled diseases

data/                 curated, reviewable by a domain expert
  legal_concepts.yaml       {s['concepts']} lay-to-statutory concepts
  formulation_classes.yaml  {s['categories']} regulatory categories
  taxa.jsonl                {s['taxa']} taxa with multilingual synonyms
  graph_links.yaml          {s['links']} anchor-verified treaty->domestic links
  facilitators.yaml         {s['routes']} escalation routes

sources/     extraction, BM25, prior art, schedules
compliance/       the rule engine + rules/*.yaml ({s['rules']} rules)
citations/     the citation gate
classification/ regulatory classification
graph/   the knowledge graph
planner/       the orchestrator
escalation/     escalation to a human
jurisdictions/        the jurisdiction matrix
cbom/        the click-to-source HTML report
core/        schema, compiler, resolver, language, localisation
rag/         retrieval, concepts, answers, chat, streaming, translation
web/         chat.html -- the whole UI, one file, no build step
tests/       {s['tests']} tests
fixtures/    10 worked formulations
scripts/     verification, and this document's build script
</pre>

<h2>B &nbsp; Command reference</h2>

<pre>
# build
pip install -r requirements.txt
ollama pull qwen2.5:1.5b          # or llama3.1 if you have a GPU
python sources/ingest.py          # PDFs  -> corpus/provisions.jsonl
python sources/priorart.py        # TKDL  -> corpus/tkdl_outcomes.jsonl
python sources/schedules.py       # DMR   -> corpus/dmr_schedule.json

# run
python cli.py serve               # web chat UI
python cli.py chat                # the same, in the terminal
python cli.py ask "can I patent a classical formulation"

# the compiler
python cli.py compile <fixture>                 # full C-BOM
python cli.py compile <fixture> --autofix       # fix, recompile, prove
python cli.py compile <fixture> --html out.html # click-to-source report
python cli.py timetravel <fixture> 2002-01-01 2026-08-31
python cli.py reproduce <fixture> --runs 10     # same input -> same digest
python cli.py resolve <names...>                # any script -> taxon

# the newer layers
python cli.py graph --stats                     # nodes, edges, bad links
python cli.py graph "IN.BDA.2002::S6"           # one node's edges
python cli.py path "Nagoya Protocol" "The Biological Diversity Act, 2002"
python cli.py plan "<question>" --dry-run       # the plan, before it runs
python cli.py facilitators                      # the escalation directory
python cli.py escalate <fixture> --redact       # a referral, recipe withheld

# verification
python cli.py rules                             # rule verification status
python cli.py eval                              # retrieval gold set
python scripts/verify_provisions.py             # re-extract; fail on drift
python -m pytest -q                             # {s['tests']} tests

# this document
python scripts/build_documentation_pdf.py
</pre>

<h2>C &nbsp; Glossary</h2>

{_table(["Term", "Meaning"], [
    ("<b>ABS</b>", "Access and Benefit Sharing &mdash; the duties flowing from "
     "India's sovereignty over its biological resources"),
    ("<b>ASU</b>", "Ayurvedic, Siddha and Unani &mdash; the drug categories "
     "under the Drugs and Cosmetics Act"),
    ("<b>C-BOM</b>", "Compliance Bill of Materials &mdash; the compiler's "
     "signed, reproducible output artifact"),
    ("<b>Groundedness</b>", "Mean entailment of the sentences shown, against "
     "the spans of the cited provisions. A <i>traceability</i> score"),
    ("<b>Lane</b>", "PATENT, REGULATORY, BRAND or ACCESS &mdash; the strategic "
     "dimension a finding belongs to"),
    ("<b>Layer</b>", "IN or INTL &mdash; the jurisdictional answer-set a "
     "question is resolved against. Never mixed"),
    ("<b>NBA / SBB</b>", "National Biodiversity Authority; State Biodiversity "
     "Board"),
    ("<b>Provision</b>", "One extracted, page-anchored unit of an instrument "
     "&mdash; a Section, Rule, Article or page"),
    ("<b>TKDL</b>", "Traditional Knowledge Digital Library &mdash; India's "
     "defensive prior-art database"),
    ("<b>Taxon</b>", "The canonical botanical binomial an ingredient name "
     "resolves to"),
])}

<h2>D &nbsp; Primary sources</h2>

<p class="small">Every instrument in the corpus was obtained from an official
source and its provenance is recorded, because provenance is treated as part of
correctness. India Code (indiacode.nic.in) and the ministry registries
(ipindia.gov.in, copyright.gov.in) for Indian legislation; WIPO Lex for
time-limited signed copies of amended Indian rules; wto.org for TRIPS; cbd.int
for the Convention and the Nagoya Protocol; wipo.int for the PCT, its
Regulations and the GRATK Treaty 2024; fda.gov for the botanical-drug guidance;
WHO for the Ayurveda benchmarks and standard terminologies; and the Ministry of
Ayush for the TKDL documentation and the AYUSH primers.</p>

<div class="box">
<p class="last"><i>Informational compliance analysis generated from primary
statutory sources. This is not legal advice and does not replace a registered
patent agent or advocate. Every citation in this system can be opened at the
page it came from &mdash; and if it cannot, that is a defect and the
verification script will find it.</i></p>
</div>
"""


def chapters_three(s: dict):
    return [
        ("16 · Technology choices", ch_stack(s)),
        ("17 · Security, reliability and load", ch_security(s)),
        ("18 · Feasibility and scaling", ch_deployment(s)),
        ("19 · Testing, and what broke", ch_testing(s)),
        ("20 · Current limitations", ch_limits(s)),
        ("21 · Measurable impact", ch_impact(s)),
        ("22 · Q&A", ch_qa(s)),
        ("23 · Demonstration run-sheet", ch_demo(s)),
        ("24 · Appendices", ch_appendix(s)),
    ]
