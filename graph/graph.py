"""Knowledge graph -- the relational knowledge graph over the corpus.

A relational knowledge graph is here to deepen
multi-step reasoning, and the reason it is needed is specific
rather than fashionable: the questions an AYUSH founder actually asks are
multi-hop, and retrieval is single-hop by construction.

  "India is a Party to the Nagoya Protocol -- so what do *I* have to do?"

No single provision answers that. The answer is a path: Nagoya Article 5 is
given effect in India by Biological Diversity Act Section 21, Section 21 is
imposed by the rule that fires on your facts, and that rule is cleared by
obtaining NBA approval. A retriever scores each of those four nodes
independently and returns whichever scores best; a graph walks the path.

WHAT IS AND IS NOT ASSERTED HERE
--------------------------------
Almost every edge is *derived*, not authored, and therefore cannot be wrong:

  PART_OF          a provision belongs to the instrument it was extracted from
  IN_JURISDICTION  an instrument belongs to the regime it was registered under
  CITES            a compliance rule cites what its own YAML declares (already
                   anchor-verified at rule load)
  GOVERNED_BY      a concept points at the provisions listed against it
  DEFINED_BY       a formulation category points at the provisions that define it
  TRIGGERED_BY     a rule reads the facts named in its `when` block
  CLEARED_BY       an autofix clears the rule that offers it
  IMPOSES          a rule's obligation names its own provision
  CROSS_REFERS     one provision names another BY NUMBER in its own text
  RESTRICTED_UNDER a taxon carrying a schedule flag reaches the provision that
                   flag belongs to
  PRIOR_ART_FROM   a TKDL adverse outcome belongs to the TKDL record set

The only authored edges are the cross-instrument ones in
`data/graph_links.yaml` -- treaty obligation to the domestic provision giving
it effect -- and those are held to the rule-loader gate: both endpoints must resolve
in the corpus and every declared anchor must be verbatim in its endpoint. A
link that fails is dropped and reported, never silently kept.

The graph therefore adds NO new way to be wrong. It rearranges facts the
system already had to prove.

AND WHAT IT STILL MAY NOT DO
----------------------------
A path is not an argument. `explain()` renders a path as prose built from the
edge notes and the provision headings -- fixed connective text plus material
already verified -- and every hop carries its citation so the reader can open
it. The graph never merges two jurisdictions into one answer: a path that
crosses the India/international boundary is rendered with the boundary shown,
because "India is a Party to Nagoya" and "you can sue on Nagoya in Delhi" are
very different statements.
"""
from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from sources.index import Corpus, load_corpus

ROOT = Path(__file__).resolve().parent.parent
LINKS = ROOT / "data" / "graph_links.yaml"
TAXA = ROOT / "data" / "taxa.jsonl"
TKDL = ROOT / "corpus" / "tkdl_outcomes.jsonl"

# Node kinds, in the order a reader should meet them.
KINDS = ("provision", "instrument", "jurisdiction", "concept", "rule",
         "category", "fact", "fix", "taxon", "outcome", "facilitator")

# Container nodes. An instrument holds every one of its provisions, so allowing
# a walk to pass THROUGH one would make any two sections of the Patents Act two
# hops apart via "is a provision of / contains" -- a path that is true, useless,
# and crowds out the real one. Containers can be the start or the end of a walk;
# they are never a step in the middle of it. Membership is not a relationship.
TRANSIT_BLOCKED = {"instrument", "jurisdiction"}

# Edges whose direction carries meaning when read aloud. Everything else reads
# the same either way and the traversal treats the graph as undirected.
EDGE_PROSE = {
    "PART_OF": "is a provision of",
    "IN_JURISDICTION": "belongs to the regime",
    "CITES": "cites",
    "GOVERNED_BY": "is governed by",
    "DECIDED_BY": "is decided by the rule",
    "DEFINED_BY": "is defined by",
    "TRIGGERED_BY": "is triggered by the fact",
    "CLEARED_BY": "is cleared by",
    "IMPOSES": "imposes the duty in",
    "CROSS_REFERS": "refers in its own text to",
    "IMPLEMENTED_BY": "is given domestic effect in India by",
    # A provision and the later section that rewrote it. Distinct from CITES,
    # which is derived from a section number appearing in the text: an
    # amending section names its target, but so does an ordinary
    # cross-reference, and only one of the two means "this is no longer what
    # the section says".
    "AMENDED_BY": "is amended by",
    "INFORMS": "informs",
    "CORRESPONDS_TO": "corresponds to",
    "RESTRICTED_UNDER": "is restricted under",
    "PRIOR_ART_FROM": "is a recorded outcome in",
    "ACTS_UNDER": "acts under",
}


