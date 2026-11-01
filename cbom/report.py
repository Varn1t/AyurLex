"""Render a C-BOM to a self-contained HTML report.

The interaction that matters is click-to-source: every finding opens the
provision text it rests on, with the entailing span highlighted, the source PDF
and page, and the retrieval date. A reader can check any sentence in two clicks
without leaving the page, which is the whole point -- a compliance claim nobody
can check is worth nothing.

No network calls, no external assets. The file opens from disk on an air-gapped
machine, same as the rest of the stack.
"""
from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path

from core.schema import CBOM, Finding, Severity

SEV_CLASS = {
    Severity.BLOCKER: "blocker",
    Severity.WARNING: "warning",
    Severity.OPPORTUNITY: "opportunity",
    Severity.INFO: "info",
}
LANE_LABEL = {
    "PATENT": "Patent lane",
    "REGULATORY": "Regulatory lane",
    "BRAND": "Brand / advertising lane",
    "ACCESS": "Access &amp; benefit-sharing lane",
    "OTHER": "General",
}


def esc(s: str) -> str:
    return html.escape(str(s))


def highlight(quote: str, anchor_words: set[str]) -> str:
    """Mark the span the finding actually leans on inside the full provision."""
    out = []
    for tok in re.split(r"(\W+)", quote):
        if tok.lower() in anchor_words and len(tok) > 3:
            out.append(f"<mark>{esc(tok)}</mark>")
        else:
            out.append(esc(tok))
    return "".join(out)


def render_finding(f: Finding, idx: int) -> str:
    anchor_words = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", f.statement)}
    cites = []
    for c in f.citations:
        cites.append(f"""
      <div class="cite">
        <div class="cite-head">
          <span class="pill">{esc(c.kind.value)}</span>
          <strong>{esc(c.provision)}</strong> — {esc(c.instrument)}
        </div>
        <div class="cite-meta">
          {esc(c.hierarchy_path)}<br>
          source: <code>{esc(c.source_pdf)}</code> p.{c.page}
          &middot; corpus id <code>{esc(c.corpus_id)}</code>
          {f"&middot; retrieved {esc(c.retrieved_on)}" if c.retrieved_on else ""}
          &middot; authority rank {c.authority_rank}
        </div>
        <blockquote>{highlight(c.quote, anchor_words)}</blockquote>
      </div>""")

    fixes = []
    for fx in f.autofix:
        state = ("available" if fx.available
                 else f"blocked — {esc(fx.unavailable_reason)}")
        cls = "fix" if fx.available else "fix fix-blocked"
        fixes.append(f"""
      <div class="{cls}">
        <div><strong>{esc(fx.id)}</strong> <span class="tag">{state}</span></div>
        <p>{esc(fx.description)}</p>
        {f'<p class="effect">Expected effect: {esc(fx.expected_effect)}</p>'
         if fx.expected_effect else ''}
      </div>""")

    return f"""
  <article class="finding {SEV_CLASS[f.severity]}">
    <header>
      <span class="sev">{f.severity.value}</span>
      <span class="lane">{LANE_LABEL.get(f.lane, f.lane)}</span>
      <span class="rule">{esc(f.rule_id)}</span>
    </header>
    <h3>{esc(f.instrument)} — {esc(f.provision)}</h3>
    <p class="statement">{esc(f.statement)}</p>
    <div class="scores">
      groundedness <strong>{f.groundedness:.2f}</strong>
      &middot; {esc(f.verification.value)}
      &middot; {len(f.citations)} citation(s)
    </div>
    <details open>
      <summary>Show the authority this rests on</summary>
      {''.join(cites)}
    </details>
    {f'<details><summary>Autofix ({len(f.autofix)})</summary>{"".join(fixes)}</details>'
     if fixes else ''}
  </article>"""


