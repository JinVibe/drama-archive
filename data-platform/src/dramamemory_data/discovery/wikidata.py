"""Discovery of Korean dramas for the `wikidata` source.

Two candidate lists, one verdict:

  1. Wikidata SPARQL: every item with a series-like class (television series,
     web series, miniseries, season, TV film, …), country of origin South Korea
     and a start date in or after `year_from`. Broad on purpose — it also
     returns variety and reality shows.
  2. Korean Wikipedia: the members of 분류:{year}년 텔레비전 드라마 for each year,
     keeping the pages whose categories say they are Korean. These are curated
     by people and catch the many dramas Wikidata files under a generic class
     or without a start date.

The union is classified with normalization.program_kind using the items'
classes, genre labels, country and — for the ambiguous ones — their kowiki
categories. NOT_DRAMA and foreign items go to an exclusion list the publish DAG
uses to hide anything that slipped in earlier; DRAMA and UNKNOWN items become
the manifest the ingest DAG fetches.

Network functions take an httpx.Client; the merge/decide functions are pure.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from dramamemory_data.normalization.program_kind import ProgramKind, classify
from dramamemory_data.parsers.wikidata_sparql import SPARQL_ENDPOINT, detail_url

KOWIKI_API = "https://ko.wikipedia.org/w/api.php"
KOREA = "Q884"

# Series-like classes; the classifier decides drama vs not. Direct instances only
# so animation classes stay out.
LIST_QUERY = """
SELECT DISTINCT ?item WHERE {
  VALUES ?cls { wd:Q5398426 wd:Q526877 wd:Q1259759 wd:Q482612 wd:Q24855895
                wd:Q15416 wd:Q3464665 wd:Q506240 wd:Q12623153 wd:Q6863157 }
  ?item wdt:P31 ?cls ; wdt:P495 wd:Q884 ; wdt:P580 ?start .
  FILTER(YEAR(?start) >= %d)
}
"""

# Per-candidate signals, VALUES-batched.
DETAILS_QUERY = """
SELECT ?item ?itemLabel ?cls ?genreLabel ?country ?article WHERE {
  VALUES ?item { %s }
  OPTIONAL { ?item wdt:P31 ?cls }
  OPTIONAL { ?item wdt:P136 ?genre }
  OPTIONAL { ?item wdt:P495 ?country }
  OPTIONAL { ?article schema:about ?item ; schema:isPartOf <https://ko.wikipedia.org/> }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ko,en". }
}
"""

# A kowiki drama-of-the-year category member counts as Korean when one of its
# categories names Korea or a Korean channel/platform.
KOREAN_CATEGORY = re.compile(
    r"대한민국|한국|KBS|MBC|SBS|JTBC|tvN|OCN|채널A|TV조선|MBN|ENA|넷플릭스|티빙|웨이브|쿠팡|디즈니"
    r"|카카오|네이버|왓챠|U\+|지니"
)


@dataclass
class Candidate:
    qid: str
    label: str | None = None
    found_by: set[str] = field(default_factory=set)  # "sparql" and/or "kowiki"
    classes: set[str] = field(default_factory=set)
    genre_labels: list[str] = field(default_factory=list)
    countries: set[str] = field(default_factory=set)
    article: str | None = None
    kowiki_categories: list[str] = field(default_factory=list)
    kind: ProgramKind = "UNKNOWN"
    reasons: list[str] = field(default_factory=list)

    def decide(self) -> None:
        self.kind, self.reasons = classify(
            classes=self.classes,
            genre_labels=self.genre_labels,
            kowiki_categories=self.kowiki_categories or None,
        )


def year_categories(year_from: int, year_to: int) -> list[str]:
    return [f"분류:{y}년 텔레비전 드라마" for y in range(year_from, year_to + 1)]


# ---------------------------------------------------------------- network


def sparql(client: httpx.Client, query: str, *, user_agent: str) -> list[dict[str, Any]]:
    resp = client.get(
        SPARQL_ENDPOINT,
        params={"format": "json", "query": query},
        headers={"User-Agent": user_agent, "Accept": "application/sparql-results+json"},
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()["results"]["bindings"]


def list_qids(client: httpx.Client, *, year_from: int, user_agent: str) -> set[str]:
    return {
        r["item"]["value"].rsplit("/", 1)[1]
        for r in sparql(client, LIST_QUERY % year_from, user_agent=user_agent)
    }


def mediawiki(client: httpx.Client, params: dict[str, str], *, user_agent: str) -> dict:
    resp = client.get(
        KOWIKI_API,
        params={"action": "query", "format": "json", **params},
        headers={"User-Agent": user_agent},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def category_members(
    client: httpx.Client, category: str, *, user_agent: str, min_interval: float = 0.25
) -> dict[str, dict[str, Any]]:
    """title -> {"qid": str | None, "categories": [..]} for every article in `category`."""
    pages: dict[str, dict[str, Any]] = {}
    cont: dict[str, str] = {}
    while True:
        data = mediawiki(
            client,
            {
                "generator": "categorymembers",
                "gcmtitle": category,
                "gcmnamespace": "0",
                "gcmlimit": "200",
                "prop": "pageprops|categories",
                "ppprop": "wikibase_item",
                "cllimit": "max",
                **cont,
            },
            user_agent=user_agent,
        )
        for page in data.get("query", {}).get("pages", {}).values():
            entry = pages.setdefault(page["title"], {"qid": None, "categories": []})
            if "pageprops" in page:
                entry["qid"] = page["pageprops"].get("wikibase_item")
            for cat in page.get("categories", []):
                if cat["title"] not in entry["categories"]:
                    entry["categories"].append(cat["title"])
        if "continue" not in data:
            return pages
        cont = data["continue"]
        time.sleep(min_interval)


def page_categories(
    client: httpx.Client, titles: list[str], *, user_agent: str, min_interval: float = 0.25
) -> dict[str, list[str]]:
    """Categories of the given article titles, 50 per request."""
    out: dict[str, list[str]] = {}
    for i in range(0, len(titles), 50):
        chunk = titles[i : i + 50]
        cont: dict[str, str] = {}
        while True:
            data = mediawiki(
                client,
                {"titles": "|".join(chunk), "prop": "categories", "cllimit": "max", **cont},
                user_agent=user_agent,
            )
            for page in data.get("query", {}).get("pages", {}).values():
                cats = out.setdefault(page["title"], [])
                cats.extend(
                    c["title"] for c in page.get("categories", []) if c["title"] not in cats
                )
            if "continue" not in data:
                break
            cont = data["continue"]
        time.sleep(min_interval)
    return out


def fetch_details(
    client: httpx.Client,
    qids: list[str],
    *,
    user_agent: str,
    batch: int = 200,
    min_interval: float = 1.0,
) -> dict[str, dict[str, Any]]:
    """qid -> {label, classes, genre_labels, countries, article} via DETAILS_QUERY."""
    out: dict[str, dict[str, Any]] = {}
    for i in range(0, len(qids), batch):
        values = " ".join(f"wd:{q}" for q in qids[i : i + batch])
        for r in sparql(client, DETAILS_QUERY % values, user_agent=user_agent):
            merge_detail_row(out, r)
        time.sleep(min_interval)
    return out


# ---------------------------------------------------------------- pure


def merge_detail_row(out: dict[str, dict[str, Any]], r: dict[str, Any]) -> None:
    qid = r["item"]["value"].rsplit("/", 1)[1]
    e = out.setdefault(
        qid,
        {"label": None, "classes": set(), "genre_labels": [], "countries": set(), "article": None},
    )
    label = r.get("itemLabel", {}).get("value")
    if label and label != qid:
        e["label"] = label
    if "cls" in r:
        e["classes"].add(r["cls"]["value"].rsplit("/", 1)[1])
    if "genreLabel" in r and r["genreLabel"]["value"] not in e["genre_labels"]:
        e["genre_labels"].append(r["genreLabel"]["value"])
    if "country" in r:
        e["countries"].add(r["country"]["value"].rsplit("/", 1)[1])
    if "article" in r and not e["article"]:
        from urllib.parse import unquote

        e["article"] = unquote(r["article"]["value"].rsplit("/wiki/", 1)[1]).replace("_", " ")


def build_candidates(
    sparql_qids: set[str],
    kowiki_pages: dict[str, dict[str, Any]],
    details: dict[str, dict[str, Any]],
) -> dict[str, Candidate]:
    """Union of both lists with their signals attached. kowiki pages without a
    Wikidata item are dropped (nothing to fetch)."""
    cands: dict[str, Candidate] = {}
    for qid in sparql_qids:
        cands.setdefault(qid, Candidate(qid)).found_by.add("sparql")
    for title, page in kowiki_pages.items():
        qid = page.get("qid")
        if not qid:
            continue
        c = cands.setdefault(qid, Candidate(qid))
        c.found_by.add("kowiki")
        c.article = c.article or title
        for cat in page.get("categories", []):
            if cat not in c.kowiki_categories:
                c.kowiki_categories.append(cat)
    for qid, c in cands.items():
        d = details.get(qid)
        if not d:
            continue
        c.label = d.get("label")
        c.classes |= set(d.get("classes", ()))
        c.genre_labels = list(d.get("genre_labels", ()))
        c.countries |= set(d.get("countries", ()))
        c.article = c.article or d.get("article")
    return cands


def is_foreign(c: Candidate) -> bool:
    """Country known and not Korea; a kowiki-only page also needs a Korean category."""
    if c.countries:
        return KOREA not in c.countries
    if "sparql" in c.found_by:
        return False
    return not any(KOREAN_CATEGORY.search(cat) for cat in c.kowiki_categories)


def needs_category_lookup(c: Candidate) -> bool:
    return c.kind == "UNKNOWN" and bool(c.article) and not c.kowiki_categories


def decide(cands: dict[str, Candidate]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(manifest items, excluded items). Each candidate has been `decide()`d already."""
    items: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for qid in sorted(cands, key=lambda q: int(q[1:])):
        c = cands[qid]
        if is_foreign(c):
            excluded.append(
                {
                    "external_id": qid,
                    "title": c.label,
                    "reason": "foreign",
                    "countries": sorted(c.countries),
                }
            )
        elif c.kind == "NOT_DRAMA":
            excluded.append(
                {
                    "external_id": qid,
                    "title": c.label,
                    "reason": "not_a_drama",
                    "signals": c.reasons,
                }
            )
        else:
            items.append(
                {"external_id": qid, "entity_type": "DRAMA", "url": detail_url(qid), "kind": c.kind}
            )
    return items, excluded
