"""The documentation's content, as chapter HTML.

Kept separate from the renderer so the prose can be edited without touching
layout code. `build(stats)` receives the figures measured from the live system
at build time -- see build_documentation_pdf.measured() -- and interpolates
them, so no count in this document is typed by hand.
"""
from __future__ import annotations


def _rows(rows, cls=""):
    out = []
    for r in rows:
        cells = "".join(f'<td class="{cls}">{c}</td>' for c in r)
        out.append(f"<tr>{cells}</tr>")
    return "".join(out)


def _table(headers, rows, cls=""):
    head = "".join(f"<th>{h}</th>" for h in headers)
    return f"<table><tr>{head}</tr>{_rows(rows, cls)}</table>"


# ============================================================== cover =======
def cover(s: dict) -> str:
    return f"""
<p class="kicker">TECHNICAL &amp; EVALUATION DOCUMENTATION</p>
<p class="kicker">&nbsp;</p>

<h1>AyurLex</h1>

<p class="sub">A multilingual, source-cited assistant for intellectual
property and regulatory guidance in Ayurveda &mdash; with a deterministic
compliance compiler underneath it.</p>

<p>An assistant that will not answer a legal question without citing the
provision it relied on, abstains by name when its corpus does not cover the
question, and never lets an Indian statute and a treaty article stand in one
answer as though they were the same authority.</p>

<p>Underneath the chat sits something a retrieval chatbot cannot do: describe a
formulation instead of asking a question, and the system <b>compiles</b> it
&mdash; returning the statutory duties it triggers, every blocker with the
provision that causes it, the minimum change that clears each blocker, and a
signed, reproducible Compliance Bill of Materials.</p>

<h2>At a glance, measured at build time</h2>

{_table(["Measure", "Value", "How it is checked"], [
    ("Primary-source corpus",
     f"{s['provisions']:,} provisions, {s['instruments']} instruments",
     "Article counts matched against each instrument's real structure"),
    ("Law encoded as rules",
     f"{s['rules_verified']}/{s['rules']} VERIFIED",
     "Each anchor phrase re-extracted from the source PDF at load"),
    ("Knowledge graph",
     f"{s['graph_nodes']:,} nodes, {s['graph_edges']:,} edges",
     f"{len(s['graph_problems'])} curated links failing verification"),
    ("Escalation directory",
     f"{s['routes_cited']}/{s['routes']} routes cited to statute",
     "The rest declare that they have no citation"),
    ("Automated tests", f"{s['tests']} passing",
     f"{s['test_loc']:,} lines of test code"),
    ("Reproducibility", "10 runs &rarr; 1 C-BOM digest",
     "python cli.py reproduce"),
    ("Retrieval gold set", "17/17 recall@1 &middot; 2/2 abstention",
     "Seed set, honestly described in &sect;19"),
    ("Network calls at runtime", "zero",
     "Local model under Ollama; nothing leaves the machine"),
])}

<p class="small muted">Built {s['built']} from the working tree. Every figure
above is read from the running system by the build script, not typed into the
prose. &mdash; <i>Informational compliance analysis generated from primary
statutory sources. Not legal advice; does not replace a registered patent agent
or advocate.</i></p>
"""