# Which kind of node a bare phrase should prefer to mean. A question that
# names an instrument means the instrument, not its first article.
_KIND_RANK = {"instrument": 0, "concept": 1, "category": 2, "rule": 3,
              "taxon": 4, "fix": 5, "provision": 6, "outcome": 7,
              "jurisdiction": 8, "fact": 9}


def _norm(s: str) -> str:
    """Whitespace-insensitive comparison, exactly as the rule loader does it:
    PDF extraction breaks lines mid-sentence, so an anchor matches on words."""
    return re.sub(r"\s+", " ", s).strip().lower()


@dataclass(frozen=True)
class Node:
    id: str
    kind: str
    label: str
    meta: tuple = ()          # frozen key/value pairs, so a Node stays hashable

    @property
    def data(self) -> dict:
        return dict(self.meta)


@dataclass
class Edge:
    src: str
    dst: str
    kind: str
    note: str = ""
    evidence: str = ""

    def prose(self) -> str:
        return EDGE_PROSE.get(self.kind, self.kind.lower().replace("_", " "))


@dataclass
class Hop:
    """One step of a walk: the edge taken and the node arrived at."""

    edge: Edge
    node: Node
    forward: bool = True


@dataclass
class Walk:
    """A walk through the graph: where it started and every hop taken.

    Named Walk rather than Path because `pathlib.Path` is imported above and
    a second `Path` in this module would shadow it for everything below the
    class -- which works today only by accident of ordering.
    """

    start: Node
    hops: list[Hop] = field(default_factory=list)

    @property
    def nodes(self) -> list[Node]:
        return [self.start] + [h.node for h in self.hops]

    @property
    def length(self) -> int:
        return len(self.hops)

    def crosses_jurisdiction(self) -> bool:
        seen = {n.data.get("jurisdiction") for n in self.nodes
                if n.kind == "provision"}
        seen.discard(None)
        return len({"IN" if j == "IN" else "INTL" for j in seen}) > 1


