"""sakti -- the IP-SAKTI Sahayak command line.

    python cli.py compile fixtures/triphala_classical.json --as-of 2026-08-31
    python cli.py compile fixtures/triphala_classical.json --autofix
    python cli.py timetravel fixtures/triphala_classical.json 2002-01-01 2026-08-31
    python cli.py rules
    python cli.py resolve गुडूची Giloy Brahmi
    python cli.py reproduce fixtures/triphala_classical.json --runs 10
"""
from __future__ import annotations

import argparse

import sys
from datetime import date
from pathlib import Path

# Windows consoles default to a legacy code page; the corpus is Devanagari and
# em-dash heavy, so make stdout explicitly UTF-8 rather than crashing on print.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.compiler import (  # noqa: E402
    apply_autofix,
    compile_formulation,
    diff_findings,
)
from core.resolver import load_resolver  # noqa: E402
from core.schema import Formulation, Severity  # noqa: E402
from samhita.index import load_corpus  # noqa: E402
from sutra.loader import load_rules  # noqa: E402

ROOT = Path(__file__).resolve().parent

BAR = "=" * 78
SEV_MARK = {
    Severity.BLOCKER: "[BLOCKER]    ",
    Severity.WARNING: "[WARNING]    ",
    Severity.OPPORTUNITY: "[OPPORTUNITY]",
    Severity.INFO: "[INFO]       ",
}


def load_formulation(path: str) -> Formulation:
    return Formulation.model_validate_json(Path(path).read_text(encoding="utf-8"))


def wrap(text: str, width: int = 74, indent: str = "    ") -> str:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return "\n".join(indent + ln for ln in lines)


def print_resolution(result) -> None:
    print("\nRESOLVER — ingredient names to canonical taxa")
    print("-" * 78)
    for r in result.cbom.resolution_log:
        mark = "OK " if r["auto_accepted"] else "?? "
        target = r["resolved_to"] or ", ".join(r["candidates"]) or "no candidate"
        print(f"  {mark}{r['input']:<22} -> {target:<34} "
              f"[{r['path']}, conf {r['confidence']:.2f}]")


def print_findings(result, show_citations: bool = True) -> None:
    cbom = result.cbom
    print(f"\nFINDINGS — {len(cbom.findings)} emitted, "
          f"{cbom.suppressed_count} suppressed")
    print("-" * 78)
    for f in cbom.findings:
        print(f"\n{SEV_MARK[f.severity]} {f.rule_id}   [{f.lane} lane]")
        print(f"    {f.instrument} — {f.provision}")
        print(wrap(f.statement))
        print(f"    groundedness {f.groundedness:.2f} | {f.verification.value}")
        if show_citations:
            for c in f.citations:
                print(f"    └─ CITE {c.corpus_id}  ({c.source_pdf} p.{c.page})")
                print(f"       {c.hierarchy_path}")
                q = " ".join(c.quote.split())
                print(f"       \"{q[:200]}{'…' if len(q) > 200 else ''}\"")
        for fix in f.autofix:
            tick = "available" if fix.available else f"blocked: {fix.unavailable_reason}"
            print(f"    └─ AUTOFIX {fix.id}  ({tick})")
            print(wrap(fix.description, indent="       "))


def print_matrix(result) -> None:
    print("\nSETU — jurisdiction matrix")
    print("-" * 78)
    print(f"  {'JURIS':<6} {'STATUS':<12} {'CITES':<6} NEXT ACTION")
    for row in result.cbom.jurisdiction_matrix:
        print(f"  {row.jurisdiction.value:<6} {row.status.value:<12} "
              f"{row.citation_count:<6} {row.next_action}")
    for row in result.cbom.jurisdiction_matrix:
        print(f"\n  [{row.jurisdiction.value}] patentability : {row.patentability}")
        print(f"       disclosure duty: {row.disclosure_duty}")
        print(f"       access / ABS   : {row.abs_requirement}")
        print(f"       market route   : {row.market_route}")