def render(cbom: CBOM, *, title: str | None = None) -> str:
    counts = {s: sum(1 for f in cbom.findings if f.severity is s) for s in Severity}
    findings_html = "".join(render_finding(f, i)
                            for i, f in enumerate(cbom.findings))

    res_rows = "".join(
        f"""<tr class="{'ok' if r['auto_accepted'] else 'flag'}">
          <td>{esc(r['input'])}</td>
          <td>{esc(r['resolved_to'] or ' / '.join(r['candidates']) or '—')}</td>
          <td><code>{esc(r['path'])}</code></td>
          <td>{r['confidence']:.2f}</td>
          <td>{'auto-accepted' if r['auto_accepted'] else 'needs confirmation'}</td>
        </tr>"""
        for r in cbom.resolution_log
    )

    ob_rows = "".join(
        f"""<tr><td>{esc(o.provision)}</td><td>{esc(o.duty)}</td>
            <td>{esc(o.discharged_by)}</td><td>{esc(o.when)}</td></tr>"""
        for o in cbom.obligations
    )

    matrix_rows = "".join(
        f"""<tr class="{SEV_CLASS[r.status]}">
          <td><strong>{esc(r.jurisdiction.value)}</strong></td>
          <td>{esc(r.patentability)}</td>
          <td>{esc(r.disclosure_duty)}</td>
          <td>{esc(r.abs_requirement)}</td>
          <td>{esc(r.market_route)}</td>
          <td>{r.citation_count}</td>
          <td>{esc(r.next_action)}</td>
        </tr>"""
        for r in cbom.jurisdiction_matrix
    )

    abstentions = "".join(f"<li>{esc(a)}</li>" for a in cbom.abstentions)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>C-BOM — {esc(cbom.formulation_name)}</title>
<style>
  :root {{
    --bg:#fbfaf8; --fg:#1c1a17; --muted:#6b645c; --line:#e2ddd6; --card:#fff;
    --blocker:#b3261e; --warning:#a9690a; --opportunity:#1c6b4a; --info:#3a5a8c;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#16150f; --fg:#eee9e1; --muted:#a49c91; --line:#332f28;
             --card:#1e1c16; --blocker:#f2857b; --warning:#e0aa5a;
             --opportunity:#6fc79c; --info:#8fb0e0; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.6
    ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif; }}
  .wrap {{ max-width:1000px; margin:0 auto; padding:32px 20px 80px; }}
  h1 {{ font-size:26px; margin:0 0 4px; letter-spacing:-.02em; }}
  h2 {{ font-size:15px; text-transform:uppercase; letter-spacing:.08em;
        color:var(--muted); margin:40px 0 12px; }}
  .sub {{ color:var(--muted); font-size:13px; }}
  .tiles {{ display:flex; flex-wrap:wrap; gap:10px; margin:20px 0; }}
  .tile {{ flex:1 1 130px; background:var(--card); border:1px solid var(--line);
    border-radius:10px; padding:12px 14px; }}
  .tile .n {{ font-size:26px; font-weight:650; line-height:1.1; }}
  .tile .l {{ font-size:11px; text-transform:uppercase; letter-spacing:.07em;
    color:var(--muted); }}
  .finding {{ background:var(--card); border:1px solid var(--line);
    border-left:4px solid var(--line); border-radius:10px; padding:16px 18px;
    margin:14px 0; }}
  .finding.blocker {{ border-left-color:var(--blocker); }}
  .finding.warning {{ border-left-color:var(--warning); }}
  .finding.opportunity {{ border-left-color:var(--opportunity); }}
  .finding.info {{ border-left-color:var(--info); }}
  .finding header {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center;
    font-size:11px; text-transform:uppercase; letter-spacing:.06em; }}
  .sev {{ font-weight:700; }}
  .blocker .sev {{ color:var(--blocker); }} .warning .sev {{ color:var(--warning); }}
  .opportunity .sev {{ color:var(--opportunity); }} .info .sev {{ color:var(--info); }}
  .lane, .rule {{ color:var(--muted); }}
  .rule {{ font-family:ui-monospace,Menlo,Consolas,monospace; text-transform:none; }}
  .finding h3 {{ font-size:15px; margin:8px 0 6px; }}
  .statement {{ margin:6px 0 10px; }}
  .scores {{ font-size:12px; color:var(--muted); }}
  details {{ margin-top:10px; }}
  summary {{ cursor:pointer; font-size:13px; color:var(--muted);
    padding:4px 0; user-select:none; }}
  summary:hover {{ color:var(--fg); }}
  .cite {{ border-top:1px solid var(--line); padding-top:10px; margin-top:10px; }}
  .cite-head {{ font-size:13px; }}
  .cite-meta {{ font-size:11px; color:var(--muted); margin:4px 0 6px; }}
  blockquote {{ margin:0; padding:10px 12px; background:var(--bg);
    border:1px solid var(--line); border-radius:8px; font-size:13px;
    white-space:pre-wrap; max-height:280px; overflow:auto; }}
  mark {{ background:rgba(224,170,90,.35); color:inherit; padding:0 1px;
    border-radius:2px; }}
  .pill, .tag {{ display:inline-block; font-size:10px; letter-spacing:.05em;
    text-transform:uppercase; border:1px solid var(--line); border-radius:20px;
    padding:1px 7px; color:var(--muted); }}
  .fix {{ border-top:1px dashed var(--line); padding:8px 0; }}
  .fix p {{ margin:4px 0; font-size:13px; }}
  .fix-blocked {{ opacity:.55; }}
  .effect {{ color:var(--muted); font-size:12px; }}
  .scroll {{ overflow-x:auto; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px;
    background:var(--card); border:1px solid var(--line); border-radius:10px; }}
  th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--line);
    vertical-align:top; }}
  th {{ font-size:11px; text-transform:uppercase; letter-spacing:.06em;
    color:var(--muted); }}
  tr.flag td {{ background:rgba(224,170,90,.10); }}
  code {{ font-family:ui-monospace,Menlo,Consolas,monospace; font-size:12px; }}
  .note {{ background:var(--card); border:1px solid var(--line);
    border-radius:10px; padding:14px 16px; font-size:13px; color:var(--muted); }}
  footer {{ margin-top:44px; padding-top:16px; border-top:1px solid var(--line);
    font-size:12px; color:var(--muted); }}