class Graph:
    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self._adj: dict[str, list[tuple[int, bool]]] = defaultdict(list)
        self.problems: list[str] = []

    # ------------------------------------------------------------ build --
    def add_node(self, node: Node) -> Node:
        return self.nodes.setdefault(node.id, node)

    def add_edge(self, src: str, dst: str, kind: str, *, note: str = "",
                 evidence: str = "") -> None:
        if src not in self.nodes or dst not in self.nodes or src == dst:
            return
        i = len(self.edges)
        self.edges.append(Edge(src, dst, kind, note, evidence))
        self._adj[src].append((i, True))
        self._adj[dst].append((i, False))

    # ----------------------------------------------------------- lookup --
    def get(self, nid: str) -> Node:
        if nid not in self.nodes:
            raise KeyError(f"{nid!r} is not a node in the graph")
        return self.nodes[nid]

    def has(self, nid: str) -> bool:
        return nid in self.nodes

    def resolve(self, text: str) -> list[Node]:
        """Best-effort lookup by id, by corpus id, or by label.

        Deliberately not fuzzy. A graph query that matched loosely would walk
        from the wrong node and produce a confident wrong path, which is the
        failure mode this whole system is built to avoid.
        """
        t = text.strip()
        for cand in (t, f"prov:{t}", f"inst:{t}", f"rule:{t}",
                     f"concept:{t}", f"category:{t}", f"taxon:{t}",
                     f"fact:{t}", f"fix:{t}", f"juris:{t}"):
            if cand in self.nodes:
                return [self.nodes[cand]]
        low = _norm(t)
        exact = [n for n in self.nodes.values() if _norm(n.label) == low]
        if exact:
            return exact
        # Substring matches, ranked. "Nagoya Protocol" is a substring of the
        # instrument's title AND of every one of its 36 article labels, so
        # unranked iteration order returns Article 1 -- and a walk from
        # Article 1 finds nothing, because the relationship the user asked
        # about hangs off Article 5. The instrument is the right answer to a
        # question that named the instrument; shorter label breaks ties,
        # because a shorter label containing the phrase is a closer match.
        hits = [n for n in self.nodes.values() if low in _norm(n.label)]
        hits.sort(key=lambda n: (_KIND_RANK.get(n.kind, 9), len(n.label), n.id))
        return hits[:8]

    def neighbours(self, nid: str, *, kinds: set[str] | None = None,
                   node_kinds: set[str] | None = None) -> list[Hop]:
        out: list[Hop] = []
        for i, forward in self._adj.get(nid, ()):
            e = self.edges[i]
            if kinds and e.kind not in kinds:
                continue
            other = self.nodes[e.dst if forward else e.src]
            if node_kinds and other.kind not in node_kinds:
                continue
            out.append(Hop(edge=e, node=other, forward=forward))
        out.sort(key=lambda h: (h.edge.kind, h.node.id))
        return out

    def degree(self, nid: str) -> int:
        return len(self._adj.get(nid, ()))

    # -------------------------------------------------------- traversal --
    def path(self, src: str, dst: str, *, max_hops: int = 6) -> Walk | None:
        """Shortest path, breadth-first.

        Breadth-first rather than weighted: every edge here is an assertion the
        system can already prove, so there is no notion of a 'cheaper' hop, and
        the shortest chain of provable assertions is the one a reader can check
        fastest.
        """
        if src == dst or src not in self.nodes or dst not in self.nodes:
            return Walk(start=self.nodes[src]) if src == dst else None
        prev: dict[str, tuple[str, Edge, bool]] = {}
        seen = {src}
        q: deque[tuple[str, int]] = deque([(src, 0)])
        while q:
            cur, d = q.popleft()
            if d >= max_hops:
                continue
            if cur != src and self.nodes[cur].kind in TRANSIT_BLOCKED:
                continue        # reachable, but not walked through
            for i, forward in self._adj.get(cur, ()):
                e = self.edges[i]
                nxt = e.dst if forward else e.src
                if nxt in seen:
                    continue
                seen.add(nxt)
                prev[nxt] = (cur, e, forward)
                if nxt == dst:
                    return self._rebuild(src, dst, prev)
                q.append((nxt, d + 1))
        return None

    def _rebuild(self, src: str, dst: str,
                 prev: dict[str, tuple[str, Edge, bool]]) -> Walk:
        hops: list[Hop] = []
        cur = dst
        while cur != src:
            back, e, forward = prev[cur]
            hops.append(Hop(edge=e, node=self.nodes[cur], forward=forward))
            cur = back
        hops.reverse()
        return Walk(start=self.nodes[src], hops=hops)

    def subgraph(self, nid: str, *, hops: int = 1) -> tuple[list[Node], list[Edge]]:
        seen = {nid}
        frontier = [nid]
        edges: list[Edge] = []
        for _ in range(hops):
            nxt = []
            for cur in frontier:
                for h in self.neighbours(cur):
                    if h.edge not in edges:
                        edges.append(h.edge)
                    if h.node.id not in seen:
                        seen.add(h.node.id)
                        nxt.append(h.node.id)
            frontier = nxt
        return [self.nodes[i] for i in seen], edges

    # ---------------------------------------------------------- explain --
    def explain(self, path: Walk) -> list[str]:
        """Render a walk as prose.

        Every line is fixed connective text plus material already verified --
        an edge note from the curated file, a provision heading from the
        corpus. Nothing here is generated, so nothing here can be hallucinated.
        """
        if not path.hops:
            return [f"{path.start.label} — no walk needed; that is the node itself."]
        lines = [f"{path.start.label}"]
        for h in path.hops:
            verb = h.edge.prose() if h.forward else _invert(h.edge)
            lines.append(f"  → {verb} {h.node.label}")
            if h.edge.note:
                lines.append(f"      {h.edge.note.strip()}")
            cite = _citation_line(h.node)
            if cite:
                lines.append(f"      {cite}")
        if path.crosses_jurisdiction():
            lines.append(
                "  ! This walk crosses the India / international boundary. "
                "The layers are separate authorities: the treaty binds India "
                "as a State, the Indian provision is what binds you.")
        return lines

    def stats(self) -> dict:
        by_node = defaultdict(int)
        for n in self.nodes.values():
            by_node[n.kind] += 1
        by_edge = defaultdict(int)
        for e in self.edges:
            by_edge[e.kind] += 1
        return {"nodes": len(self.nodes), "edges": len(self.edges),
                "by_node_kind": dict(sorted(by_node.items())),
                "by_edge_kind": dict(sorted(by_edge.items())),
                "problems": list(self.problems)}