def print_obligations(result) -> None:
    if not result.cbom.obligations:
        return
    print(f"\nNIYAMA — {len(result.cbom.obligations)} obligation(s) triggered")
    print("-" * 78)
    for o in result.cbom.obligations:
        print(f"  * {o.provision} — {o.duty}")
        print(f"      discharged by: {o.discharged_by}  ({o.when})")


def print_summary(result) -> None:
    cbom = result.cbom
    counts = {s: sum(1 for f in cbom.findings if f.severity is s) for s in Severity}
    print(f"\n{BAR}")
    print(f"  C-BOM  {cbom.formulation_name}")
    print(f"  fingerprint {cbom.formulation_fingerprint} | as-of {cbom.as_of} | "
          f"digest {cbom.digest()[:16]}")
    print(f"  {counts[Severity.BLOCKER]} blockers | "
          f"{counts[Severity.WARNING]} warnings | "
          f"{counts[Severity.OPPORTUNITY]} opportunities | "
          f"{counts[Severity.INFO]} info")
    print(f"  groundedness {cbom.groundedness_score:.2f} | "
          f"{len(cbom.obligations)} obligations | "
          f"{len(cbom.abstentions)} abstentions")
    if result.integrity_problems:
        print(f"  !! CITATION INTEGRITY: {len(result.integrity_problems)} problem(s)")
        for p in result.integrity_problems:
            print(f"     {p}")
    else:
        print("  citation integrity: every quote re-verified against the source PDF")
    if cbom.abstentions:
        print("\n  ABSTENTIONS (matched the facts, not asserted):")
        for a in cbom.abstentions:
            print(wrap(a, indent="     "))
    print(BAR)


# ------------------------------------------------------------- commands ----
def cmd_compile(args) -> int:
    f = load_formulation(args.file)
    as_of = date.fromisoformat(args.as_of)
    result = compile_formulation(f, as_of=as_of)

    print(BAR)
    print(f"  IP-SAKTI Sahayak — compiling '{f.name}'  (as-of {as_of})")
    print(BAR)
    print_resolution(result)
    print_findings(result, show_citations=not args.brief)
    print_obligations(result)
    print_matrix(result)
    print_summary(result)

    if args.autofix:
        run_autofix(f, result, as_of)

    if args.out:
        Path(args.out).write_text(
            result.cbom.model_dump_json(indent=2), encoding="utf-8"
        )
        print(f"\nC-BOM JSON written to {args.out}")
    if args.html:
        from cbom.report import write_report

        write_report(result.cbom, Path(args.html))
        print(f"C-BOM report written to {args.html}")
    return 1 if result.blockers and args.strict else 0


def run_autofix(f, result, as_of) -> None:
    print(f"\n{BAR}")
    print("  AUTOFIX — compile, fix, recompile")
    print(BAR)
    overrides: dict = {}
    current = result
    for finding in list(result.blockers):
        fix = next((x for x in finding.autofix if x.available), None)
        if not fix:
            print(f"\n  {finding.rule_id}: no autofix available on these facts")
            continue
        print(f"\n  applying {fix.id} for {finding.rule_id}")
        after, overrides = apply_autofix(f, fix, as_of=as_of,
                                         base_overrides=overrides)
        d = diff_findings(current, after)
        for r in d["cleared"]:
            print(f"    CLEARED     {r}")
        for r in d["introduced"]:
            print(f"    INTRODUCED  {r}")
        current = after
    before_b = {x.rule_id for x in result.blockers}
    after_b = {x.rule_id for x in current.blockers}
    print(f"\n  blockers {len(before_b)} -> {len(after_b)}")
    if before_b - after_b:
        print(f"  proved cleared by recompilation: {sorted(before_b - after_b)}")
    if after_b:
        print(f"  still blocking: {sorted(after_b)}")