</style></head><body><div class="wrap">

<h1>Compliance Bill of Materials</h1>
<p class="sub">
  <strong>{esc(cbom.formulation_name)}</strong> &middot;
  compiled as-of {cbom.as_of} &middot;
  fingerprint <code>{esc(cbom.formulation_fingerprint)}</code> &middot;
  digest <code>{esc(cbom.digest()[:20])}</code>
</p>

<div class="tiles">
  <div class="tile"><div class="n" style="color:var(--blocker)">{counts[Severity.BLOCKER]}</div><div class="l">Blockers</div></div>
  <div class="tile"><div class="n" style="color:var(--warning)">{counts[Severity.WARNING]}</div><div class="l">Warnings</div></div>
  <div class="tile"><div class="n" style="color:var(--opportunity)">{counts[Severity.OPPORTUNITY]}</div><div class="l">Opportunities</div></div>
  <div class="tile"><div class="n">{len(cbom.obligations)}</div><div class="l">Obligations</div></div>
  <div class="tile"><div class="n">{cbom.groundedness_score:.2f}</div><div class="l">Groundedness</div></div>
</div>

<h2>Resolver — what the ingredient names were taken to mean</h2>
<div class="scroll"><table>
  <tr><th>As entered</th><th>Canonical taxon</th><th>Path</th><th>Conf.</th><th>Status</th></tr>
  {res_rows}
</table></div>

<h2>Findings</h2>
{findings_html}

<h2>Obligations triggered</h2>
<div class="scroll"><table>
  <tr><th>Provision</th><th>Duty</th><th>Discharged by</th><th>When</th></tr>
  {ob_rows}
</table></div>

<h2>Jurisdiction matrix</h2>
<div class="scroll"><table>
  <tr><th>Juris.</th><th>Patentability</th><th>Disclosure duty</th>
      <th>Access / ABS</th><th>Market route</th><th>Cites</th><th>Next action</th></tr>
  {matrix_rows}
</table></div>

{f'<h2>Abstentions</h2><div class="note"><ul>{abstentions}</ul></div>'
 if abstentions else ''}

<footer>
  {esc(cbom.disclaimer)}<br><br>
  Law version: <code>{esc(cbom.law_version)}</code>.
  Every citation above was re-verified verbatim against the source PDF at
  compile time. Generated by {esc(cbom.generated_by)}.
</footer>
</div></body></html>"""


def write_report(cbom: CBOM, path: Path, *, title: str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(cbom, title=title), encoding="utf-8")
    return path