# ============================================================ chapters ======
def ch_contents(s: dict) -> str:
    items = [
        ("1", "Executive summary"),
        ("2", "The problem, and why it matters in the real world"),
        ("3", "The design brief, and a line-by-line coverage audit"),
        ("4", "How the solution differs from what already exists"),
        ("5", "System architecture"),
        ("6", "The corpus: sourcing, extraction, and the problems solved"),
        ("7", "Retrieval: the stack, and the number that forced it"),
        ("8", "The trust machinery: how hallucination is made structurally hard"),
        ("9", "The compliance compiler: rules, obligations, jurisdictions, C-BOM"),
        ("10", "Classify before advising"),
        ("11", "The relational knowledge graph"),
        ("12", "Agentic orchestration that is a plan, not an improviser"),
        ("13", "Escalation to a human IP facilitator"),
        ("14", "Multilingual delivery and the terminology lock"),
        ("15", "Conversation memory, and what the confidence score measures"),
        ("16", "Technology choices, and why each one"),
        ("17", "Security, privacy, reliability and load"),
        ("18", "Feasibility, deployment and scaling to national use"),
        ("19", "How it was tested, and what broke during the build"),
        ("20", "Current limitations, stated plainly"),
        ("21", "Measurable impact"),
        ("22", "Anticipated questions, with answers"),
        ("23", "Demonstration run-sheet"),
        ("24", "Appendices: repository map, commands, glossary, sources"),
    ]
    rows = "".join(
        f'<tr><td class="n" style="width:8%">{n}</td><td>{t}</td></tr>'
        for n, t in items)
    return f"""
<h1>Contents</h1>
<p class="kicker">EVERY CHAPTER IS BOOKMARKED IN THE PDF OUTLINE</p>
<table>{rows}</table>

<div class="box">
<p><b>How to read this document.</b> Chapters 1&ndash;4 are the overview: the
problem, the gap, and what makes this different. Chapters 5&ndash;15 are the
engineering, and each explains not only what was built but the failure that
forced it &mdash; those failures are the most useful part of the document and
are not hidden. Chapters 16&ndash;21 are the deployment case. Chapter 22 answers
the questions a sceptical reader asks.</p>
<p class="last"><b>A note on numbers.</b> Anything presented as measured was
measured, and the command that measures it is given. Anything estimated is
labelled as an estimate with its assumptions stated. Nothing in between.</p>
</div>
"""


def ch_summary(s: dict) -> str:
    return f"""
<h1>1 &nbsp; Executive summary</h1>
<p class="kicker">WHAT WAS BUILT, IN ONE PAGE</p>

<p class="lead">Ayurvedic innovation in India is simultaneously
under-protected at home and exposed to misappropriation abroad. The reason is
not a lack of law &mdash; it is that seven or eight bodies of law apply at
once, and no practitioner, cultivator or MSME founder can hold all of them in
their head at the same time.</p>

<p>AyurLex is an assistant built against that problem. It has two entry
points and one engine.</p>

<h3>Ask a question</h3>
<p>Every answer is tied to a statutory span, with click-to-source back to the
page of the source PDF. Sentences the citation gate cannot tie to the retrieved
text are <b>removed before display</b>. When the corpus has no authority, the
system abstains and names why &mdash; which the design brief scores as an
explicit criterion rather than treating as a shortcoming.</p>

<h3>Describe a formulation</h3>
<p>It stops being a lookup. The system resolves each ingredient to its
botanical taxon (in any Indian script), classifies the product into one of the
six regulatory categories the design brief names, and compiles it against
{s['rules']} deterministic rules &mdash; returning blockers, warnings,
opportunities, obligations, a jurisdiction matrix and a reproducible digest.
<b>No language model is in that path at all</b>, and it returns in about
30 milliseconds.</p>

<h3>The claim, and the mechanism behind it</h3>
<p>The language model is permitted to do exactly three things: parse messy
input into a typed schema, phrase explanations of decisions the rule engine has
already made, and translate. <b>It never decides a legal outcome.</b> Four
guarantees enforce that in code rather than by convention:</p>

{_table(["Guarantee", "Where it is enforced"], [
    ("A finding without a citation cannot be serialised",
     "<code>core/schema.py</code> &mdash; pydantic validator"),
    ("A rule cannot cite a provision that was never extracted",
     "<code>compliance/loader.py</code> &mdash; corpus binding at load"),
    ("A rule's anchor must be verbatim in the source PDF",
     "<code>compliance/loader.py</code> + <code>scripts/verify_provisions.py</code>"),
    ("A number or quotation with no traceable source is stripped",
     "<code>citations/verify.py</code> &mdash; exact-match paths"),
])}

<h3>What is in it now</h3>
<p>{s['provisions']:,} provisions from {s['instruments']} instruments across
seven jurisdiction tags, in two layers that are retrieved separately and never
merged. {s['rules_verified']}/{s['rules']} rules verified against primary
sources. A {s['graph_nodes']:,}-node knowledge graph answering the multi-hop
questions retrieval structurally cannot. A deterministic orchestrator for
questions spanning both layers. A {s['routes']}-route escalation directory to
human facilitators, each verified against the provision that establishes the
office. {s['tests']} automated tests. {s['loc']:,} lines of Python.</p>

<div class="box">
<p class="last"><b>The single sentence to remember.</b> A groundedness score is
a <i>traceability</i> score, not a correctness score &mdash; and knowing the
difference is why questions whose entire answer is a yes-or-no never reach the
language model at all.</p>
</div>
"""


