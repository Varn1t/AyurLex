"""SAMBANDHA — the knowledge graph must not become a diagram.

The graph's whole claim is that it adds no new way to be wrong: derived edges
restate facts already proved elsewhere, and the handful of authored edges are
held to the SUTRA gate. These tests pin that claim.
"""
from __future__ import annotations

import pytest

from sambandha.graph import TRANSIT_BLOCKED, load_graph


@pytest.fixture(scope="module")
def g():
    return load_graph()


def test_every_curated_link_verifies(g):
    """A cross-instrument link whose endpoint or anchor has drifted from the
    primary source is a defect, not a warning."""
    assert g.problems == [], g.problems


def test_curated_links_are_actually_present(g):
    """The gate dropping every link would also produce zero problems."""
    authored = {"IMPLEMENTED_BY", "INFORMS", "CORRESPONDS_TO"}
    count = sum(1 for e in g.edges if e.kind in authored)
    assert count >= 8, f"only {count} authored links survived the gate"


def test_every_edge_endpoint_is_a_real_node(g):
    for e in g.edges:
        assert e.src in g.nodes, e
        assert e.dst in g.nodes, e


def test_rule_citations_match_the_rule_loader(g):
    """CITES is derived from the rules, so it must agree with them exactly."""
    from sutra.loader import load_rules

    for rule in load_rules():
        rid = f"rule:{rule.id}"
        assert g.has(rid)
        cited = {h.node.data["corpus_id"]
                 for h in g.neighbours(rid, kinds={"CITES"})}
        declared = {c.corpus_id for c in rule.citations
                    if g.has(f"prov:{c.corpus_id}")}
        assert cited == declared, rule.id


def test_containers_are_never_walked_through(g):
    """Membership is not a relationship.

    Without this, any two sections of the Patents Act are two hops apart via
    "is a provision of / contains" -- a true, useless path that crowds out the
    real one.
    """
    walk = g.path("prov:IN.PATENTS.1970::S3", "prov:IN.PATENTS.1970::S39")
    if walk is not None:
        middles = walk.nodes[1:-1]
        assert not any(n.kind in TRANSIT_BLOCKED for n in middles), \
            [n.id for n in middles]


def test_treaty_reaches_its_domestic_provision(g):
    """The path the product actually demonstrates: a Nagoya obligation reaching
    the Indian fix that discharges it."""
    walk = g.path("prov:CBD.NAGOYA.2010::A5", "fix:OBTAIN_NBA_APPROVAL")
    assert walk is not None
    ids = [n.id for n in walk.nodes]
    assert "prov:IN.BDA.2002::S6" in ids or "prov:IN.BDA.2002::S21" in ids


def test_cross_layer_walk_is_flagged(g):
    """A walk that crosses India/international must say so. Treating the two
    as one authority is the failure the whole system exists to prevent."""
    walk = g.path("prov:WTO.TRIPS.1994::A27", "prov:IN.PATENTS.1970::S3")
    assert walk is not None
    assert walk.crosses_jurisdiction()
    assert any("crosses the India / international boundary" in line
               for line in g.explain(walk))


def test_no_path_is_reported_not_invented(g):
    """Two unrelated things must produce a stated absence."""
    walk = g.path("taxon:Withania somnifera", "juris:WTO", max_hops=2)
    assert walk is None


def test_resolve_prefers_the_instrument_over_its_first_article(g):
    """'Nagoya Protocol' is a substring of the instrument title AND of all 36
    article labels. A question naming the instrument means the instrument."""
    hits = g.resolve("Nagoya Protocol")
    assert hits
    assert hits[0].kind == "instrument"


def test_resolve_does_not_guess(g):
    assert g.resolve("Widget Protection Act 2099") == []


def test_explain_only_emits_verified_material(g):
    """Every line of a walk is fixed connective text over an edge note or a
    provision heading. Nothing here is generated."""
    walk = g.path("prov:WIPO.GRATK.2024::A3", "prov:IN.PATENTS.1970::S10")
    assert walk is not None
    lines = g.explain(walk)
    assert any("Section 10" in line for line in lines)
    notes = {e.note for e in g.edges if e.note}
    body = "\n".join(lines)
    assert any(n.strip()[:40] in body for n in notes)


def test_cross_reference_edges_stay_inside_their_instrument(g):
    """'section 3' inside the Patents Act means the Patents Act's section 3.
    Reading it as some other Act's section 3 would invent a relationship."""
    for e in g.edges:
        if e.kind != "CROSS_REFERS":
            continue
        a = g.nodes[e.src].data.get("corpus_id", "")
        b = g.nodes[e.dst].data.get("corpus_id", "")
        assert a.split("::")[0] == b.split("::")[0], e


def test_subchunks_are_not_nodes(g):
    """A #part2 chunk is a display artefact of a long provision, not a separate
    provision. Admitting it would double every edge."""
    assert not any("#" in n.data.get("corpus_id", "") for n in g.nodes.values())


def test_graph_is_deterministic():
    """Same corpus, same graph. A graph that reshuffles between runs cannot be
    the basis of a reproducible answer."""
    from sambandha.graph import build_graph

    a, b = build_graph(), build_graph()
    assert [(e.src, e.dst, e.kind) for e in a.edges] == \
           [(e.src, e.dst, e.kind) for e in b.edges]


# --------------------------------------------------------------- routing ----
def test_a_procedure_question_is_not_routed_to_the_graph():
    """"how do I apply to the NBA?" matches the relationship pattern on
    "apply to" and is not a relationship question.

    Routing it to a walk produced a dead end -- "I could not pick two out of
    that sentence" -- for a question the retriever answers well from Rule 13 of
    the Biological Diversity Rules, 2024. GRAPH_HINT is a pattern over the
    wording; only the graph can settle whether the wording meant a walk.
    """
    from rag.chat import GRAPH_HINT, is_graph_question

    q = "how do I apply to the NBA for approval under the 2024 rules?"
    assert GRAPH_HINT.search(q), "the pattern is expected to match; that is the point"
    assert not is_graph_question(q)


def test_a_real_relationship_question_still_walks():
    from rag.chat import is_graph_question

    assert is_graph_question(
        "how does the Nagoya Protocol connect to the Biological Diversity Act")


def test_the_orchestrator_does_not_plan_an_unwalkable_graph_step():
    """The same false positive cost a planned step that could only fail, and
    it printed above the answer the user actually asked for."""
    from yukti.orchestrate import plan

    steps = plan("how do I apply to the NBA for approval under the 2024 rules?")
    assert not [s for s in steps if s.tool == "graph"]


def test_the_two_routing_paths_agree():
    """The streaming path decides the route before `respond` runs, so a second
    copy of the rule would drift and drop the citations of an answer that fell
    through to retrieval on only one of them."""
    import inspect

    import rag.stream

    src = inspect.getsource(rag.stream.events)
    assert "is_graph_question" in src
    assert "GRAPH_HINT" not in src