def _invert(edge: Edge) -> str:
    """Read an edge backwards without lying about its direction."""
    return {
        "PART_OF": "contains",
        "IN_JURISDICTION": "is the regime of",
        "CITES": "is cited by",
        "GOVERNED_BY": "governs",
        "DECIDED_BY": "decides",
        "DEFINED_BY": "defines",
        "TRIGGERED_BY": "triggers",
        "CLEARED_BY": "clears",
        "IMPOSES": "is the duty imposed by",
        "CROSS_REFERS": "is referred to by",
        "IMPLEMENTED_BY": "gives domestic effect in India to",
        "AMENDED_BY": "amends",
        "INFORMS": "is informed by",
        "CORRESPONDS_TO": "corresponds to",
        "RESTRICTED_UNDER": "restricts",
        "PRIOR_ART_FROM": "records",
        "ACTS_UNDER": "is the authority for",
    }.get(edge.kind, f"is linked ({edge.kind.lower()}) to")


def _citation_line(node: Node) -> str:
    d = node.data
    if node.kind != "provision":
        return ""
    bits = [d.get("instrument", ""), d.get("provision", "")]
    tail = f"{d.get('pdf','')} p.{d.get('page','')}" if d.get("pdf") else ""
    return " — ".join([b for b in bits if b]) + (f"  [{tail}]" if tail else "")


# ================================================================= build ==
_SECTION_REF = re.compile(
    r"\b(?:section|sections|sub-section)\s+(\d+[A-Z]{0,2})\b", re.I)
_RULE_REF = re.compile(r"\brule\s+(\d+[A-Z]{0,3})\b", re.I)
_ARTICLE_REF = re.compile(r"\barticle\s+(\d+[a-z]{0,2})\b", re.I)

_LOCATOR = {"Section": ("S", _SECTION_REF),
            "Rule": ("R", _RULE_REF),
            "Article": ("A", _ARTICLE_REF)}


def _prov_node(rec: dict) -> Node:
    # Prose sources are located by page, not by section -- the rule lives in
    # rag.answer and is imported rather than restated here.
    from rag.answer import _provision_label

    label = f"{rec['act_title']} — {_provision_label(rec)}"
    return Node(
        id=f"prov:{rec['corpus_id']}",
        kind="provision",
        label=label,
        meta=(("corpus_id", rec["corpus_id"]),
              ("instrument", rec["act_title"]),
              ("provision", _provision_label(rec)),
              ("heading", rec.get("heading", "")),
              ("jurisdiction", rec.get("jurisdiction", "IN")),
              ("rank", rec.get("authority_rank", 9)),
              ("pdf", rec.get("source_pdf", "")),
              ("page", rec.get("page_start", 0)),
              ("citable", rec.get("citable", True)),
              ("force_note", rec.get("force_note", "") or "")),
    )


