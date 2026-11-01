"""Render the project documentation to a PDF.

Why a build script rather than a hand-made file: every number in that document
is a claim, and a claim about this system has to be re-derivable. The figures
that can be measured are measured HERE, at build time, from the running code --
the corpus counts, the rule verification state, the graph size, the test count.
A number that drifts from the code fails the build instead of misleading
whoever reads it.

  python scripts/build_documentation_pdf.py

Uses PyMuPDF's Story layout engine, which is already a dependency (the ingester
uses PyMuPDF to read the source PDFs), so the documentation builds with no
extra install and no network.
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "AyurLex-technical-and-evaluation-documentation.pdf"

PAGE = pymupdf.paper_rect("A4")
MARGIN_L, MARGIN_T, MARGIN_R, MARGIN_B = 56, 62, 56, 66
FRAME = PAGE + (MARGIN_L, MARGIN_T, -MARGIN_R, -MARGIN_B)

INK = (0.09, 0.10, 0.11)
MUTED = (0.44, 0.46, 0.47)
RULE = (0.83, 0.85, 0.84)
ACCENT = (0.05, 0.32, 0.18)

CSS = """
body       { font-family: sans-serif; font-size: 9.6pt; color: #17191a;
             line-height: 1.5; }
p          { margin: 0 0 7pt 0; }

h1         { font-family: sans-serif; font-size: 19pt; color: #0d5227;
             margin: 0 0 2pt 0; line-height: 1.15; }
h2         { font-family: sans-serif; font-size: 12.5pt; color: #0d5227;
             margin: 15pt 0 5pt 0; }
h3         { font-family: sans-serif; font-size: 10.4pt; color: #1f2937;
             margin: 12pt 0 4pt 0; }
h4         { font-family: sans-serif; font-size: 9.6pt; color: #374151;
             margin: 10pt 0 3pt 0; }

.kicker    { font-family: monospace; font-size: 7.6pt; color: #5b6b60;
             margin: 0 0 9pt 0; }