def cmd_timetravel(args) -> int:
    f = load_formulation(args.file)
    results = []
    for d in args.dates:
        r = compile_formulation(f, as_of=date.fromisoformat(d))
        results.append((d, r))

    print(BAR)
    print(f"  TIME TRAVEL — '{f.name}' under the law as it stood")
    print(BAR)
    for d, r in results:
        ids = [x.rule_id for x in r.cbom.findings]
        print(f"\n  as-of {d}: {len(ids)} finding(s), "
              f"{len(r.blockers)} blocker(s)")
        for x in r.cbom.findings:
            print(f"      {SEV_MARK[x.severity]} {x.rule_id}")
    for i in range(1, len(results)):
        (d0, r0), (d1, r1) = results[i - 1], results[i]
        diff = diff_findings(r0, r1)
        print(f"\n  DIFF {d0} -> {d1}")
        for r in diff["introduced"]:
            print(f"      + {r}   (obligation appeared)")
        for r in diff["cleared"]:
            print(f"      - {r}   (no longer in force)")
        if not diff["introduced"] and not diff["cleared"]:
            print("      (no change)")
    print(f"\n{BAR}")
    return 0


def cmd_rules(args) -> int:
    corpus = load_corpus()
    rules = load_rules(corpus=corpus)
    print(f"{len(rules)} rule(s) loaded from sutra/rules/\n")
    print(f"  {'RULE ID':<38} {'SEV':<12} {'STATUS':<11} CITATIONS")
    print("-" * 78)
    for r in rules:
        cites = ", ".join(c.corpus_id for c in r.citations)
        print(f"  {r.id:<38} {r.severity.value:<12} "
              f"{r.verification.value:<11} {cites}")
        for note in r.verification_notes:
            print(f"      ! {note}")
    verified = sum(1 for r in rules if r.verification.value == "VERIFIED")
    print(f"\n  {verified}/{len(rules)} VERIFIED against primary sources")
    print(f"  corpus: {len(corpus.records)} provisions")
    return 0 if verified == len(rules) else 1


def cmd_resolve(args) -> int:
    r = load_resolver()
    for name in args.names:
        res = r.resolve(name)
        target = res.taxon or ", ".join(res.candidates) or "(no candidate)"
        print(f"  {name:<24} -> {target:<34} "
              f"[{res.path}, conf {res.confidence:.2f}, "
              f"{'accepted' if res.is_accepted else 'PROPOSED — needs confirmation'}]")
    return 0


