import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from run import (  # noqa: E402
    Golden,
    QueryResult,
    aggregate,
    load_golden,
    mrr,
    ndcg_at_k,
    recall_at_k,
    score,
)


def test_recall_mrr_ndcg():
    ranked = ["b", "a", "c"]
    assert recall_at_k(ranked, ["a"], 1) == 0.0
    assert recall_at_k(ranked, ["a"], 2) == 1.0
    assert recall_at_k(ranked, ["a", "z"], 5) == 0.5
    assert mrr(ranked, ["a"]) == 0.5
    assert mrr(ranked, ["zz"]) == 0.0
    assert ndcg_at_k(["a"], ["a"], 5) == 1.0
    assert 0 < ndcg_at_k(ranked, ["a"], 5) < 1.0
    assert ndcg_at_k([], ["a"], 5) == 0.0


def test_score_and_aggregate():
    g = Golden("q1", "c", "x", ["a"])
    r1 = QueryResult(g, ["a"], 10.0)
    r1.metrics = score(["a"], ["a"])
    r2 = QueryResult(g, ["b"], 30.0)
    r2.metrics = score(["b"], ["a"])
    agg = aggregate([r1, r2])
    assert agg["recall@1"] == 0.5 and agg["mrr"] == 0.5 and agg["n"] == 2
    assert agg["latency_p50_ms"] == 20.0 and agg["errors"] == 0


def test_golden_file_is_well_formed():
    golden = load_golden(Path(__file__).with_name("golden_queries.jsonl"))
    ids = [g.id for g in golden]
    assert len(ids) == len(set(ids)), "duplicate ids"
    assert len(golden) >= 30
    classes = {g.cls for g in golden}
    assert {"entity_lookup", "person", "ost", "semantic_memory", "temporal"} <= classes
    for g in golden:
        assert g.query.strip() and g.expected, g.id
        json.dumps(g.expected)  # serializable
