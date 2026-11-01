"""Render the architecture diagrams, for slides.

Three diagrams, each 16:9 so it drops onto a slide without cropping, and each
emitted three ways:

  .pdf   vector, for print and for anyone who wants to edit it
  .svg   vector, insertable in PowerPoint 2016+ and Google Slides
  .png   300 dpi raster, for anything that will not take an SVG

Drawn rather than laid out because a diagram in a deck has one job: to be
readable from the back of the room. That means few boxes, big type, and one
idea carried by colour -- here, GREEN means no language model is involved and
AMBER means the model may phrase text, behind the gate. Everything else on
these diagrams is subordinate to that distinction, because it is the project's
whole argument.

  python scripts/build_architecture_diagrams.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUTDIR = ROOT / "docs"
DPI = 300

W, H = 960, 540                      # 16:9, in points

INK = (0.10, 0.11, 0.12)
MUTED = (0.42, 0.45, 0.46)
WHITE = (1, 1, 1)

GREEN_DARK = (0.04, 0.29, 0.16)
GREEN_MID = (0.13, 0.45, 0.27)
GREEN_PALE = (0.925, 0.955, 0.93)
GREEN_LINE = (0.68, 0.80, 0.71)

AMBER_DARK = (0.62, 0.35, 0.04)
AMBER_PALE = (0.995, 0.955, 0.885)
AMBER_LINE = (0.88, 0.70, 0.42)

SLATE_PALE = (0.955, 0.962, 0.958)
SLATE_LINE = (0.80, 0.83, 0.81)

RED = (0.66, 0.16, 0.12)


# ------------------------------------------------------------- helpers ----
def R(x, y, w, h):
    return pymupdf.Rect(x, y, x + w, y + h)


# The built-in PDF fonts are Latin-1 only, and PyMuPDF substitutes a "?" for
# anything outside it -- silently. An em dash and a right arrow are exactly the
# characters a writer reaches for, so they are mapped rather than banned, and
# anything still unmappable raises instead of shipping as "?".
_ASCII = {
    "—": " - ", "–": "-", "→": "->", "←": "<-",
    "≥": ">=", "≤": "<=", "’": "'", "‘": "'",
    "“": '"', "”": '"', "…": "...", "•": "-",
    "₹": "Rs ", "✓": "yes", "✗": "no", " ": " ",
}


def _latin1(s: str) -> str:
    for bad, good in _ASCII.items():
        s = s.replace(bad, good)
    try:
        s.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise ValueError(
            f"character {s[exc.start:exc.end]!r} has no glyph in the built-in "
            f"fonts and would render as '?': {s[:60]!r}") from None
    return s


def text(page, rect, s, *, size=9, font="helv", color=INK, align=0,
         lh=1.28, grow=1.7):
    """Place text; grow the box a little if needed, and fail loudly if not.

    insert_textbox returns a negative number when the string does not fit, and
    draws nothing. On a diagram that is a missing label nobody notices until
    it is on a projector.

    Small shortfalls are usually one line of descender clearance rather than a
    layout error, so the box is retried once with exactly the shortfall added.
    Anything needing more than `grow` times the requested height is a real
    layout mistake and raises -- silently overlapping the box below would be
    worse than a broken build.
    """
    s = _latin1(s)
    rc = page.insert_textbox(rect, s, fontname=font, fontsize=size,
                             color=color, align=align, lineheight=lh)
    if rc >= 0:
        return rc
    taller = pymupdf.Rect(rect.x0, rect.y0, rect.x1, rect.y1 - rc + 2)
    if taller.height > rect.height * grow:
        raise ValueError(
            f"text needs {taller.height:.0f}pt in a {rect.height:.0f}pt box: "
            f"{s[:60]!r}")
    rc = page.insert_textbox(taller, s, fontname=font, fontsize=size,
                             color=color, align=align, lineheight=lh)
    if rc < 0:
        raise ValueError(f"text does not fit ({rc:.0f}pt short): {s[:60]!r}")
    return rc


def box(page, rect, *, fill=WHITE, line=SLATE_LINE, width=0.9, radius=0.06):
    page.draw_rect(rect, color=line, fill=fill, width=width, radius=radius)


def band_label(page, x, y, w, h, label):
    box(page, R(x, y, w, h), fill=GREEN_DARK, line=GREEN_DARK, radius=0.10)
    text(page, R(x + 6, y + h / 2 - 8, w - 12, 20), label,
         size=8.2, font="hebo", color=WHITE, align=1)


def chip(page, rect, name, desc, *, model=False, size=10):
    """One module. Amber means a language model may write text here."""
    fill = AMBER_PALE if model else GREEN_PALE
    line = AMBER_LINE if model else GREEN_LINE
    head = AMBER_DARK if model else GREEN_DARK
    box(page, rect, fill=fill, line=line, width=1.0, radius=0.09)
    text(page, R(rect.x0 + 8, rect.y0 + 6, rect.width - 16, 16), name,
         size=size, font="hebo", color=head)
    text(page, R(rect.x0 + 8, rect.y0 + 6 + size + 3, rect.width - 16,
                 rect.height - size - 12), desc,
         size=7.3, color=MUTED, lh=1.25)


def arrow_up(page, x, y0, y1, *, color=GREEN_MID, width=1.4, head=5):
    page.draw_line(pymupdf.Point(x, y0), pymupdf.Point(x, y1),
                   color=color, width=width)
    page.draw_polyline([pymupdf.Point(x - head, y1 + head),
                        pymupdf.Point(x, y1),
                        pymupdf.Point(x + head, y1 + head)],
                       color=color, width=width)


def arrow_down(page, x, y0, y1, *, color=GREEN_MID, width=1.2, head=4.5):
    page.draw_line(pymupdf.Point(x, y0), pymupdf.Point(x, y1),
                   color=color, width=width)
    page.draw_polyline([pymupdf.Point(x - head, y1 - head),
                        pymupdf.Point(x, y1),
                        pymupdf.Point(x + head, y1 - head)],
                       color=color, width=width)


def legend(page, x, y, items):
    cx = x
    for fill, line, label in items:
        box(page, R(cx, y, 11, 11), fill=fill, line=line, width=1.0,
            radius=0.18)
        # Measure the string that will actually be DRAWN. Measuring the raw one
        # under-reserves whenever a substitution widens it (an em dash becomes
        # " - "), and the label then wraps to a second line.
        drawn = _latin1(label)
        w = pymupdf.get_text_length(drawn, fontname="helv", fontsize=7.6)
        text(page, R(cx + 16, y - 1, w + 8, 14), drawn, size=7.6, color=MUTED)
        cx += 16 + w + 24


def footer(page, s):
    page.draw_line(pymupdf.Point(28, H - 34), pymupdf.Point(W - 28, H - 34),
                   color=SLATE_LINE, width=0.6)
    text(page, R(28, H - 28, W - 56, 16), s, size=7.4, color=MUTED)


# =========================================================== diagram 1 =====
def d_layers(page, s):
    text(page, R(28, 22, 620, 22),
         "System architecture", size=15, font="hebo", color=GREEN_DARK)
    text(page, R(28, 42, 700, 14),
         "Data flows upward through verification gates. No layer may assert "
         "what a lower layer has not already proved.",
         size=8.4, color=MUTED)

    LX, LW = 28, 96                      # band label column
    CX = LX + LW + 12                    # content column
    CW = W - CX - 28

    arrow_up(page, LX + LW / 2, 452, 78, color=GREEN_LINE, width=2.6, head=7)

    # ---- INTERFACE
    y, h = 66, 42
    band_label(page, LX, y, LW, h, "INTERFACE")
    for i, (n, d) in enumerate([
            ("Web chat", "streaming; citations arrive first"),
            ("CLI", "compile · graph · escalate · plan"),
            ("HTTP API", "chat · provision · graph · escalate")]):
        w = (CW - 16) / 3
        chip(page, R(CX + i * (w + 8), y, w, h), n, d, size=9)

    # ---- ORCHESTRATION
    y, h = 116, 44
    band_label(page, LX, y, LW, h, "ORCHESTRATION")
    for i, (n, d) in enumerate([
            ("Planner", "deterministic plan · typed tools · hard step cap · "
                      "auditable trace"),
            ("CHAT", "intent routing · session state · 3-turn follow-ups")]):
        w = (CW - 8) / 2
        chip(page, R(CX + i * (w + 8), y, w, h), n, d, size=9.6)

    # ---- REASONING
    y, h = 168, 96
    band_label(page, LX, y, LW, h, "REASONING")
    mods = [
        ("Rules", f"{s['rules']} rules as data\nverified at load", False),
        ("Classification", "6 regulatory\ncategories", False),
        ("Knowledge graph", f"{s['graph_nodes']:,}-node\nknowledge graph", False),
        ("Escalation", f"{s['routes']} escalation\nroutes", False),
        ("Obligations", "obligations:\nwho, and when", False),
        ("Jurisdictions", "jurisdiction\nmatrix", False),
        ("RESOLVER", "any script →\nbotanical taxon", False),
        ("RAG", "hybrid retrieval\n+ LLM phrasing", True),
    ]
    cw = (CW - 3 * 8) / 4
    ch = (h - 8) / 2
    for i, (n, d, m) in enumerate(mods):
        r, c = divmod(i, 4)
        chip(page, R(CX + c * (cw + 8), y + r * (ch + 8), cw, ch),
             n, d, model=m, size=8.6)

    # ---- VERIFICATION
    y, h = 272, 44
    band_label(page, LX, y, LW, h, "VERIFICATION")
    box(page, R(CX, y, CW, h), fill=AMBER_PALE, line=AMBER_LINE, width=1.2)
    text(page, R(CX + 10, y + 7, CW - 20, 14), "Citation gate — the citation gate",
         size=9.6, font="hebo", color=AMBER_DARK)
    text(page, R(CX + 10, y + 22, CW - 20, 16),
         "Every sentence checked against the spans it cites.  Numbers, "
         "quotations and instrument names take exact-match paths.  "
         "Unsupported sentences are dropped before display.",
         size=7.3, color=MUTED)

    # ---- EVIDENCE
    y, h = 324, 60
    band_label(page, LX, y, LW, h, "EVIDENCE")
    box(page, R(CX, y, CW, h), fill=SLATE_PALE, line=SLATE_LINE, width=1.0)
    text(page, R(CX + 10, y + 7, CW - 20, 14),
         f"Sources — {s['provisions']:,} page-anchored provisions from "
         f"{s['instruments']} instruments",
         size=9.6, font="hebo", color=INK)
    text(page, R(CX + 10, y + 23, CW - 20, 30),
         f"{s['pdfs']} primary-source PDFs, shipped with the repository.  "
         "Two layers retrieved separately and never merged: India "
         f"({dict(s['jurisdictions']).get('IN', 0):,}) and international.  "
         "Authority-ranked, so a primer can never stand in for a statute.",
         size=7.3, color=MUTED)

    # ---- the claim
    y = 396
    box(page, R(28, y, W - 56, 42), fill=GREEN_PALE, line=GREEN_LINE,
        width=1.0)
    text(page, R(40, y + 8, W - 80, 14),
         "The language model may do exactly three things: parse input into the "
         "typed schema, phrase decisions the rule engine already made, and "
         "translate.",
         size=8.8, font="hebo", color=GREEN_DARK)
    text(page, R(40, y + 24, W - 80, 14),
         "It never decides a legal outcome.  Every legal outcome is a "
         "declarative rule firing on resolved facts.  Turn the model off and "
         "the system still compiles, classifies, walks its graph and escalates.",
         size=7.8, color=INK)

    legend(page, 28, 452, [
        (GREEN_PALE, GREEN_LINE, "deterministic — no language model"),
        (AMBER_PALE, AMBER_LINE, "model may phrase text here, behind the gate"),
    ])
    footer(page, f"AyurLex  ·  {s['loc']:,} lines of "
                 f"Python  ·  {s['tests']} tests  ·  8 dependencies, no vector "
                 f"database, no agent framework")


# =========================================================== diagram 2 =====
def d_flow(page, s):
    text(page, R(28, 22, 620, 22),
         "Two request paths", size=15, font="hebo", color=GREEN_DARK)
    text(page, R(28, 42, 760, 14),
         "The fastest and safest answers are the ones where no generation "
         "happens.  Three checks can end a request before the model is called.",
         size=8.4, color=MUTED)

    colw = (W - 56 - 24) / 2
    LX, RX = 28, 28 + colw + 24

    # ---------------- ASK
    box(page, R(LX, 66, colw, 26), fill=GREEN_DARK, line=GREEN_DARK,
        radius=0.12)
    text(page, R(LX + 12, 72, colw - 24, 16),
         'ASK  —  "can I patent a traditional formulation?"',
         size=9.6, font="hebo", color=WHITE)

    ask = [
        ("detect language", "Unicode block, then romanised-Indic", None),
        ("concept match", "lay phrasing → statutory vocabulary", None),
        ("polarity guard", '"do I need…?" → quote the provision', "STOP"),
        ("out-of-corpus check", "foreign regime → abstain, by name", "STOP"),
        ("layer routing", "IN or INTL — a pre-filter, not a post-filter", None),
        ("retrieval", "BM25 + LSA dense + taxon, fused and reranked", None),
        ("weak-retrieval check", "nothing good enough → abstain", "STOP"),
        ("citations stream", "~0.1 s, before a word of prose", None),
        ("draft", "the model sees the top 3 extracts, nothing else", "MODEL"),
        ("citation gate", "verified against those same 3 extracts", None),
        ("final", "what was dropped is shown, not deleted", None),
    ]
    y = 100
    for i, (n, d, kind) in enumerate(ask):
        h = 26
        model = kind == "MODEL"
        fill = AMBER_PALE if model else (WHITE if kind != "STOP" else GREEN_PALE)
        line = AMBER_LINE if model else (SLATE_LINE if kind != "STOP"
                                         else GREEN_LINE)
        box(page, R(LX, y, colw, h), fill=fill, line=line, width=1.0)
        text(page, R(LX + 9, y + 4, 18, 12), f"{i + 1}", size=7.4,
             font="cour", color=MUTED)
        text(page, R(LX + 28, y + 3.5, colw - 100, 12), n,
             size=8.4, font="hebo",
             color=AMBER_DARK if model else INK)
        text(page, R(LX + 28, y + 14, colw - 100, 11), d, size=7.1,
             color=MUTED)
        if kind == "STOP":
            bw = 62
            box(page, R(LX + colw - bw - 8, y + 6, bw, 14), fill=GREEN_DARK,
                line=GREEN_DARK, radius=0.28)
            text(page, R(LX + colw - bw - 8, y + 9.5, bw, 10), "NO MODEL",
                 size=6.6, font="hebo", color=WHITE, align=1)
        if kind == "MODEL":
            bw = 62
            box(page, R(LX + colw - bw - 8, y + 6, bw, 14), fill=AMBER_DARK,
                line=AMBER_DARK, radius=0.28)
            text(page, R(LX + colw - bw - 8, y + 9.5, bw, 10), "LLM",
                 size=6.6, font="hebo", color=WHITE, align=1)
        y += h + 3

    # ---------------- COMPILE
    box(page, R(RX, 66, colw, 26), fill=GREEN_DARK, line=GREEN_DARK,
        radius=0.12)
    text(page, R(RX + 12, 72, colw - 24, 16),
         'COMPILE  —  "my churna contains amla, haritaki and bibhitaki"',
         size=9.6, font="hebo", color=WHITE)

    comp = [
        ("parse", "ingredients, claims, markets, filing intent"),
        ("RESOLVER", "every name → binomial, or an explicit refusal to guess"),
        ("build facts", "tri-state; every fact records why it holds"),
        ("Classification", "the category, or the one question that settles it"),
        ("Rules", "declarative rules; only VERIFIED rules may emit"),
        ("Citation gate", "each finding checked against its own cited span"),
        ("Obligations", "obligations — who discharges each, and when"),
        ("Jurisdictions", "jurisdiction matrix; abstains where corpus is absent"),
        ("C-BOM", "signed, digest-stable artifact"),
    ]
    y = 100
    for i, (n, d) in enumerate(comp):
        h = 26
        box(page, R(RX, y, colw, h), fill=GREEN_PALE, line=GREEN_LINE,
            width=1.0)
        text(page, R(RX + 9, y + 4, 18, 12), f"{i + 1}", size=7.4,
             font="cour", color=MUTED)
        text(page, R(RX + 28, y + 3.5, colw - 40, 12), n, size=8.4,
             font="hebo", color=GREEN_DARK)
        text(page, R(RX + 28, y + 14, colw - 40, 11), d, size=7.1, color=MUTED)
        y += h + 3

    box(page, R(RX, y + 6, colw, 52), fill=GREEN_DARK, line=GREEN_DARK,
        radius=0.06)
    text(page, R(RX + 12, y + 14, colw - 24, 16),
         "No language model at any step.", size=11, font="hebo", color=WHITE)
    text(page, R(RX + 12, y + 32, colw - 24, 14),
         "Returns in ~30 ms.  Ten runs produce one digest.",
         size=8.4, color=(0.85, 0.92, 0.87))

    footer(page, "Abstention costs 0.0 s — no model call is made at all.  "
                 "If the model is unavailable, the ask path degrades to "
                 "quoting the retrieved provision; the compile path is "
                 "unaffected.")


# =========================================================== diagram 3 =====
def d_gates(page, s):
    text(page, R(28, 22, 700, 22),
         "Why a fabricated citation is structurally impossible",
         size=15, font="hebo", color=GREEN_DARK)
    text(page, R(28, 42, 780, 14),
         "Four gates, each enforced in code rather than by convention.  There "
         "is no code path from a rule to a finding that bypasses the primary "
         "source text.",
         size=8.4, color=MUTED)

    gates = [
        ("1", "SCHEMA",
         "A finding without a citation\ncannot be serialised",
         "core/schema.py — pydantic validator",
         "The entire class of \"the model invented a section number\" is "
         "unrepresentable, not merely discouraged."),
        ("2", "RULE LOADER",
         "A rule cannot cite a provision\nthat was never extracted",
         "compliance/loader.py — corpus binding at load",
         "A rule that fails is demoted to UNVERIFIED and refused permission "
         "to emit. The abstention is printed, not hidden."),
        ("3", "ANCHOR CHECK",
         "A rule's anchor must be verbatim\nin the source PDF",
         "verify_provisions.py — re-extracts from the PDF",
         "Catches an amendment silently changing text a rule depends on. "
         "13 anchors re-verified, zero drift."),
        ("4", "CITATION GATE",
         "A number, quotation or instrument\nname with no source is stripped",
         "citations/verify.py — exact-match paths",
         "Each path was added because a real model failed it during the "
         "build."),
    ]

    y = 76
    for n, title, claim, where, why in gates:
        h = 66
        box(page, R(28, y, W - 56, h), fill=WHITE, line=SLATE_LINE, width=1.0)
        box(page, R(28, y, 46, h), fill=GREEN_DARK, line=GREEN_DARK,
            radius=0.06)
        text(page, R(28, y + h / 2 - 12, 46, 24), n, size=19, font="hebo",
             color=WHITE, align=1)
        text(page, R(88, y + 10, 150, 14), title, size=9.4, font="hebo",
             color=GREEN_DARK)
        text(page, R(88, y + 26, 190, 34), claim, size=8.6, color=INK, lh=1.3)
        text(page, R(300, y + 10, 300, 14), where, size=7.6, font="cour",
             color=AMBER_DARK)
        text(page, R(300, y + 26, W - 340, 34), why, size=8, color=MUTED,
             lh=1.32)
        y += h + 10

    box(page, R(28, y + 6, W - 56, 56), fill=AMBER_PALE, line=AMBER_LINE,
        width=1.1)
    text(page, R(40, y + 15, W - 80, 14),
         "And the one the gate cannot catch — which is why it is named out "
         "loud:", size=8.6, font="hebo", color=AMBER_DARK)
    text(page, R(40, y + 31, W - 80, 26),
         "A groundedness score is a TRACEABILITY score, not a correctness "
         "score.  Measured: three of four \"do I need X?\" questions came back "
         "with the polarity INVERTED, at groundedness 1.00.  So first-person "
         "duty questions never reach the model at all — the provision is "
         "quoted instead.",
         size=7.8, color=INK, lh=1.3)

    footer(page, "An unverified rule can match the facts perfectly and still "
                 "emit nothing.  That abstention is printed in the report "
                 "rather than hidden.")


# ============================================================== render =====
def emit(name: str, draw, s) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    draw(page, s)

    OUTDIR.mkdir(exist_ok=True)
    pdf = OUTDIR / f"{name}.pdf"
    doc.save(pdf)
    (OUTDIR / f"{name}.svg").write_text(page.get_svg_image(text_as_path=False),
                                        encoding="utf-8")
    page.get_pixmap(dpi=DPI).save(OUTDIR / f"{name}.png")
    doc.close()
    px = int(W / 72 * DPI)
    print(f"  {name}.png / .svg / .pdf     {px} x {int(H / 72 * DPI)} px")


def main() -> int:
    from scripts.build_documentation_pdf import measured

    s = measured()
    emit("architecture-system-layers", d_layers, s)
    emit("architecture-request-flow", d_flow, s)
    emit("architecture-trust-gates", d_gates, s)
    print(f"\n  written to {OUTDIR}{chr(92)}")
    print("  PowerPoint: Insert > Pictures > This Device, and pick the .svg "
          "(it stays sharp at any size)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
