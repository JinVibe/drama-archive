from ai_api.retrieval.fusion import Candidate, rrf


def _list(*ids: int) -> list[Candidate]:
    return [Candidate(doc_id=d, rank=i + 1, score=1.0 / (i + 1)) for i, d in enumerate(ids)]


def test_rrf_weights_scale_a_list():
    lists = {"fts": _list(1), "vector": _list(2)}
    assert [f.doc_id for f in rrf(lists, k=60)] == [1, 2]            # tie -> lower id
    assert [f.doc_id for f in rrf(lists, k=60, weights={"vector": 2.0})] == [2, 1]
    assert [f.doc_id for f in rrf(lists, k=60, weights={"vector": 0.0})] == [1, 2]
    assert rrf(lists, k=60, weights={"vector": 0.0})[1].score == 0.0


def test_rrf_rewards_agreement_across_lists():
    fused = rrf({"fts": _list(1, 2, 3), "vector": _list(3, 1, 9)}, k=60)
    ids = [f.doc_id for f in fused]
    # 1 and 3 appear in both lists and beat 2 and 9 which appear once.
    assert ids[:2] == [1, 3]
    assert set(ids[2:]) == {2, 9}
    assert fused[0].ranks == {"fts": 1, "vector": 2}
    assert fused[0].scores["fts"] == 1.0


def test_rrf_scores_are_rank_based_not_raw_scores():
    # A huge raw score must not dominate: only ranks matter.
    huge = [Candidate(doc_id=5, rank=1, score=1_000_000.0)]
    fused = rrf({"a": huge, "b": _list(7, 5)}, k=60)
    assert [f.doc_id for f in fused] == [5, 7]
    assert abs(fused[0].score - (1 / 61 + 1 / 62)) < 1e-12


def test_rrf_limit_and_deterministic_ties():
    fused = rrf({"a": _list(4), "b": _list(2)}, k=60, limit=1)
    assert [f.doc_id for f in fused] == [2]  # equal score -> lower id first


def test_rrf_empty():
    assert rrf({}) == []
    assert rrf({"a": []}) == []