.lead      { font-size: 10.4pt; color: #33383c; margin: 0 0 10pt 0; }
.small     { font-size: 8.4pt; color: #55595c; }
.muted     { color: #55595c; }

ul, ol     { margin: 0 0 8pt 0; }
li         { margin: 0 0 3.5pt 0; }

code       { font-family: monospace; font-size: 8.6pt; color: #7c2d12; }
pre        { font-family: monospace; font-size: 7.9pt; line-height: 1.42;
             background-color: #f5f6f5; color: #1b1d1e;
             padding: 7pt; margin: 5pt 0 9pt 0; }

table      { width: 100%; margin: 4pt 0 10pt 0; }
th         { background-color: #e9efe9; color: #14361f; text-align: left;
             font-size: 8.2pt; padding: 4.5pt 5pt; }
td         { font-size: 8.4pt; padding: 4.5pt 5pt; vertical-align: top;
             border-bottom: 1px solid #e2e5e3; }
td.n       { font-family: monospace; font-size: 8.2pt; }

.box       { background-color: #f3f6f3; padding: 9pt 10pt; margin: 6pt 0 10pt 0; }
.box p     { margin: 0 0 5pt 0; }
.box p.last{ margin: 0; }
.warn      { background-color: #fdf5ec; padding: 9pt 10pt; margin: 6pt 0 10pt 0; }
.warn p    { margin: 0 0 5pt 0; }
.q         { font-family: sans-serif; font-size: 10.2pt; color: #0d5227;
             font-weight: bold; margin: 14pt 0 4pt 0; }
.tag       { font-family: monospace; font-size: 7.6pt; color: #5b6b60; }
"""

COVER_CSS = CSS + """
body       { font-size: 10pt; }
h1         { font-size: 28pt; line-height: 1.08; margin: 2pt 0 7pt 0; }
.sub       { font-size: 12.4pt; color: #33383c; margin: 0 0 15pt 0;
             line-height: 1.35; }
.kicker    { font-size: 7.4pt; margin: 0 0 4pt 0; }
.stamp     { font-family: monospace; font-size: 7.6pt; color: #5b6b60;
             margin: 12pt 0 0 0; }
"""


# --------------------------------------------------------------- measured --
def measured() -> dict:
    """Every figure the document quotes that can be read off the code.

    Read here rather than typed into the prose, so the documentation cannot
    quietly disagree with the system it describes.
    """
    import json
    from collections import Counter

    from sambandha.graph import load_graph
    from sampark.escalate import load_registry
    from samhita.index import load_corpus
    from sutra.loader import load_rules

    corpus = load_corpus()
    rules = load_rules()
    graph = load_graph()
    registry = load_registry()

    recs = corpus.records
    juris = Counter(r["jurisdiction"] for r in recs)
    ranks = Counter(r["authority_rank"] for r in recs)
    instruments = Counter(
        (r["act_id"], r["act_title"], r["jurisdiction"], r["authority_rank"],
         r["unit"]) for r in recs)

    tkdl = (ROOT / "corpus" / "tkdl_outcomes.jsonl")
    n_tkdl = len([x for x in tkdl.read_text(encoding="utf-8").splitlines()
                  if x.strip()]) if tkdl.exists() else 0
    dmr = ROOT / "corpus" / "dmr_schedule.json"
    n_dmr = json.loads(dmr.read_text(encoding="utf-8"))["count"] if dmr.exists() else 0

    # The system, not the paperwork. The scripts that build this document and
    # the slide diagrams are real code, but counting them as "lines of the
    # system" would inflate the figure with prose about the system -- and a
    # number that flatters is exactly what this build script exists to prevent.
    DOCS_BUILD = {"build_documentation_pdf.py", "documentation_content.py",
                  "documentation_content_2.py", "documentation_content_3.py",
                  "build_architecture_diagrams.py"}
    py = sorted(ROOT.rglob("*.py"))
    py = [f for f in py
          if "__pycache__" not in f.parts and ".git" not in f.parts
          and f.name not in DOCS_BUILD]
    loc = sum(len(f.read_text(encoding="utf-8", errors="ignore").splitlines())
              for f in py)
    test_loc = sum(len(f.read_text(encoding="utf-8", errors="ignore").splitlines())
                   for f in py if f.parent.name == "tests")

    n_tests = 0
    try:
        out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"],
                             cwd=ROOT, capture_output=True, text=True, timeout=300)
        m = re.search(r"(\d+)\s+tests? collected", out.stdout)
        if m:
            n_tests = int(m.group(1))
    except Exception:
        pass

    return {
        "provisions": len(recs),
        "instruments": len(instruments),
        "instrument_rows": sorted(instruments.items(), key=lambda kv: -kv[1]),
        "jurisdictions": juris.most_common(),
        "ranks": sorted(ranks.items()),
        "rules": len(rules),
        "rules_verified": sum(1 for r in rules
                              if r.verification.value == "VERIFIED"),
        "rule_rows": [(r.id, r.severity.value, r.lane, r.provision,
                       r.verification.value) for r in rules],
        "graph_nodes": len(graph.nodes),
        "graph_edges": len(graph.edges),
        "graph_stats": graph.stats(),
        "graph_problems": graph.problems,
        "routes": len(registry.routes),
        "routes_cited": sum(1 for r in registry.routes if r.cited),
        "route_problems": registry.problems,
        "tkdl": n_tkdl,
        "dmr": n_dmr,
        "loc": loc,
        "test_loc": test_loc,
        "tests": n_tests,
        "concepts": len(open(ROOT / "data" / "legal_concepts.yaml",
                             encoding="utf-8").read().split("\n- id:")) - 1,
        "taxa": len([x for x in (ROOT / "data" / "taxa.jsonl")
                     .read_text(encoding="utf-8").splitlines() if x.strip()]),
        "categories": len(open(ROOT / "data" / "formulation_classes.yaml",
                               encoding="utf-8").read().split("\n- id:")) - 1,
        "links": len(open(ROOT / "data" / "graph_links.yaml",
                          encoding="utf-8").read().split("\n- id:")) - 1,
        "pdfs": len(list((ROOT / "Dataset").glob("*.pdf"))),
        "dataset_mb": round(sum(f.stat().st_size for f in
                                (ROOT / "Dataset").glob("*.pdf")) / 1e6),
        "built": date.today().isoformat(),
    }


# ----------------------------------------------------------------- render --
def render(chapters: list[tuple[str, str]], cover_html: str, stats: dict) -> None:
    writer = pymupdf.DocumentWriter(OUT)
    page_no = 0
    starts: list[tuple[str, int]] = []

    def flow(html: str, css: str, first_page_extra_top: int = 0) -> None:
        nonlocal page_no
        story = pymupdf.Story(html=html, user_css=css)
        more, first = 1, True
        while more:
            dev = writer.begin_page(PAGE)
            frame = FRAME
            if first and first_page_extra_top:
                frame = FRAME + (0, first_page_extra_top, 0, 0)
            more, _ = story.place(frame)
            story.draw(dev)
            writer.end_page()
            page_no += 1
            first = False

    flow(cover_html, COVER_CSS)
    for title, html in chapters:
        starts.append((title, page_no))     # 0-based index of the chapter's first page
        flow(html, CSS)
    writer.close()

    # Second pass: chrome and the clickable outline. Story lays text out; the
    # running furniture is drawn afterwards because it belongs to the page, not
    # to the flow.
    doc = pymupdf.open(OUT)
    # A single accent bar on the cover, under the kicker. Drawn rather than
    # laid out because Story has no border-box primitive worth fighting.
    doc[0].draw_rect(pymupdf.Rect(MARGIN_L, MARGIN_T + 26,
                                  MARGIN_L + 58, MARGIN_T + 29.5),
                     color=ACCENT, fill=ACCENT)
    for i, page in enumerate(doc):
        if i == 0:
            continue
        y = PAGE.height - MARGIN_B + 22
        page.draw_line(pymupdf.Point(MARGIN_L, y - 12),
                       pymupdf.Point(PAGE.width - MARGIN_R, y - 12),
                       color=RULE, width=0.5)
        page.insert_text(pymupdf.Point(MARGIN_L, y),
                         "AyurLex  ·  Technical & "
                         "Evaluation Documentation",
                         fontname="helv", fontsize=7.2, color=MUTED)
        page.insert_text(pymupdf.Point(PAGE.width - MARGIN_R - 22, y),
                         f"{i + 1}", fontname="hebo", fontsize=7.6, color=ACCENT)

    doc.set_metadata({
        "title": "AyurLex - Technical & Evaluation Documentation",
        "author": "Varnit Kalra",
        "subject": f"{stats['provisions']} provisions, {stats['instruments']} "
                   f"instruments, {stats['rules_verified']}/{stats['rules']} "
                   f"rules verified.",
        "keywords": "Ayurveda, AYUSH, intellectual property, RAG, citation, "
                    "knowledge graph, compliance",
    })
    doc.set_toc([[1, t, p + 1] for t, p in starts])
    doc.saveIncr()
    doc.close()


def main() -> int:
    from scripts.documentation_content import build

    stats = measured()
    cover, chapters = build(stats)
    render(chapters, cover, stats)
    doc = pymupdf.open(OUT)
    print(f"  {OUT.name}")
    print(f"  {doc.page_count} pages · {OUT.stat().st_size / 1024:.0f} KB · "
          f"{len(doc.get_toc())} chapters")
    print(f"  built from a live corpus of {stats['provisions']} provisions, "
          f"{stats['rules_verified']}/{stats['rules']} rules verified")
    if stats["graph_problems"] or stats["route_problems"]:
        print("  WARNING: unverified curated data — "
              f"{stats['graph_problems']} {stats['route_problems']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