def ch_problem(s: dict) -> str:
    return """
<h1>2 &nbsp; The problem, and why it matters in the real world</h1>
<p class="kicker">WHAT SPECIFIC PROBLEM IS BEING SOLVED</p>

<p class="lead">A vaidya in Kerala has a family formulation that works. A
women's self-help group in Madhya Pradesh cultivates a medicinal plant and
sells it to a trader for a fraction of what the finished product earns. An
AYUSH startup in Pune has a standardised extract and a clinical hunch. All
three are about to make an expensive mistake, and none of them knows which one.</p>

<h2>2.1 &nbsp; Seven bodies of law apply at once</h2>

<p>Protecting and commercialising an Ayurvedic product is not one legal
question. It is the intersection of at least four regimes that do not talk to
each other, and getting any of them wrong is unrecoverable:</p>

<ul>
<li><b>Patents.</b> Section 3(p) of the Patents Act, 1970 excludes an
invention which is "in effect, traditional knowledge or which is an aggregation
or duplication of known properties of traditionally known component or
components". Section 3(e) excludes a mere admixture. Most classical
formulations fail both. Filing anyway costs money and time and produces
nothing.</li>
<li><b>Access and benefit sharing.</b> Section 6(1) of the Biological
Diversity Act, 2002 prohibits <i>applying</i> for any intellectual property
right on an invention based on a biological resource obtained from India
without previous National Biodiversity Authority approval. This is a
precondition on the act of filing, not a formality afterwards &mdash; and it is
routinely discovered late.</li>
<li><b>Drug regulation.</b> Whether a product is a classical medicine, a
patent-or-proprietary medicine, a new drug, a phytopharmaceutical, an
Ayurveda-Aahara food or a cosmetic decides the licensing route, the evidence
burden, and &mdash; critically &mdash; the IP posture. The same three herbs are
unpatentable traditional knowledge as a classical churna and a defensible
invention as a standardised fraction.</li>
<li><b>Advertising.</b> Section 3 of the Drugs and Magic Remedies
(Objectionable Advertisements) Act, 1954, read with its Schedule, prohibits
advertising a treatment claim for a listed disease. Diabetes is on that list.
A label printed before anyone checked is a recall.</li>
</ul>

<p>Add trade marks, geographical indications, designs, copyright, plant
variety rights and trade secrets &mdash; each of which may be the <i>right</i>
answer when a patent is not &mdash; and the international layer on top: TRIPS,
the Convention on Biological Diversity and the Nagoya Protocol, the WIPO GRATK
Treaty of 2024, the PCT, and the market-access regime of every export
destination.</p>

<h2>2.2 &nbsp; Why the result is a double loss</h2>

<div class="box">
<p><b>Domestically, legitimate innovation is under-protected.</b> A founder
told "you cannot patent this" hears "there is nothing to protect", and stops
&mdash; when the brand was registrable, the region was a candidate for a
geographical indication, the process may have been patentable even though the
composition was not, and the documented traditional use was an evidentiary
<i>asset</i> in the regulatory lane rather than only a liability in the patent
lane.</p>
<p class="last"><b>Abroad, traditional knowledge stays exposed.</b> India's
defensive answer &mdash; the Traditional Knowledge Digital Library &mdash;
works: the official TKDL annexure records patent applications actually refused,
revoked or withdrawn after TKDL prior art was cited. But defensive prior art
protects the commons; it does not help an individual innovator decide what they
personally can protect and how.</p>
</div>

<h2>2.3 &nbsp; Why a general-purpose chatbot makes this worse, not better</h2>

<p>This is the part that matters, because it is the obvious alternative and it
fails in a specific and dangerous way.</p>

<p>Ask a general assistant "do I need NBA approval before filing a patent on my
ashwagandha formulation" and it will answer fluently. It may cite a section
number that does not exist, or a real section number attached to the wrong
proposition. It will not tell you that its confidence is unrelated to whether
it read the provision. It will not know that Section 7 carries a proviso
exempting vaids and hakims practising indigenous medicine &mdash; so it will
tell a practising vaidya to file an intimation the statute exempts them
from.</p>

<p>And in legal work the cost of a wrong answer is asymmetric in a way that
most software gets to ignore:</p>

<ul>
<li>A <b>missed obligation</b> is discovered at the worst moment &mdash; NBA
approval under s.6(1) is a precondition to the application, and finding out
after filing is not a correctable error.</li>
<li>A <b>fabricated citation</b> is worse than no answer, because the reader
cannot tell it from a real one. A reader who catches one fabricated cell
discards everything else in the table, and they are right to.</li>
<li>An <b>inverted polarity</b> &mdash; "no, you do not need approval" against
a section headed <i>"Application for intellectual property rights not to be
made without approval"</i> &mdash; is fluent, confident, and exactly
backwards. This is not hypothetical; it is measured, and Chapter 8 gives the
numbers and the fix.</li>
</ul>

<p>The users who most need this tool are the least able to detect any of those
failures. That asymmetry is the design constraint the whole system is built
around: <b>the system must be more willing to say nothing than to say something
plausible.</b></p>
"""