def _add_corpus(g: Graph, corpus: Corpus) -> None:
    by_instrument: dict[str, dict] = {}
    locators: dict[str, dict[str, str]] = defaultdict(dict)

    for rec in corpus.records:
        # Sub-chunks (#part2) are display artefacts of a long provision, not
        # separate provisions. They would double every edge, so they are not
        # nodes; the parent carries the relationships.
        if "#" in rec["corpus_id"]:
            continue
        g.add_node(_prov_node(rec))
        by_instrument.setdefault(rec["act_id"], rec)
        locators[rec["act_id"]][str(rec["section"]).upper()] = rec["corpus_id"]

    for act_id, rec in by_instrument.items():
        g.add_node(Node(id=f"inst:{act_id}", kind="instrument",
                        label=rec["act_title"],
                        meta=(("jurisdiction", rec.get("jurisdiction", "IN")),
                              ("rank", rec.get("authority_rank", 9)),
                              ("unit", rec.get("unit", "Section")),
                              ("pdf", rec.get("source_pdf", "")),
                              ("force_note", rec.get("force_note", "") or ""))))
        j = rec.get("jurisdiction", "IN")
        g.add_node(Node(id=f"juris:{j}", kind="jurisdiction", label=j))
        g.add_edge(f"inst:{act_id}", f"juris:{j}", "IN_JURISDICTION")

    for rec in corpus.records:
        if "#" in rec["corpus_id"]:
            continue
        g.add_edge(f"prov:{rec['corpus_id']}", f"inst:{rec['act_id']}", "PART_OF")

    # Internal cross-references, read out of the provision's own text. Only
    # same-instrument targets are linked: "section 3" inside the Patents Act
    # means the Patents Act's section 3, but the same words inside a treaty
    # mean nothing resolvable, and guessing across instruments would invent a
    # relationship the text does not assert.
    for rec in corpus.records:
        if "#" in rec["corpus_id"]:
            continue
        prefix, pattern = _LOCATOR.get(rec.get("unit") or "Section",
                                       ("S", _SECTION_REF))
        own = str(rec["section"]).upper()
        table = locators[rec["act_id"]]
        for m in pattern.finditer(rec["text"]):
            target = m.group(1).upper()
            if target == own:
                continue
            tid = table.get(target)
            if tid:
                g.add_edge(f"prov:{rec['corpus_id']}", f"prov:{tid}",
                           "CROSS_REFERS")


def _add_rules(g: Graph, corpus: Corpus) -> None:
    from compliance.loader import load_rules

    for rule in load_rules(corpus=corpus):
        rid = f"rule:{rule.id}"
        g.add_node(Node(id=rid, kind="rule", label=rule.id,
                        meta=(("severity", rule.severity.value),
                              ("lane", rule.lane),
                              ("instrument", rule.instrument),
                              ("provision", rule.provision),
                              ("verification", rule.verification.value))))
        for c in rule.citations:
            if g.has(f"prov:{c.corpus_id}"):
                g.add_edge(rid, f"prov:{c.corpus_id}", "CITES",
                           evidence=c.quote[:200] if c.verified else "")
        for key in _facts_in(rule.when):
            g.add_node(Node(id=f"fact:{key}", kind="fact", label=key))
            g.add_edge(rid, f"fact:{key}", "TRIGGERED_BY")
        for fx in rule.autofix:
            g.add_node(Node(id=f"fix:{fx.id}", kind="fix", label=fx.id,
                            meta=(("description", fx.description.strip()),)))
            g.add_edge(rid, f"fix:{fx.id}", "CLEARED_BY",
                       note=fx.expected_effect)
        if rule.obligation:
            for c in rule.citations:
                if g.has(f"prov:{c.corpus_id}"):
                    g.add_edge(rid, f"prov:{c.corpus_id}", "IMPOSES",
                               note=str(rule.obligation.get("duty", "")).strip())
                    break


def _facts_in(cond) -> list[str]:
    if not isinstance(cond, dict):
        return []
    if "fact" in cond:
        return [cond["fact"]]
    out: list[str] = []
    for key in ("all", "any"):
        for sub in cond.get(key, []) or []:
            out += _facts_in(sub)
    if "not" in cond:
        out += _facts_in(cond["not"])
    return out


def _add_concepts(g: Graph, corpus: Corpus) -> None:
    from rag.concepts import load_concepts

    for c in load_concepts().concepts:
        if not c.ok:
            g.problems.append(f"concept {c.id}: {'; '.join(c.problems)}")
            continue
        cid = f"concept:{c.id}"
        g.add_node(Node(id=cid, kind="concept", label=c.label,
                        meta=(("id", c.id),)))
        for pid in c.provisions:
            g.add_edge(cid, f"prov:{pid}", "GOVERNED_BY")
        for rid in c.rules:
            if g.has(f"rule:{rid}"):
                g.add_edge(cid, f"rule:{rid}", "DECIDED_BY")


