"""SAMHITA ingest: primary-source PDFs -> structured provision records.

Design rules (Section 6 of the build spec):
  * Split on structural boundaries only. We split at SECTION level and never
    below, which structurally guarantees that a proviso or an Explanation can
    never be separated from its parent provision.
  * Every record carries the full hierarchy path and an authority rank.
  * Nothing is paraphrased. text is the verbatim extracted span with only a
    documented, reversible character-repair applied (see repair_text).
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "Dataset"
CORPUS = ROOT / "corpus"


# --------------------------------------------------------------------------
# Corpus registry. authority_rank follows the tiering in the build spec:
#   1 statutes | 2 rules/regulations | 3 notifications | 4 case law
#   5 official manuals | 6 pharmacopoeia & classical texts | 7 commentary
# --------------------------------------------------------------------------
@dataclass
class Source:
    act_id: str
    title: str
    short_title: str
    instrument_type: str
    authority_rank: int
    jurisdiction: str
    pdf: str
    # Layout profile: "gazette" (India Code PDFs), "kanoon" (indiankanoon.org),
    # "treaty" / "treaty_rules" (UN and WIPO typesetting), "prose"
    # (non-statutory reference material) or "table" (a ruled multi-column
    # table read row by row rather than line by line).
    layout: str
    # Pages to skip -- tables of contents / arrangement-of-sections front matter.
    body_starts_page: int = 0
    # Last page of this instrument's body, exclusive; 0 means "to the end".
    # Needed where one PDF carries two instruments: the India Code file for the
    # Drugs and Cosmetics Act also contains the Rules 1945, and section
    # numbering restarts at the boundary.
    body_ends_page: int = 0
    citable: bool = True
    # What a numbered provision is called in this instrument. Indian statutes
    # number Sections; treaties number Articles; the PCT Regulations number
    # Rules. Citing a treaty Article as a "Section" would be simply wrong.
    unit: str = "Section"
    # Free-text note shown with the instrument, e.g. that a treaty binds the
    # state and is not directly enforceable in India without implementation.
    force_note: str = ""


SOURCES: list[Source] = [
    Source("IN.PATENTS.1970", "The Patents Act, 1970", "Patents Act, 1970",
           "ACT", 1, "IN", "Patents Act 1970.pdf", "gazette", body_starts_page=8),
    Source("IN.PATENT_RULES.2003", "The Patents Rules, 2003", "Patents Rules, 2003",
           "RULES", 2, "IN", "The_Patent_Rules_2003.pdf", "gazette",
           body_starts_page=4, unit="Rule"),
    Source("IN.BDA.2002", "The Biological Diversity Act, 2002",
           "Biological Diversity Act, 2002",
           "ACT", 1, "IN", "The_Biological_Diversity_Act_2002.pdf", "kanoon"),
    Source("IN.DMR.1954",
           "The Drugs and Magic Remedies (Objectionable Advertisements) Act, 1954",
           "Drugs and Magic Remedies Act, 1954",
           "ACT", 1, "IN",
           "The_Drugs_And_Magic_Remedies_Objectionable_Advertisements_Act_1954.pdf",
           "kanoon"),
    # One India Code PDF, two instruments. The Act runs to the Schedules and
    # the Rules 1945 begin after them, restarting their numbering at 1 -- so
    # ingesting the file as a single instrument buried the Act's definitions
    # in a record labelled "Section 38" and cited every rule as a section of
    # the Act. Both are wrong citations.
    Source("IN.DCA.1940", "The Drugs and Cosmetics Act, 1940",
           "Drugs and Cosmetics Act, 1940", "ACT", 1, "IN",
           "DrugsandCosmeticsAct1940Rules1945.pdf", "gazette",
           body_starts_page=5, body_ends_page=38),
    Source("IN.DC_RULES.1945", "The Drugs and Cosmetics Rules, 1945",
           "Drugs and Cosmetics Rules, 1945", "RULES", 2, "IN",
           "DrugsandCosmeticsAct1940Rules1945.pdf", "gazette",
           body_starts_page=38, unit="Rule"),
    Source("IN.TM.1999", "The Trade Marks Act, 1999", "Trade Marks Act, 1999",
           "ACT", 1, "IN", "Trade Marks Act, 1999.pdf", "gazette", body_starts_page=6),
    Source("IN.GI.1999",
           "The Geographical Indications of Goods "
           "(Registration and Protection) Act, 1999",
           "GI Act, 1999", "ACT", 1, "IN",
           "The_Geographical_Indications_Of_Goods_Registration_And_Protection_Act_1999.pdf",
           "kanoon"),
    Source("IN.PPVFR.2001",
           "The Protection of Plant Varieties and Farmers Rights Act, 2001",
           "PPV&FR Act, 2001", "ACT", 1, "IN", "PPV&FR Act, 2001.pdf", "kanoon"),
    Source("IN.COPYRIGHT_RULES.1957", "The Copyright Rules, 1957",
           "Copyright Rules, 1957",
           "RULES", 2, "IN", "copyrightrules1957.pdf", "gazette", unit="Rule"),
    # SIH26045 names the Designs and Copyright regimes among the national
    # coverage. The Copyright *Rules* were already ingested; the Act itself
    # was not, which meant the regime could be cited only through its rules.
    Source("IN.DESIGNS.2000", "The Designs Act, 2000", "Designs Act, 2000",
           "ACT", 1, "IN", "The_Designs_Act_2000.pdf", "gazette"),
    Source("IN.COPYRIGHT.1957",
           "The Copyright Act, 1957 (as amended up to Act No. 7 of 2017)",
           "Copyright Act, 1957", "ACT", 1, "IN",
           "The_Copyright_Act_1957.pdf", "gazette"),

    # The 2024 amendment to the Patent Rules. SIH26045 names it explicitly, and
    # it post-dates the 2003 Rules already ingested above.
    Source("IN.PATENT_RULES.2024", "The Patents (Amendment) Rules, 2024",
           "Patents (Amendment) Rules, 2024", "RULES", 2, "IN",
           "The_Patents_Amendment_Rules_2024.pdf", "gazette", unit="Rule"),

    # ------------------------------------------------------------------
    # International layer. SIH26045 requires national and international
    # regimes to be answerable but kept "visibly separate", so every record
    # below carries a non-IN jurisdiction and the retriever never mixes the
    # two into one answer.
    #
    # A treaty binds India as a state; it is not directly enforceable in an
    # Indian court until implemented by domestic legislation. That is exactly
    # the kind of thing this assistant must not blur, so it is recorded on the
    # instrument itself rather than left to the model to remember.
    # ------------------------------------------------------------------
    Source("WTO.TRIPS.1994",
           "Agreement on Trade-Related Aspects of Intellectual Property "
           "Rights (TRIPS)", "TRIPS Agreement", "TREATY", 1, "WTO",
           "TRIPS_Agreement_WTO_1994.pdf", "treaty", unit="Article",
           force_note="Binds India as a WTO Member. Not directly enforceable "
                      "in Indian courts; given effect through the Patents Act "
                      "and allied legislation."),
    Source("CBD.1992", "Convention on Biological Diversity",
           "Convention on Biological Diversity", "TREATY", 1, "CBD",
           "Convention_on_Biological_Diversity_1992.pdf", "treaty",
           unit="Article",
           force_note="Implemented in India by the Biological Diversity Act, "
                      "2002 (as amended in 2023)."),
    Source("CBD.NAGOYA.2010",
           "Nagoya Protocol on Access to Genetic Resources and the Fair and "
           "Equitable Sharing of Benefits Arising from their Utilization",
           "Nagoya Protocol", "TREATY", 1, "CBD",
           "Nagoya_Protocol_ABS_2010.pdf", "treaty", unit="Article",
           force_note="India is a Party. Access-and-benefit-sharing duties are "
                      "given domestic effect through the Biological Diversity "
                      "Act and its Rules."),
    Source("WIPO.GRATK.2024",
           "WIPO Treaty on Intellectual Property, Genetic Resources and "
           "Associated Traditional Knowledge", "WIPO GRATK Treaty, 2024",
           "TREATY", 1, "WIPO", "WIPO_GRATK_Treaty_2024.pdf", "treaty",
           unit="Article",
           force_note="Adopted 24 May 2024. Establishes a patent-application "
                      "disclosure requirement for genetic resources and "
                      "associated traditional knowledge; not yet in force."),
    Source("WIPO.PCT.1970", "Patent Cooperation Treaty (PCT)",
           "PCT", "TREATY", 1, "PCT", "Patent_Cooperation_Treaty_PCT.pdf",
           "treaty", unit="Article", body_starts_page=5,
           force_note="Route for seeking patent protection in multiple "
                      "jurisdictions. An Indian resident must still comply "
                      "with Section 39 of the Patents Act before filing "
                      "abroad."),
    Source("WIPO.PCT_REGS", "Regulations under the Patent Cooperation Treaty",
           "PCT Regulations", "RULES", 2, "PCT",
           "Regulations_under_the_PCT.pdf", "treaty_rules", unit="Rule",
           body_starts_page=20),
    # Rank 5: official guidance, persuasive but expressly non-binding. It is
    # the answer to "can I sell this in the US", which the corpus could not
    # previously reach at all.
    Source("US.FDA.BOTANICAL",
           "FDA Botanical Drug Development - Guidance for Industry",
           "FDA Botanical Drug Guidance", "GUIDANCE", 5, "US",
           "FDA_Botanical_Drug_Development_Guidance.pdf", "prose",
           force_note="US FDA guidance. Non-binding recommendations, not law; "
                      "reflects the agency's current thinking on botanical "
                      "drug applications."),

    # ------------------------------------------------------------------
    # WHO layer. These are international instruments about the practice of
    # Ayurveda itself rather than about intellectual property, and they are
    # the first non-IP international material in the corpus. They are kept at
    # a non-IN jurisdiction for the same reason the treaties are: a WHO
    # benchmark is not Indian law and must never be quoted as though it were.
    # ------------------------------------------------------------------
    Source("WHO.AYURVEDA_BENCHMARKS",
           "WHO Benchmarks for the Practice of Ayurveda",
           "WHO Benchmarks for Ayurveda Practice", "GUIDANCE", 5, "WHO",
           "9789240042674-eng.pdf", "prose",
           force_note="World Health Organization benchmark document. "
                      "Recommendatory international guidance on training and "
                      "practice; it is not law in India and creates no "
                      "enforceable obligation on its own."),
    # Rank 6: a controlled vocabulary, authoritative for what a term MEANS and
    # for nothing else. 608 pages of Ayurveda terminology with Sanskrit,
    # IAST and English for each entry -- by some distance the best source in
    # the corpus for "what is X", which is the commonest question asked.
    Source("WHO.AYURVEDA_TERMS",
           "WHO International Standard Terminologies on Ayurveda",
           "WHO Ayurveda Terminologies", "REFERENCE", 6, "WHO",
           "9789240064935-eng.pdf", "table", citable=False,
           force_note="Standardised terminology, not a legal instrument."),

    # Rank 7: peer-reviewed commentary. Never citable as authority -- it is
    # one author's account -- but it is the only material in the corpus that
    # describes how the WHO benchmarks were actually arrived at, and how
    # standardisation is being implemented in practice.
    Source("REF.WHO_INTEGRATION",
           "Integration of Ayurveda and allopathic medicine: opinion of "
           "experts in the WHO benchmark working groups "
           "(J. Res. Ayurvedic Sci., 2023)",
           "JRAS: Ayurveda-allopathy integration (2023)",
           "COMMENTARY", 7, "WHO", "jras_96_23_R7.pdf", "prose",
           citable=False,
           force_note="Peer-reviewed commentary. Reports expert opinion, not "
                      "law and not WHO policy."),
    Source("REF.PANCHAKARMA_STD",
           "Standardisation of Panchakarma - A Review: Initiatives and "
           "Developments Advancing Ayurveda through Uniform Practices "
           "(The Academic, 2025)",
           "Panchakarma standardisation review (2025)",
           "COMMENTARY", 7, "IN", "50.pdf", "prose", citable=False,
           force_note="Peer-reviewed commentary. Describes standardisation "
                      "initiatives; not law."),

    # Rank 6: authoritative for facts of traditional use, never for law.
    Source("REF.TKDL", "About TKDL (Traditional Knowledge Digital Library)", "TKDL",
           "REFERENCE", 6, "IN", "About TKDL.pdf", "prose", citable=False),
    Source("REF.AYURVEDA", "Ayurveda at a Glance", "Ayurveda at a Glance",
           "REFERENCE", 6, "IN", "Ayurveda at a Glance.pdf", "prose", citable=False),
    Source("REF.SIDDHA", "Siddha at a Glance", "Siddha at a Glance",
           "REFERENCE", 6, "IN", "Siddha at Glance.pdf", "prose", citable=False),
    Source("REF.UNANI", "Unani at a Glance", "Unani at a Glance",
           "REFERENCE", 6, "IN", "Unani at Glance.pdf", "prose", citable=False),
    Source("REF.SOWARIGPA", "Sowa-Rigpa at a Glance", "Sowa-Rigpa at a Glance",
           "REFERENCE", 6, "IN", "Sowarigpa at a Glance.pdf", "prose", citable=False),
]

SOURCES_BY_ID = {s.act_id: s for s in SOURCES}


# --------------------------------------------------------------------------
# Character repair.
#
# The India Code PDFs ship a broken ToUnicode CMap: em-dashes and curly quotes
# both extract as U+FFFD. This is a deterministic, rule-based repair -- it
# never rewrites a word, only restores punctuation, so the statutory wording
# stays verbatim. text_raw keeps the untouched extraction for audit.
# --------------------------------------------------------------------------
_WORDISH = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789)].,;")


def repair_text(s: str) -> str:
    out = []
    for i, ch in enumerate(s):
        if ch != "�":
            out.append(ch)
            continue
        prev = s[i - 1] if i else " "
        # Look ahead past whitespace: a section heading separator is followed by
        # the start of a sentence; a quote is followed by a lowercase word.
        j = i + 1
        while j < len(s) and s[j] in " \n\t":
            j += 1
        nxt = s[j] if j < len(s) else " "
        gap = j > i + 1
        if prev in ".,;" or (prev in _WORDISH and nxt.isupper() and not gap):
            out.append("—")            # heading separator em dash
        elif prev.isspace() or prev in "([":
            out.append("“")            # opening quote
        else:
            out.append("”")            # closing quote
    return "".join(out)


def normalise_ws(s: str) -> str:
    s = s.replace(" ", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


# --------------------------------------------------------------------------
# Section detection
# --------------------------------------------------------------------------
# Gazette layout:  "3. What are not inventions.-The following are not..."
# Kanoon layout:   "3. Certain persons not to undertake Biodiversity activities"
# A substituted section carries its amendment bracket first: "3[39. Residents
# not to apply...". Without the optional prefix the whole section is missed.
GAZETTE_SEC = re.compile(
    r"^[ \t]*(?:\d{1,2}\[)?(?P<num>\d{1,3}[A-Z]{0,2})\.[ \t]*"
    r"(?P<rest>[A-Z\[][^\n]{0,200})$", re.M
)
KANOON_SEC = re.compile(
    r"^[ \t]*(?:\d{1,2}\[)?(?P<num>\d{1,3}[A-Z]{0,2})\.[ \t]*"
    r"(?P<rest>[A-Z][^\n]{0,200})$", re.M
)

# Treaty layout. TRIPS writes "Article 3" and puts the rubric on the NEXT
# line; the GRATK treaty shouts "ARTICLE 3"; the PCT Regulations number in
# "Rule 31". Indian statutes keep the rubric on the same line as the number,
# so the section patterns above cannot be reused -- for a treaty the heading
# has to be picked up across the newline.
TREATY_ART = re.compile(
    # WTO puts "Article 3" on one line; the UN treaty typesetting breaks it
    # as "Article" / "3" on two. Both have to match, or the whole instrument
    # silently yields nothing.
    r"^[ \t]*(?:ARTICLE|Article)[ \t]*\n?[ \t]*"
    r"(?P<num>\d{1,3}(?:bis|ter|quater)?)[ \t]*[.:]?[ \t]*\n+"
    r"[ \t]*(?P<rest>[^\n]{0,200})$", re.M
)
TREATY_RULE = re.compile(
    r"^[ \t]*Rule[ \t]*\n?[ \t]*"
    r"(?P<num>\d{1,3}(?:bis|ter|quater)?)[ \t]*[.:]?[ \t]*\n+"
    r"[ \t]*(?P<rest>[^\n]{0,200})$", re.M
)

CHAPTER = re.compile(r"^[ \t]*CHAPTER[ \t]+([IVXLC]+)[ \t]*$", re.M)
HEADING_SPLIT = re.compile(r"[—.](?=\s|—|$)")
TOC_HINT = re.compile(r"^[ \t]*\d{1,3}[A-Z]{0,2}\.[ \t]+[^\n]{1,120}\.?[ \t]*$")


@dataclass
class Provision:
    corpus_id: str
    act_id: str
    act_title: str
    instrument_type: str
    authority_rank: int
    jurisdiction: str
    citable: bool
    chapter: str | None
    section: str
    heading: str
    hierarchy_path: str
    text: str
    text_raw: str
    page_start: int
    page_end: int
    source_pdf: str
    retrieved_on: str
    unit: str = "Section"
    force_note: str = ""
    effective_from: str | None = None
    effective_to: str | None = None
    clauses: dict[str, str] = field(default_factory=dict)
    amendment_notes: list[str] = field(default_factory=list)


# The two layouts space their clauses differently: India Code writes "(a) an
# invention..." and Indian Kanoon writes "(a)the procurement...". Requiring the
# trailing space silently indexes zero clauses for every Kanoon-sourced Act.
# No constraint on what precedes the bracket. The two layouts differ wildly --
# India Code writes "(a) an invention...", Indian Kanoon writes "; or(b)the
# maintenance..." with no separator at all -- and any prefix rule tight enough
# to exclude cross-references silently indexes zero clauses for one of them.
# Cross-references like "clause (d) of section 2" do match here, but they are
# short, and split_clauses keeps the LONGEST body per label, so the real clause
# always wins.
# Three letters, not two: the Drugs and Cosmetics Act definitions run to
# (aaa) "cosmetic" and (aab), and a two-letter cap makes those clauses
# impossible to pin-cite. Roman numerals were already covered separately, so
# the widening adds real labels and a handful of harmless three-letter words
# that lose anyway -- split_clauses keeps the longest body per label.
CLAUSE_RE = re.compile(
    r"(?:\d+\[)?\((?P<lbl>[a-z]{1,3}|[ivx]{1,4}|\d{1,2}[A-Z]?)\)"
)


def split_clauses(text: str) -> dict[str, str]:
    """Index sub-clauses for pin-cites. The parent text is never split -- this
    is an *index into* the section, so a proviso can never be orphaned."""
    marks = [(m.start(), m.group("lbl")) for m in CLAUSE_RE.finditer(text)]
    out: dict[str, str] = {}
    for i, (pos, lbl) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        body = text[pos:end].strip()
        if len(body) > 15 and len(body) > len(out.get(lbl, "")):
            out[lbl] = body
    return out


KANOON_NOISE = re.compile(
    r"^\s*(Indian Kanoon\s*-\s*http\S*.*|.*indiankanoon\.org.*)\s*$", re.I
)
PAGE_NUM = re.compile(r"^\s*\d{1,4}\s*$")
WATERMARK = re.compile(r"^\s*(IndiaCode|www\.\S+)\s*$", re.I)
# Footnote apparatus in India Code PDFs: "4. Ins. by Act 38 of 2002, s. 3 ..."
AMENDMENT_NOTE = re.compile(
    r"^\s*\d{1,2}\.\s*(Ins\.|Subs\.|Omitted|Cl\.|Sub-clause|Certain words|"
    r"The words|Explanation|Added|Rep\.|Now|Vide|Received)", re.I
)


UNIT_WORD = re.compile(r"^(?:ARTICLE|Article|Rule|RULE)$")


def _reading_order(lines: list[tuple], width: float):
    """Sort key that reads a two-column page column-by-column.

    The UN treaty typesetting (CBD, the Nagoya Protocol) sets the operative
    text in two columns. Sorting purely by y interleaves the two, which turns
    "Article 5 / Fair and Equitable Benefit-sharing" into a sentence spliced
    out of both columns -- the headings stop being recognisable and the whole
    instrument silently ingests as nothing.

    Detection is per page, not per document, because the same treaty sets its
    annexes in a single column. A page counts as two-column only when both
    halves carry a real share of the lines and almost nothing straddles the
    midline, so a single-column page keeps its existing top-to-bottom order
    and the Indian gazette PDFs are unaffected.
    """
    mid = width / 2.0
    left = [t for t in lines if t[4] <= mid + 6]
    right = [t for t in lines if t[3] >= mid - 6]
    straddle = [t for t in lines if t[3] < mid - 6 < mid + 6 < t[4]]
    n = len(lines)
    two_col = (
        n >= 8
        and len(left) >= 0.2 * n
        and len(right) >= 0.2 * n
        and len(straddle) <= 0.15 * n
    )
    if not two_col:
        return lambda t: (0, t[0])
    # Column index first, then y within the column.
    return lambda t: (0 if t[4] <= mid + 6 else 1, t[0])


def page_body_text(page) -> str:
    """Extract a page's *body* text, dropping the footnote apparatus.

    India Code PDFs set the body at ~11pt and the amendment footnotes at ~9pt
    in a block at the foot of the page. Footnotes restart numbering on every
    page ("1. Ins. by Act 15 of 2005..."), so a naive linear extraction reads
    them as new sections and silently overwrites the real provision -- that is
    exactly how Patents Act s.3 disappears. We therefore find the last line set
    in the body size and drop smaller-font lines below it. Chapter headings are
    also small-caps 9pt but sit *above* body text, so they survive.
    """
    d = page.get_text("dict")
    lines = []
    for b in d["blocks"]:
        for ln in b.get("lines", []):
            spans = [s for s in ln["spans"] if s["text"].strip()]
            if not spans:
                continue
            size = max(round(s["size"], 1) for s in spans)
            y = ln["bbox"][1]
            txt = "".join(s["text"] for s in ln["spans"])
            lines.append((y, size, txt, ln["bbox"][0], ln["bbox"][2]))
    if not lines:
        return "", []
    # Reading order has to be settled before anything is discarded, because
    # whether a bare number is page furniture or an article number depends on
    # the line that precedes it *in reading order*.
    lines.sort(key=_reading_order(lines, page.rect.width))

    # Treaty typesetting puts the unit word and its number on separate lines
    # ("Article" / "5"), so the number is indistinguishable from a page number
    # on its own. Protect it when the preceding line is the bare unit word --
    # without this, every UN-typeset treaty loses all of its article numbers
    # and the whole instrument ingests as zero provisions.
    protected = {
        i for i in range(1, len(lines))
        if UNIT_WORD.match(lines[i - 1][2].strip())
        and PAGE_NUM.match(lines[i][2])
    }

    # Drop page furniture: a bare page number is body-sized and sits *below*
    # the footnote block, so leaving it in would anchor last_body_y at the
    # bottom of the page and defeat the footnote test entirely.
    lines = [t for i, t in enumerate(lines)
             if i in protected or not PAGE_NUM.match(t[2])]
    if not lines:
        return "", []

    sizes = [sz for _, sz, _, _, _ in lines]
    body_size = max(set(sizes),
                    key=lambda s: sum(len(t) for _, z, t, _, _ in lines if z == s))
    body_ys = [y for y, sz, _, _, _ in lines if sz >= body_size - 0.6]
    last_body_y = max(body_ys) if body_ys else 1e9

    kept, notes = [], []
    for y, size, txt, _, _ in lines:
        small = size < body_size - 0.6
        if small and (y > last_body_y or AMENDMENT_NOTE.match(txt)):
            notes.append(txt.strip())     # footnote apparatus
            continue
        if KANOON_NOISE.match(txt) or WATERMARK.match(txt):
            continue                      # Kanoon page furniture
        kept.append(txt)
    return "\n".join(kept) + "\n", notes


def page_texts(pdf: Path) -> tuple[list[str], list[list[str]]]:
    doc = pymupdf.open(pdf)
    pairs = [page_body_text(p) for p in doc]
    return [b for b, _ in pairs], [n for _, n in pairs]


def looks_like_toc(page: str) -> bool:
    lines = [ln for ln in page.splitlines() if ln.strip()]
    if len(lines) < 8:
        return False
    hits = sum(1 for ln in lines if TOC_HINT.match(ln))
    return hits / len(lines) > 0.55


def page_table_text(page) -> tuple[str, list[str]]:
    """Extract a ruled table row by row instead of line by line.

    The WHO terminology volume is a five-column table -- term ID, English
    term, description, Sanskrit in IAST, Sanskrit -- and reading it in plain
    layout order tears every entry apart: the English descriptions come out in
    one region of the page and the Sanskrit headwords in another, so a search
    for "vamana" lands on a page that contains it and a description that
    belongs to some other term. A glossary whose terms are not adjacent to
    their definitions is not a glossary.

    So lines are clustered into rows by their y coordinate and ordered by x
    within the row, which puts each term next to its own definition. The
    tolerance is generous (4pt) because the Devanagari column is typeset a
    point higher than the Latin columns on the same row.

    This changes only how the page is READ. Nothing is paraphrased or
    reordered within a cell, and the chunking is still one record per page.
    """
    lines = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            txt = "".join(s["text"] for s in ln["spans"]).strip()
            if not txt or PAGE_NUM.match(txt):
                continue
            lines.append((ln["bbox"][1], ln["bbox"][0], txt))
    if not lines:
        return "", []

    lines.sort(key=lambda t: (t[0], t[1]))
    rows: list[list[tuple[float, str]]] = []
    row_y = None
    for y, x, txt in lines:
        if row_y is None or y - row_y > 4.0:
            rows.append([])
            row_y = y
        rows[-1].append((x, txt))

    out = []
    for row in rows:
        row.sort(key=lambda t: t[0])
        out.append(" ".join(txt for _, txt in row))
    return "\n".join(out) + "\n", []


def page_texts_table(pdf: Path) -> tuple[list[str], list[list[str]]]:
    doc = pymupdf.open(pdf)
    pairs = [page_table_text(p) for p in doc]
    return [b for b, _ in pairs], [n for _, n in pairs]


def ingest_source(src: Source) -> list[Provision]:
    pdf = DATASET / src.pdf
    if src.layout == "table":
        pages, footnotes = page_texts_table(pdf)
    else:
        pages, footnotes = page_texts(pdf)
    today = date.today().isoformat()

    if src.layout in ("prose", "table"):
        return ingest_prose(src, pages, today)

    # One blob with page offsets so every span keeps a real page number.
    blob_parts, offsets, cursor = [], [], 0
    end_page = src.body_ends_page or len(pages)
    for pno, ptext in enumerate(pages):
        if (pno < src.body_starts_page or pno >= end_page
                or looks_like_toc(ptext)):
            ptext = ""
        blob_parts.append(ptext)
        offsets.append((cursor, cursor + len(ptext), pno))
        cursor += len(ptext)
    blob = "".join(blob_parts)

    def page_of(pos: int) -> int:
        for lo, hi, pno in offsets:
            if lo <= pos < hi:
                return pno + 1
        return 0

    def chapter_of(pos: int) -> str | None:
        cur = None
        for cpos, cnum in chapters:
            if cpos <= pos:
                cur = cnum
            else:
                break
        return f"Chapter {cur}" if cur else None

    chapters = [(m.start(), m.group(1)) for m in CHAPTER.finditer(blob)]
    pattern = {
        "gazette": GAZETTE_SEC,
        "kanoon": KANOON_SEC,
        "treaty": TREATY_ART,
        "treaty_rules": TREATY_RULE,
    }[src.layout]

    # Keep only forward-progressing section numbers -- this discards stray TOC
    # echoes, page numbers and list items that look like section starts.
    kept, last = [], -1
    for m in pattern.finditer(blob):
        n = int(re.match(r"\d+", m.group("num")).group())
        if n >= last and n - last < 25:
            kept.append(m)
            last = max(last, n)

    provisions: list[Provision] = []
    for i, m in enumerate(kept):
        start = m.start()
        end = kept[i + 1].start() if i + 1 < len(kept) else len(blob)
        raw = blob[start:end]
        if len(raw.strip()) < 60:
            continue
        fixed = normalise_ws(repair_text(raw))
        rest = repair_text(m.group("rest"))
        heading = HEADING_SPLIT.split(rest, 1)[0].strip(" .—")
        heading = re.sub(r"\s+", " ", heading)[:160]
        sec = m.group("num")
        ch = chapter_of(start)
        path = " > ".join(
            x for x in [src.short_title, ch, f"{src.unit} {sec}"] if x)
        provisions.append(
            Provision(
                corpus_id=f"{src.act_id}::{src.unit[0]}{sec}",
                act_id=src.act_id,
                act_title=src.title,
                instrument_type=src.instrument_type,
                authority_rank=src.authority_rank,
                jurisdiction=src.jurisdiction,
                citable=src.citable,
                chapter=ch,
                section=sec,
                heading=heading,
                hierarchy_path=path,
                text=fixed,
                text_raw=raw,
                page_start=page_of(start),
                page_end=page_of(max(start, end - 1)),
                source_pdf=src.pdf,
                retrieved_on=today,
                unit=src.unit,
                force_note=src.force_note,
                clauses=split_clauses(fixed),
                amendment_notes=notes_for(footnotes, page_of(start),
                                          page_of(max(start, end - 1))),
            )
        )
    return dedupe(provisions)



def notes_for(footnotes: list[list[str]], p_start: int, p_end: int) -> list[str]:
    """Amendment footnotes from the pages a provision spans.

    These carry the commencement dates ("w.e.f. 20-5-2003") that make
    time-travel compilation answerable from the primary source instead of from
    anyone's recollection.
    """
    out: list[str] = []
    for pno in range(max(p_start, 1), max(p_end, p_start) + 1):
        if 0 < pno <= len(footnotes):
            out.extend(footnotes[pno - 1])
    return out


WEF = re.compile(r"w\.e\.f\.\s*(\d{1,2})-(\d{1,2})-(\d{4})", re.I)


def commencement_dates(notes: list[str]) -> list[str]:
    """ISO dates mentioned in a provision's amendment notes.

    Deliberately NOT wired to `effective_from`, and it must stay that way
    until the data supports it. The notes are collected per *page*, so a
    footnote reading "Ins. by Act 15 of 2005, w.e.f. 1-1-2005" may be dating a
    single inserted clause -- or a neighbouring provision that merely shares
    the page. Writing that date onto the provision would mean an as_of query
    for 2004 excluded the whole of Patents Act s.3, which has been in force
    since 1970.

    So `in_force()` currently passes everything, and the temporal filter is
    scaffolding rather than a working guarantee. Closing that gap needs
    provision-level commencement data, not a better regex over footnotes; it
    is recorded in SIH26045-problem-statement-alignment.md as an open item
    rather than papered over here.
    """
    out = []
    for n in notes:
        for d_, m_, y_ in WEF.findall(n):
            try:
                out.append(date(int(y_), int(m_), int(d_)).isoformat())
            except ValueError:
                continue
    return sorted(set(out))


def ingest_prose(src: Source, pages: list[str], today: str) -> list[Provision]:
    """Rank-6 reference material: page-level chunks, factual use only."""
    out = []
    for pno, ptext in enumerate(pages):
        fixed = normalise_ws(repair_text(ptext))
        if len(fixed) < 200:
            continue
        head = re.sub(r"\s+", " ", fixed[:90])
        out.append(
            Provision(
                corpus_id=f"{src.act_id}::P{pno + 1}",
                act_id=src.act_id, act_title=src.title,
                instrument_type=src.instrument_type,
                authority_rank=src.authority_rank, jurisdiction=src.jurisdiction,
                citable=src.citable, chapter=None, section=f"p.{pno + 1}",
                heading=head, hierarchy_path=f"{src.short_title} > page {pno + 1}",
                text=fixed, text_raw=ptext, page_start=pno + 1, page_end=pno + 1,
                source_pdf=src.pdf, retrieved_on=today,
                unit=src.unit, force_note=src.force_note,
            )
        )
    return out


# A real section is rarely longer than this. Anything much bigger is not one
# provision -- it is a region the section splitter failed to parse, almost
# always a Schedule made of numbered list items ("178. Ergot, alkaloids of...")
# that look exactly like section starts. The Drugs and Cosmetics PDF produces a
# 574,000-character "section" this way, which then poisons every retrieval it
# appears in.
MAX_CHUNK = 6000
SUBSECTION = re.compile(r"(?=(?:^|\s)(?:\d{1,2}\[)?\(\d{1,2}[A-Z]?\)\s)")


def subchunk(p: Provision) -> list[Provision]:
    """Split an oversized record at SUB-SECTION boundaries.

    Sub-section is still a legitimate parent for a proviso or an Explanation, so
    this does not violate the never-orphan-a-proviso rule: a proviso always
    travels with the sub-section it qualifies. Where there are no sub-section
    markers at all (a Schedule of drug names), we fall back to paragraph
    boundaries, which is safe because such a list has no provisos to break.
    """
    if len(p.text) <= MAX_CHUNK:
        return [p]

    pieces = [s for s in SUBSECTION.split(p.text) if s.strip()]
    if len(pieces) < 2 or max(len(s) for s in pieces) > MAX_CHUNK:
        pieces = _pack(re.split(r"\n\s*\n", p.text), MAX_CHUNK)
    pieces = _pack(pieces, MAX_CHUNK)

    out = []
    for i, body in enumerate(pieces, 1):
        out.append(
            Provision(
                corpus_id=f"{p.corpus_id}#part{i}",
                act_id=p.act_id, act_title=p.act_title,
                instrument_type=p.instrument_type,
                authority_rank=p.authority_rank, jurisdiction=p.jurisdiction,
                citable=p.citable, chapter=p.chapter, section=p.section,
                heading=p.heading,
                hierarchy_path=f"{p.hierarchy_path} > part {i} of {len(pieces)}",
                text=body.strip(), text_raw=body,
                page_start=p.page_start, page_end=p.page_end,
                source_pdf=p.source_pdf, retrieved_on=p.retrieved_on,
                unit=p.unit, force_note=p.force_note,
                effective_from=p.effective_from, effective_to=p.effective_to,
                clauses=split_clauses(body),
                amendment_notes=p.amendment_notes,
            )
        )
    return out


def _pack(pieces: list[str], limit: int) -> list[str]:
    """Merge fragments up to the limit, and hard-split any single fragment that
    still exceeds it."""
    out: list[str] = []
    cur = ""
    for piece in pieces:
        if len(piece) > limit:
            if cur:
                out.append(cur)
                cur = ""
            for j in range(0, len(piece), limit):
                out.append(piece[j : j + limit])
            continue
        if len(cur) + len(piece) + 1 > limit and cur:
            out.append(cur)
            cur = piece
        else:
            cur = f"{cur} {piece}".strip()
    if cur:
        out.append(cur)
    return out


def dedupe(provs: list[Provision]) -> list[Provision]:
    """A section number can legitimately recur (Act + Rules in one PDF).
    Keep the longest body for each id."""
    best: dict[str, Provision] = {}
    for p in provs:
        cur = best.get(p.corpus_id)
        if cur is None or len(p.text) > len(cur.text):
            best[p.corpus_id] = p
    out: list[Provision] = []
    for p in best.values():
        out.extend(subchunk(p))
    return sorted(out, key=lambda p: (p.act_id, p.page_start, p.corpus_id))


def main() -> None:
    CORPUS.mkdir(exist_ok=True)
    out = CORPUS / "provisions.jsonl"
    total = 0
    with out.open("w", encoding="utf-8") as fh:
        for src in SOURCES:
            if not (DATASET / src.pdf).exists():
                print(f"  !! missing {src.pdf}")
                continue
            provs = ingest_source(src)
            for p in provs:
                fh.write(json.dumps(asdict(p), ensure_ascii=False) + "\n")
            total += len(provs)
            print(f"  {src.act_id:26s} {len(provs):4d} provisions  ({src.pdf})")
    print(f"\nwrote {total} records -> {out}")


if __name__ == "__main__":
    main()