def cmd_chat(args) -> int:
    """Interactive RAG chat. The engine answers; chat is the interface."""
    from datetime import date as _date

    from rag.chat import Session, respond
    from rag.answer import pick_backend

    session = Session(as_of=_date.fromisoformat(args.as_of),
                      backend_pref=args.backend)
    backend = pick_backend(args.backend)

    print(BAR)
    print("  IP-SAKTI Sahayak — ask about AYURVEDA/IP compliance, or describe")
    print("  a formulation and I will compile it.")
    print(f"  backend: {backend.name}  |  law as-of {session.as_of}")
    print("  try:  can I patent a traditional ayurvedic formulation?")
    print("        my churna contains amla, haritaki and bibhitaki")
    print("        apply the fixes")
    print("  Ctrl-C or 'exit' to quit.")
    print(BAR)

    while True:
        try:
            q = input("\nyou > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not q:
            continue
        if q.lower() in {"exit", "quit", ":q"}:
            return 0

        reply = respond(q, session, backend=backend)
        print(f"\nsakti [{reply.intent}] >")
        print(wrap(reply.text, width=76, indent="  "))
        if reply.answer and reply.answer.citations:
            print("\n  sources:")
            for c in reply.answer.citations:
                print(f"    - {c.instrument}, {c.provision}")
                print(f"      {c.source_pdf} p.{c.page}  [{c.corpus_id}]")
        if reply.answer and not reply.answer.abstained:
            print(f"\n  groundedness {reply.answer.groundedness:.2f}"
                  f"  |  backend {reply.answer.backend}")


def cmd_ask(args) -> int:
    """One-shot question, for scripting and for the demo."""
    from datetime import date as _date

    from rag.chat import Session, respond

    session = Session(as_of=_date.fromisoformat(args.as_of),
                      backend_pref=args.backend)
    reply = respond(" ".join(args.question), session)
    print(wrap(reply.text, width=76, indent="  "))
    if reply.answer and reply.answer.citations:
        print("\n  sources:")
        for c in reply.answer.citations:
            print(f"    - {c.instrument}, {c.provision} "
                  f"({c.source_pdf} p.{c.page})")
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    print(f"  IP-SAKTI Sahayak chat UI -> http://{args.host}:{args.port}")
    uvicorn.run("server:app", host=args.host, port=args.port, log_level="warning")
    return 0


def cmd_eval(args) -> int:
    from tests.eval_retrieval import evaluate

    print("SAMHITA retrieval gold set\n")
    out = evaluate()
    return 0 if out["recall@5"] >= 0.8 else 1


def cmd_reproduce(args) -> int:
    """A compiler must be reproducible. Same input + same law version ->
    byte-identical output."""
    f = load_formulation(args.file)
    as_of = date.fromisoformat(args.as_of)
    digests = set()
    for _ in range(args.runs):
        r = compile_formulation(f, as_of=as_of)
        digests.add(r.cbom.digest())
    ok = len(digests) == 1
    print(f"  {args.runs} runs -> {len(digests)} distinct C-BOM digest(s)")
    print(f"  digest: {digests.pop() if ok else 'UNSTABLE'}")
    print(f"  {'PASS — reproducible build' if ok else 'FAIL — output is not deterministic'}")
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser(prog="sakti", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("compile", help="compile a formulation to a C-BOM")
    c.add_argument("file")
    c.add_argument("--as-of", default=date.today().isoformat())
    c.add_argument("--autofix", action="store_true",
                   help="apply available autofixes and prove the blockers clear")
    c.add_argument("--brief", action="store_true", help="hide citation text")
    c.add_argument("--out", help="write the C-BOM JSON here")
    c.add_argument("--html", help="write the click-to-source HTML report here")
    c.add_argument("--strict", action="store_true",
                   help="exit non-zero if any blocker remains")
    c.set_defaults(fn=cmd_compile)

    t = sub.add_parser("timetravel", help="compile under the law on several dates")
    t.add_argument("file")
    t.add_argument("dates", nargs="+")
    t.set_defaults(fn=cmd_timetravel)

    r = sub.add_parser("rules", help="list rules and their verification status")
    r.set_defaults(fn=cmd_rules)

    v = sub.add_parser("resolve", help="resolve ingredient names to taxa")
    v.add_argument("names", nargs="+")
    v.set_defaults(fn=cmd_resolve)

    ch = sub.add_parser("chat", help="interactive RAG chat over the corpus")
    ch.add_argument("--as-of", default=date.today().isoformat())
    ch.add_argument("--backend", default="auto",
                    choices=["auto", "extractive", "claude"],
                    help="extractive runs fully offline; claude needs ANTHROPIC_API_KEY")
    ch.set_defaults(fn=cmd_chat)

    ak = sub.add_parser("ask", help="one-shot question")
    ak.add_argument("question", nargs="+")
    ak.add_argument("--as-of", default=date.today().isoformat())
    ak.add_argument("--backend", default="auto",
                    choices=["auto", "extractive", "claude"])
    ak.set_defaults(fn=cmd_ask)

    sv = sub.add_parser("serve", help="run the chat web UI")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.set_defaults(fn=cmd_serve)

    ev = sub.add_parser("eval", help="run the retrieval gold set")
    ev.set_defaults(fn=cmd_eval)

    d = sub.add_parser("reproduce", help="check the build is deterministic")
    d.add_argument("file")
    d.add_argument("--runs", type=int, default=10)
    d.add_argument("--as-of", default=date.today().isoformat())
    d.set_defaults(fn=cmd_reproduce)

    args = p.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