def _add_categories(g: Graph, corpus: Corpus) -> None:
    from classification.classify import load_classes

    for cat in load_classes().classes:
        if cat.problems:
            g.problems.append(f"category {cat.id}: {'; '.join(cat.problems)}")
        cid = f"category:{cat.id}"
        g.add_node(Node(id=cid, kind="category", label=cat.label,
                        meta=(("id", cat.id), ("ip", cat.ip.strip()),
                              ("abs", cat.abs.strip()),
                              ("requires", cat.requires.strip()))))
        for pid in cat.provisions:
            g.add_edge(cid, f"prov:{pid}", "DEFINED_BY")


def _add_taxa(g: Graph, corpus: Corpus) -> None:
    import json

    # A schedule flag is the only edge a taxon record legitimately carries into
    # the statute book: it says this species is named in a restricted list, and
    # the list lives in a provision. Anything else about a plant is botany, not
    # law, and does not belong in this graph.
    flag_targets = {
        "BDA_SCHEDULE_RESTRICTED": "IN.BDA.2002::S6",
        "NORMALLY_TRADED_COMMODITY": "IN.BDA.2002::S40",
    }
    if not TAXA.exists():
        return
    for line in TAXA.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        tid = f"taxon:{rec['taxon']}"
        g.add_node(Node(id=tid, kind="taxon", label=rec["taxon"],
                        meta=(("family", rec.get("family", "")),
                              ("indian_bioresource",
                               rec.get("indian_bioresource", False)))))
        for flag in rec.get("schedule_flags", []) or []:
            target = flag_targets.get(flag)
            if target and g.has(f"prov:{target}"):
                g.add_edge(tid, f"prov:{target}", "RESTRICTED_UNDER", note=flag)


def _add_outcomes(g: Graph, corpus: Corpus) -> None:
    import json

    if not TKDL.exists():
        return
    for line in TKDL.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        oid = f"outcome:{rec['application_no']}"
        g.add_node(Node(id=oid, kind="outcome",
                        label=f"Application {rec['application_no']}",
                        meta=(("title", rec.get("title", "")[:180]),
                              ("outcome", rec.get("outcome", "")),
                              ("page", rec.get("page", 0)))))
        if g.has("inst:REF.TKDL"):
            g.add_edge(oid, "inst:REF.TKDL", "PRIOR_ART_FROM")


def _add_links(g: Graph, corpus: Corpus) -> None:
    """The authored edges, held to the rule-loader gate."""
    if not LINKS.exists():
        return
    raw = yaml.safe_load(LINKS.read_text(encoding="utf-8")) or []
    for spec in raw:
        lid, src, dst = spec["id"], spec["from"], spec["to"]
        problems = []
        for side, pid in (("from", src), ("to", dst)):
            if not corpus.has(pid):
                problems.append(f"{side} {pid} is not in the corpus")
        for side, pid in (("from_anchor", src), ("to_anchor", dst)):
            anchor = spec.get(side)
            if not anchor:
                continue
            if corpus.has(pid) and _norm(anchor) not in _norm(corpus.get(pid)["text"]):
                problems.append(f"{side} is not verbatim in {pid}")
        if problems:
            g.problems.append(f"link {lid}: {'; '.join(problems)}")
            continue
        kind = spec.get("relation", "informs").upper()
        g.add_edge(f"prov:{src}", f"prov:{dst}", kind,
                   note=str(spec.get("note", "")).strip(),
                   evidence=str(spec.get("from_anchor", "")).strip())


def build_graph(corpus: Corpus | None = None) -> Graph:
    corpus = corpus or load_corpus()
    g = Graph()
    _add_corpus(g, corpus)
    _add_rules(g, corpus)
    _add_concepts(g, corpus)
    _add_categories(g, corpus)
    _add_taxa(g, corpus)
    _add_outcomes(g, corpus)
    _add_links(g, corpus)
    return g


@lru_cache(maxsize=1)
def load_graph() -> Graph:
    return build_graph()
