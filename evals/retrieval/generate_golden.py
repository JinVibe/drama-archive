#!/usr/bin/env python3
"""Generate golden queries from the canonical catalog (DM-901 at scale).

The hand-written set (golden_queries.jsonl) is small and written by the same
person who built the retrievers. This script derives queries mechanically from a
JSON dump of the catalog so the set is unbiased, reproducible (seeded) and grows
with the data. Query classes it can build without an LLM:

    entity_lookup   exact title / alias / english title
    person          "<actor> 나온 드라마", "<writer> 작가", "<actor1> <actor2>"
    multi_hop       "<actor1>랑 <actor2> 같이 나온 드라마" for real co-stars
    character       "<character> 역 <actor>" / "<character1> <character2>"
    temporal        "<year>년 <broadcaster> <genre>" where the answer set is small

semantic_memory needs paraphrased plots and stays hand-written.

Input: `dump.json` produced by evals/retrieval/dump_catalog.sql (see README).
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

GENRE_LABEL = {
    "romance": "로맨스",
    "comedy": "코미디",
    "melodrama": "멜로",
    "fantasy": "판타지",
    "thriller": "스릴러",
    "mystery": "미스터리",
    "crime": "범죄",
    "action": "액션",
    "medical": "의학",
    "legal": "법정",
    "historical": "사극",
    "family": "가족",
    "youth": "청춘",
    "office": "오피스",
    "sf": "SF",
    "horror": "공포",
    "daily": "일일",
}
BROADCASTER_LABEL = {
    "kbs": "KBS",
    "mbc": "MBC",
    "sbs": "SBS",
    "jtbc": "JTBC",
    "tvn": "tvN",
    "ocn": "OCN",
    "netflix": "넷플릭스",
    "tving": "티빙",
    "disney_plus": "디즈니+",
    "mbn": "MBN",
    "channel_a": "채널A",
    "tv_chosun": "TV조선",
    "ena": "ENA",
    "wavve": "웨이브",
}


def load(dump: Path) -> list[dict]:
    return json.loads(dump.read_text(encoding="utf-8"))


def generate(dramas: list[dict], *, seed: int, per_class: int) -> list[dict]:
    rng = random.Random(seed)
    out: list[dict] = []
    n = 0

    def add(cls: str, query: str, expected: list[str]) -> None:
        nonlocal n
        n += 1
        out.append({"id": f"g{n:04d}", "class": cls, "query": query, "expected": expected})

    # Titles that are unique across the catalog (so the expected answer is unambiguous).
    title_count = Counter(d["title"] for d in dramas)
    unique = [d for d in dramas if title_count[d["title"]] == 1]

    # ---- entity_lookup
    for d in rng.sample(unique, min(per_class, len(unique))):
        variants = (
            [d["title"]]
            + [a for a in d.get("aliases", []) if a]
            + ([d["title_en"]] if d.get("title_en") else [])
        )
        add("entity_lookup", rng.choice(variants), [d["slug"]])

    # ---- person: actors with 1-3 works (so expected sets stay small), writers/directors
    works: dict[str, list[dict]] = defaultdict(list)
    role: dict[str, set[str]] = defaultdict(set)
    for d in dramas:
        for c in d.get("credits", []):
            works[c["name"]].append(d)
            role[c["name"]].add(c["type"])
    person_pool = [nm for nm, ws in works.items() if 1 <= len(ws) <= 3]
    rng.shuffle(person_pool)
    for nm in person_pool[:per_class]:
        slugs = sorted({w["slug"] for w in works[nm]})
        if "WRITER" in role[nm] and "ACTOR" not in role[nm]:
            add("person", f"{nm} 작가 드라마", slugs)
        elif "DIRECTOR" in role[nm] and "ACTOR" not in role[nm]:
            add("person", f"{nm} 연출 작품", slugs)
        else:
            add("person", rng.choice([f"{nm} 나온 드라마", f"{nm} 출연작", f"배우 {nm}"]), slugs)

    # ---- multi_hop: two actors who share exactly one drama, each with >= 2 works
    pairs: dict[tuple[str, str], set[str]] = defaultdict(set)
    for d in dramas:
        actors = [c["name"] for c in d.get("credits", []) if c["type"] == "ACTOR"]
        for i, a in enumerate(actors):
            for b in actors[i + 1 :]:
                pairs[tuple(sorted((a, b)))].add(d["slug"])
    hard = [
        (p, s) for p, s in pairs.items() if len(s) == 1 and len(works[p[0]]) >= 2 and len(works[p[1]]) >= 2
    ]
    rng.shuffle(hard)
    for (a, b), slugs in hard[:per_class]:
        add(
            "multi_hop",
            rng.choice([f"{a}랑 {b} 같이 나온 드라마", f"{a} {b} 공동 출연작", f"{a}이랑 {b} 나온 작품"]),
            sorted(slugs),
        )

    # ---- character: named characters (unique across catalog)
    char_count = Counter(c["character"] for d in dramas for c in d.get("credits", []) if c.get("character"))
    char_pool = [
        (d, c)
        for d in dramas
        for c in d.get("credits", [])
        if c.get("character") and char_count[c["character"]] == 1
    ]
    rng.shuffle(char_pool)
    for d, c in char_pool[:per_class]:
        add(
            "character",
            rng.choice(
                [
                    f"{c['character']} 역 {c['name']}",
                    f"{c['character']} 나오는 드라마",
                    f"{c['name']} {c['character']}",
                ]
            ),
            [d["slug"]],
        )

    # ---- temporal: year + broadcaster (+ genre) combos whose answer set is 1-4 dramas
    combos: dict[tuple, list[str]] = defaultdict(list)
    for d in dramas:
        if not d.get("year") or not d.get("broadcaster"):
            continue
        for g in d.get("genres", []) or [None]:
            combos[(d["year"], d["broadcaster"], g)].append(d["slug"])
    small = [(k, v) for k, v in combos.items() if 1 <= len(v) <= 4 and k[1] in BROADCASTER_LABEL]
    rng.shuffle(small)
    for (year, bc, g), slugs in small[:per_class]:
        genre = f" {GENRE_LABEL.get(g, g)}" if g else ""
        add(
            "temporal",
            rng.choice(
                [
                    f"{year}년 {BROADCASTER_LABEL[bc]}{genre} 드라마",
                    f"{year}년에 {BROADCASTER_LABEL[bc]}에서 한{genre} 드라마",
                ]
            ),
            sorted(slugs),
        )

    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dump", required=True, help="catalog JSON dump (dump_catalog.sql output)")
    p.add_argument("--out", default=str(Path(__file__).with_name("golden_generated.jsonl")))
    p.add_argument("--seed", type=int, default=20260928)
    p.add_argument("--per-class", type=int, default=60)
    args = p.parse_args(argv)
    dramas = load(Path(args.dump))
    queries = generate(dramas, seed=args.seed, per_class=args.per_class)
    Path(args.out).write_text(
        "\n".join(json.dumps(q, ensure_ascii=False) for q in queries) + "\n", encoding="utf-8"
    )
    by_class = Counter(q["class"] for q in queries)
    print(f"{len(queries)} queries -> {args.out}: {dict(by_class)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