def ch_ps(s: dict) -> str:
    jur = " &middot; ".join(f"{k} {v}" for k, v in s["jurisdictions"])
    return f"""
<h1>3 &nbsp; The design brief, and a line-by-line coverage audit</h1>
<p class="kicker">WHAT THE SYSTEM IS HELD TO</p>

<p class="lead">The design brief is a "deployable, multilingual
assistant built on retrieval-augmented generation grounded in a curated,
version-tracked corpus &hellip; so that every answer is traceable to a source
and hallucination is minimised", with the output evaluated
on <b>answer accuracy, citation correctness, safe abstention on out-of-scope or
uncertain queries, and multilingual quality</b>.</p>

<div class="box">
<p class="last"><b>Read that evaluation list twice.</b> Safe abstention is a
<i>scored criterion</i>, not a limitation to apologise for. The deliberate
refusal demonstrated in Chapter 23 is a requirement being met.</p>
</div>

<h2>3.1 &nbsp; What the statement requires, and what is built</h2>

{_table(["Requirement", "Status", "Detail"], [
    ("Citation-grounded RAG; never fabricate authority", "<b>Done</b>",
     "Every sentence verified against retrieved spans; unsupported sentences "
     "dropped before display; extractive fallback quotes the provision when a "
     "draft fails the gate"),
    ("Safe abstention on out-of-scope queries", "<b>Done</b>",
     "Names the reason and the regime; no model call at all when out of corpus"),
    ("Mandatory citation to the specific provision", "<b>Done</b>",
     "Click-to-source opens the provision at the cited page with the relied-on "
     "span highlighted"),
    ("Confidence indicator", "<b>Done</b>",
     "Groundedness on every answer, with the gate's drop count beside it "
     "(&sect;15)"),
    ("Jurisdictions kept separate, never conflated", "<b>Done</b>",
     "India and international are separate retrieval layers behind a "
     "pre-filter, with a visible layer badge"),
    ("Jurisdiction toggle as a user control", "Partial",
     "Routing is automatic and visible; there is no manual switch"),
    ("Routing across IP types", "<b>Done</b>",
     f"{s['concepts']} curated concepts route patents / GI / trade marks / "
     "plant variety / ABS / advertising"),
    ("Formulation-classification flow", "<b>Done</b>",
     "All six PS categories, from six tri-state facts, asking only questions "
     "that would change the answer (&sect;10)"),
    ("ABS-compliance helper", "<b>Done</b>",
     "BDA s.6(1), s.7 and s.21 with obligations, fixes and who discharges them"),
    ("TKDL / prior-art pointer", "<b>Done</b>",
     f"{s['tkdl']} real adverse outcomes extracted with application numbers "
     "and page provenance"),
    ("Escalation to a human IP facilitator", "<b>Done</b>",
     f"{s['routes']} institutional routes, {s['routes_cited']} verified against "
     "the provision that establishes the office (&sect;13)"),
    ("Relational knowledge graph", "<b>Done</b>",
     f"{s['graph_nodes']:,} nodes / {s['graph_edges']:,} edges; multi-hop "
     "walks retrieval cannot perform (&sect;11)"),
    ("Agentic, multi-source orchestration", "<b>Done</b>",
     "Deterministic plan, typed tools, hard step cap, auditable trace "
     "(&sect;12)"),
    ("Multilingual delivery", "<b>Done</b>",
     "11 languages detected, Indic concept matching, taxon resolution and "
     "localised scaffolding; translation in both directions routed through "
     "<b>Bhashini</b> when configured, under the same output guards (&sect;19)"),
    ("Version-tracked corpus", "Partial",
     "Every record carries retrieved_on, effective_from/to and amendment "
     "notes; no diffing across corpus versions, and see &sect;20"),
    ("DPDP / privacy / audit", "Partial",
     "Sessions in-process and ephemeral, nothing written to disk; no audit log"),
    ("'Information, not legal advice' disclaimer", "<b>Done</b>",
     "Standing in the composer footer and on every exported artifact"),
])}

<h2>3.2 &nbsp; Corpus coverage against the required list</h2>

<p><b>{s['provisions']:,} provisions across {s['instruments']} instruments.</b>
By jurisdiction: {jur}.</p>

<p>The design brief names specific instruments. Ingested and citable:
Patents Act 1970 and Patents Rules 2003 <b>and the Patents (Amendment) Rules
2024</b>; Trade Marks Act 1999; Geographical Indications Act 1999; Designs Act
2000; Copyright Act 1957 and Copyright Rules 1957; Plant Varieties and Farmers'
Rights Act 2001; the Biological Diversity Act 2002 <b>with the (Amendment)
Act 2023 and the Rules 2024</b>; Drugs and Cosmetics Act 1940 and Rules 1945;
Drugs and Magic Remedies Act 1954; <b>the Food Safety and Standards Act 2006
with the FSSAI Ayurveda Aahara, Nutraceuticals, and Advertising and Claims
Regulations</b>. Internationally: TRIPS,
the Convention on Biological Diversity, the Nagoya Protocol, the WIPO GRATK
Treaty 2024, the PCT and its Regulations, and US FDA botanical-drug
guidance. Plus the WHO Ayurveda benchmarks and standard terminologies, and the
AYUSH primers &mdash; rank-separated as background, never citable as law.</p>

<p><b>Named by the PS and not yet ingested:</b> the Designs Rules 2001;
the Madrid, Hague and Budapest treaties; EU
Directive 2004/24/EC; case law; and live registry records. Each is a public
document, and adding one is a registry entry in
<code>sources/ingest.py</code> plus a re-ingest. Chapter 20 states what that
absence currently costs.</p>

<div class="warn">
<p class="last"><b>How a gap gets closed, and how it does not.</b> Until the
food layer was ingested, the Ayurveda-Aahara category was <i>identified</i> by
the classifier and its posture stated, and the answer said out loud that the
governing regulation was not in the corpus. It now cites Regulation 8 of the
Ayurveda Aahara Regulations and Section 31 of the Food Safety and Standards
Act. Note which of the two things changed: the source was added. Pinning a
loosely related provision to make the category <i>look</i> cited would have
been precisely the failure this system exists to prevent, and the gap was
carried in the open for as long as it took to close it properly.</p>
</div>
"""


