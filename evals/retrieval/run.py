#!/usr/bin/env python3
"""Retrieval evaluation runner (DM-902) — docs/EVALUATION.md.

Runs every golden query against one or more retrieval endpoints and reports
Recall@K, MRR and NDCG@K overall and per query class. No LLM involved.

    python evals/retrieval/run.py --target lexical=http://localhost:8081/api/v1/search \
        --target hybrid=http://localhost:8090/v1/search?mode=hybrid \
        --target vector=http://localhost:8090/v1/search?mode=vector \
        --out evals/retrieval/reports/latest.json

Targets are any endpoint returning `hits[].metadata.slug` (domain-api and ai-api both do).
Only the standard library is used so this runs anywhere.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_K = (1, 3, 5, 10)


@dataclass
class Golden:
    id: str
    cls: str
    query: str
    expected: list[str]


@dataclass
class QueryResult:
    golden: Golden
    ranked: list[str]
    latency_ms: float
    strategy: str = ""
    error: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)


def load_golden(path: Path) -> list[Golden]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        d = json.loads(line)
        out.append(Golden(d["id"], d["class"], d["query"], list(d["expected"])))
    return out


# ---------------------------------------------------------------------------- metrics
def recall_at_k(ranked: list[str], expected: list[str], k: int) -> float:
    return len(set(ranked[:k]) & set(expected)) / len(expected)


def mrr(ranked: list[str], expected: list[str]) -> float:
    for i, slug in enumerate(ranked, 1):
        if slug in expected:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: list[str], expected: list[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 1) for i, s in enumerate(ranked[:k], 1) if s in expected)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(expected), k) + 1))
    return dcg / ideal if ideal else 0.0


def score(ranked: list[str], expected: list[str], ks=DEFAULT_K) -> dict[str, float]:
    m = {f"recall@{k}": recall_at_k(ranked, expected, k) for k in ks}
    m["mrr"] = mrr(ranked, expected)
    m.update({f"ndcg@{k}": ndcg_at_k(ranked, expected, k) for k in ks})
    return m


# ---------------------------------------------------------------------------- targets
def call(target_url: str, query: str, size: int, timeout: float) -> tuple[list[str], str, float]:
    sep = "&" if "?" in target_url else "?"
    url = f"{target_url}{sep}{urllib.parse.urlencode({'q': query, 'size': size})}"
    t = time.perf_counter()
    with urllib.request.urlopen(url, timeout=timeout) as r:
        body = json.load(r)
    ms = (time.perf_counter() - t) * 1000
    ranked = [h["metadata"]["slug"] for h in body.get("hits", []) if h.get("metadata", {}).get("slug")]
    return ranked, str(body.get("strategy", "")), ms


def evaluate(golden: list[Golden], target_url: str, size: int, timeout: float) -> list[QueryResult]:
    results = []
    for g in golden:
        try:
            ranked, strategy, ms = call(target_url, g.query, size, timeout)
            qr = QueryResult(g, ranked, ms, strategy)
            qr.metrics = score(ranked, g.expected)
        except Exception as exc:  # noqa: BLE001 - report, do not abort the run
            qr = QueryResult(g, [], 0.0, error=str(exc))
            qr.metrics = score([], g.expected)
        results.append(qr)
    return results


def aggregate(results: list[QueryResult]) -> dict[str, float]:
    if not results:
        return {}
    keys = results[0].metrics.keys()
    agg = {k: statistics.fmean(r.metrics[k] for r in results) for k in keys}
    lat = [r.latency_ms for r in results if r.error is None]
    if lat:
        agg["latency_p50_ms"] = statistics.median(lat)
        agg["latency_p95_ms"] = sorted(lat)[max(0, math.ceil(0.95 * len(lat)) - 1)]
    agg["errors"] = sum(1 for r in results if r.error)
    agg["n"] = len(results)
    return agg


# ---------------------------------------------------------------------------- report
def build_report(golden_path: Path, targets: dict[str, list[QueryResult]]) -> dict:
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "golden_set": str(golden_path),
        "n_queries": len(next(iter(targets.values()))) if targets else 0,
        "targets": {},
    }
    for name, results in targets.items():
        by_class: dict[str, list[QueryResult]] = defaultdict(list)
        for r in results:
            by_class[r.golden.cls].append(r)
        report["targets"][name] = {
            "overall": aggregate(results),
            "by_class": {c: aggregate(rs) for c, rs in sorted(by_class.items())},
            "failures": [
                {"id": r.golden.id, "class": r.golden.cls, "query": r.golden.query,
                 "expected": r.golden.expected, "got": r.ranked[:5], "strategy": r.strategy,
                 "error": r.error}
                for r in results if r.metrics.get("recall@5", 0) < 1.0
            ],
        }
    return report


def print_summary(report: dict) -> None:
    metrics = ["recall@1", "recall@5", "recall@10", "mrr", "ndcg@10", "latency_p50_ms"]
    print(f"\ngolden set: {report['golden_set']} ({report['n_queries']} queries)\n")
    header = f"{'target':10} {'class':16} {'n':>3} " + " ".join(f"{m:>14}" for m in metrics)
    print(header)
    print("-" * len(header))
    for name, t in report["targets"].items():
        rows = [("ALL", t["overall"])] + list(t["by_class"].items())
        for cls, agg in rows:
            vals = " ".join(f"{agg.get(m, 0):>14.3f}" for m in metrics)
            print(f"{name:10} {cls:16} {int(agg.get('n', 0)):>3} {vals}")
        if t["failures"]:
            print(f"  failures (recall@5 < 1): {len(t['failures'])}")
            for f in t["failures"][:10]:
                print(f"    {f['id']} [{f['class']}] {f['query']!r} -> {f['got']} (want {f['expected']})"
                      + (f" ERROR {f['error']}" if f["error"] else ""))
        print()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--golden", default=str(Path(__file__).with_name("golden_queries.jsonl")))
    p.add_argument("--target", action="append", required=True, metavar="NAME=URL",
                   help="retrieval endpoint; repeatable")
    p.add_argument("--size", type=int, default=10)
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--out", help="write JSON report here")
    p.add_argument("--min-recall5", type=float, default=None,
                   help="exit 1 if any target's overall recall@5 is below this (regression gate)")
    args = p.parse_args(argv)

    golden_path = Path(args.golden)
    golden = load_golden(golden_path)
    targets = {}
    for spec in args.target:
        name, _, url = spec.partition("=")
        if not url:
            p.error(f"--target needs NAME=URL, got {spec!r}")
        targets[name] = evaluate(golden, url, args.size, args.timeout)

    report = build_report(golden_path, targets)
    print_summary(report)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"report written to {out}")

    if args.min_recall5 is not None:
        bad = {n: t["overall"]["recall@5"] for n, t in report["targets"].items()
               if t["overall"].get("recall@5", 0) < args.min_recall5}
        if bad:
            print(f"REGRESSION: recall@5 below {args.min_recall5}: {bad}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
