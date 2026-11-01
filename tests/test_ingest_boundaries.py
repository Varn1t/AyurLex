"""Where the section splitter stops, starts and refuses to guess.

Every test here is a regression, and every one of them is the same shape of
bug: the ingester read something that looked like a provision number and was
not, or failed to read one that was. That class of failure is silent by
construction -- nothing in the output says "five sections are missing" -- so
it has to be pinned against the instrument's real structure instead.

The counts below are not what the parser happens to produce. They are what the
instruments actually contain, checked against the primary sources.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from samhita.ingest import GAZETTE_SEC, forward_run

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "provisions.jsonl"


@pytest.fixture(scope="module")
def records() -> list[dict]:
    if not CORPUS.exists():
        pytest.skip("corpus not built; run python samhita/ingest.py")
    return [json.loads(line) for line in CORPUS.open(encoding="utf-8")]


def numbered(records: list[dict], act_id: str) -> set[str]:
    """The numbered provisions of one instrument, schedule pages excluded."""
    return {r["section"] for r in records
            if r["act_id"] == act_id and not r["section"].startswith("p.")}


# --------------------------------------------------- what the Acts contain --
def test_fss_act_has_all_one_hundred_and_one_sections(records):
    secs = numbered(records, "IN.FSSA.2006")
    assert len(secs) == 101
    assert secs == {str(n) for n in range(1, 102)}


def test_the_2023_amendment_runs_to_section_43(records):
    """The bug this pins truncated the Act at section 38.

    Section 38 substitutes sections 55, 55A and 55B into the principal Act and
    quotes them in full, so "55B." appears at the head of a line. A scan that
    accepts it as the next section then rejects the real sections 39 to 43 for
    going backwards -- losing, among others, section 43, which is the
    rule-making power the new penalties regime hangs on.
    """
    secs = numbered(records, "IN.BDA_AMEND.2023")
    assert secs == {str(n) for n in range(1, 44)}
    assert "55B" not in secs and "55A" not in secs


def test_bd_rules_2024_has_twenty_five_rules(records):
    assert numbered(records, "IN.BD_RULES.2024") == {str(n) for n in range(1, 26)}


def test_ayurveda_aahara_has_thirteen_regulations(records):
    assert numbered(records, "IN.FSS_AAHARA.2022") == {
        str(n) for n in range(1, 14)}


def test_a_short_title_provision_with_no_rubric_is_still_found(records):
    """Section 1 opens "1. (1) This Act may be called ..." with no heading.

    Requiring a capital letter after the number dropped it, and dropping
    section 1 drops the commencement clause -- the provision that says when
    anything else in the instrument began to bind anyone.
    """
    assert GAZETTE_SEC.search("1. (1) This Act may be called the Foo Act, 2023.")
    for act_id in ("IN.BDA_AMEND.2023", "IN.FSS_AAHARA.2022",
                   "IN.BD_RULES.2024"):
        assert "1" in numbered(records, act_id), act_id


def test_a_clause_label_still_cannot_open_a_provision():
    """The widening admits "(1)" and must not admit "(a)".

    A clause label at the head of a line is extremely common in these PDFs;
    treating one as a provision start would split a section in half and cite
    the back half under a number that belongs to something else.
    """
    assert not GAZETTE_SEC.search("2. (a) 'Act' means the Food Safety Act;")
    assert not GAZETTE_SEC.search("14. (iii) the words shall be omitted;")


# ------------------------------------------- what the Schedules are cited as --
@pytest.mark.parametrize("act_id", [
    "IN.FSS_NUTRA.2016", "IN.FSS_CLAIMS.2018", "IN.FSS_AAHARA.2022",
    "IN.BD_RULES.2024",
])
def test_schedule_content_is_cited_as_a_page_not_a_provision(records, act_id):
    """A Schedule row is not a regulation, however much it looks like one.

    The Schedules are numbered lists -- "14. Vitamin B12 ... 1 µg" -- and
    letting them through the section splitter produces a record cited as
    "Regulation 14 of the FSS (Nutraceuticals) Regulations, 2016" whose text is
    a vitamin limit. That is a wrong citation, so the appendix is ingested as
    pages instead: retrievable, and correctly attributed.
    """
    pages = [r for r in records
             if r["act_id"] == act_id and r["section"].startswith("p.")]
    assert pages, f"{act_id} should carry its Schedules as page records"
    for r in pages:
        assert r["chapter"] == "Schedules"
        assert "Schedules" in r["hierarchy_path"]


def test_schedule_pages_do_not_overlap_the_numbered_provisions(records):
    """The two passes must partition the instrument, not both claim a page."""
    for act_id in ("IN.FSS_NUTRA.2016", "IN.FSS_CLAIMS.2018",
                   "IN.FSS_AAHARA.2022", "IN.BD_RULES.2024"):
        rs = [r for r in records if r["act_id"] == act_id]
        first_page = min(r["page_start"] for r in rs
                         if r["section"].startswith("p."))
        last_body = max(r["page_end"] for r in rs
                        if not r["section"].startswith("p."))
        assert last_body <= first_page, act_id


# ------------------------------------------------------ the scan itself -----
class _M:
    """The slice of re.Match that forward_run actually uses."""

    def __init__(self, num: str):
        self._num = num

    def group(self, _name: str) -> str:
        return self._num


def _run(nums: list[str], **kw) -> list[str]:
    return [m.group("num") for m in forward_run([_M(n) for n in nums], **kw)]


def _act(*tail: str) -> list[str]:
    """Sections 1..35 and then whatever the test is about.

    The scan starts from a high-water mark of -1, so an instrument has to open
    near section 1 -- a document whose first candidate is 36 is not a statute,
    it is a page of something else. Building the run in full keeps the fixture
    honest about that instead of relaxing the gap to make a fragment pass.
    """
    return [str(n) for n in range(1, 36)] + list(tail)


def test_one_interpolated_number_does_not_truncate_the_rest():
    assert _run(_act("36", "37", "38", "55", "39", "40", "41")) == _act(
        "36", "37", "38", "39", "40", "41")


def test_a_genuine_gap_is_kept():
    """A repealed section leaves a hole. Numbers after it still go forwards,
    so the lookahead has nothing to object to and the jump stands."""
    assert _run(["1", "2", "5", "6", "7"]) == ["1", "2", "5", "6", "7"]


def test_a_run_of_interpolations_is_stopped_by_the_ceiling():
    """Three quoted sections in a row defeat the lookahead. That is what
    max_provision is for, and it is hand-verified data, not a heuristic."""
    nums = _act("36", "37", "38", "55", "55A", "55B", "39", "40")
    assert _run(nums, max_provision=43) == _act("36", "37", "38", "39", "40")


def test_backwards_numbers_are_still_discarded():
    assert _run(["5", "6", "2", "7"]) == ["5", "6", "7"]