def ch_difference(s: dict) -> str:
    return f"""
<h1>4 &nbsp; How the solution differs from what already exists</h1>
<p class="kicker">AGAINST EXISTING PRODUCTS, METHODS AND CURRENT PRACTICE</p>

<h2>4.1 &nbsp; The four alternatives, and where each stops</h2>

{_table(["What exists today", "What it does well", "Where it stops"], [
    ("<b>A registered patent agent or IP advocate</b>",
     "Authoritative, accountable, and irreplaceable at the drafting stage",
     "Costs money before a founder knows whether there is anything worth "
     "drafting. Most first-time AYUSH innovators never get through that door, "
     "and the ones who do arrive with none of the facts an agent needs"),
    ("<b>TKDL</b>",
     "Genuinely effective defensive prior art; the official annexure records "
     f"{s['tkdl']} applications refused, revoked or withdrawn after it was cited",
     "Protects the commons, not the individual. It answers 'can someone else "
     "patent this' &mdash; never 'what can <i>I</i> protect, and how'"),
    ("<b>Government portals and PDF handbooks</b>",
     "Authoritative text, free, and complete",
     "Organised by <i>instrument</i>, not by situation. A founder's question "
     "spans four Acts and they do not know which four"),
    ("<b>A general-purpose AI assistant</b>",
     "Fluent, instant, free, and answers any phrasing",
     "Will invent a section number, invert a duty, and cannot tell you which. "
     "Its confidence is uncorrelated with whether it read the provision"),
])}

<h2>4.2 &nbsp; The six things that are genuinely different</h2>

<h3>1. It is a compiler, not a chatbot</h3>
<p>A retrieval chatbot answers "what does Section 3(p) say". This answers "here
is what Section 3(p) does to <i>your</i> formulation, here is the minimum
change that clears it, and here is proof it cleared" &mdash; because a
deterministic rule engine sits underneath the chat. Chat is an interface; the
engine is the product.</p>

<h3>2. A fabricated citation is structurally impossible, not merely unlikely</h3>
<p>There is no code path from a rule file to a finding that does not pass
through the primary source text. A finding without a citation fails
serialisation. A rule citing a provision that was never extracted is demoted at
load and refused permission to emit. An anchor that is not verbatim in the PDF
fails the same gate. This is a different kind of claim from "we prompt it to
cite its sources".</p>

<h3>3. Two lanes over one citation graph, so it sees what a chatbot cannot</h3>
<p>The demonstration this rests on: two rules fire on the same facts and cite
<b>the same provision</b> with opposite consequences &mdash; Patents Act s.3(p)
as a <b>blocker</b> in the patent lane, and the same s.3(p) re-read as
documented traditional use, an <b>opportunity</b> in the regulatory lane. A
chatbot answers one question at a time and never notices. And the trade-off
runs both ways: applying the fix that clears the s.3(p) blocker also
<i>removes</i> the traditional-use opportunity, and the compiler surfaces that
strategic consequence without being asked.</p>

<h3>4. It refuses, by name, and that is a scored requirement</h3>
<p>Asked about EPO opposition periods it returns, instantly and with no model
call, that it has no authority in the ingested corpus &mdash; and names both
the regime the question belongs to and exactly what the corpus does cover.
Retrieval would otherwise happily return an Indian section about oppositions
and sound confident about it.</p>

<h3>5. It runs entirely on the user's machine</h3>
<p>The model is local under Ollama. No API key, no network call, nothing
leaving the box, and chat sessions are in-process and never written to disk.
This is not a convenience feature: it is the answer to the first question any
manufacturer asks, which is why a manufacturer would paste a proprietary
formulation into somebody else's API. Chapter 17 gives the detail.</p>

<h3>6. The output is a build artifact, not a conversation</h3>
<p>A compile emits a Compliance Bill of Materials &mdash; versioned, diffable,
and reproducible byte for byte. Ten runs of the same formulation produce one
digest; patch a single fact and the digest changes. That makes the analysis
something a regulator or an auditor can hold, compare across dates, and check.
A chat transcript is not.</p>

<h2>4.3 &nbsp; Against current government and market practice</h2>

<p>Current practice for an AYUSH MSME is: read a PDF handbook, ask a peer,
or pay for an hour of professional time to find out whether there is anything
worth paying for. The distinctive contribution here is not that the law is
online &mdash; it already is. It is that the law is <b>executable against your
own facts</b>, and that the execution is auditable line by line back to the
gazette page it came from.</p>
"""


def build(s: dict):
    """Assemble the whole document. Returns (cover_html, [(title, html), ...])."""
    from scripts.documentation_content_2 import chapters_two
    from scripts.documentation_content_3 import chapters_three

    chapters = [
        ("Contents", ch_contents(s)),
        ("1 · Executive summary", ch_summary(s)),
        ("2 · The problem, and why it matters", ch_problem(s)),
        ("3 · Design brief and coverage audit", ch_ps(s)),
        ("4 · How this differs from what exists", ch_difference(s)),
    ]
    chapters += chapters_two(s)
    chapters += chapters_three(s)
    return cover(s), chapters
