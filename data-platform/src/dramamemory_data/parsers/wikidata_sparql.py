"""Parser for one drama's Wikidata SPARQL detail result (source `wikidata`).

The raw snapshot is the JSON response of DETAIL_QUERY for a single item: one row
per statement (instance-of classes, dates, broadcaster, episodes, genres, cast with
character and birth date, director, writer) plus label/alias rows. Classes and genre
labels feed normalization.program_kind so variety/reality shows are rejected.
Q-ids become external ids for the drama and for every person, so re-ingests and
cross-drama matches are deterministic. No synopsis: Wikidata has none.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date

from dramamemory_data.normalization.dates import DateParseError, parse_date
from dramamemory_data.normalization.models import (
    NormalizedAlias,
    NormalizedCredit,
    NormalizedDrama,
    NormalizedLink,
    NormalizedPerson,
)
from dramamemory_data.normalization.program_kind import classify
from dramamemory_data.normalization.text import clean, normalize_key

PARSER_VERSION = "wikidata_sparql/4"
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

# Statements we ask for, per item. Label/alias rows and the Korean Wikipedia sitelink
# come through the UNION branches. P856 (official website) and P1874 (Netflix ID)
# become official links; the sitelink title stands in when the item has no label.
DETAIL_QUERY = """
SELECT ?item ?p ?o ?oLabel ?charLabel ?birth ?ord ?lang WHERE {
  BIND(wd:%s AS ?item)
  {
    ?item ?p ?st . ?st ?ps ?o .
    ?prop wikibase:claim ?p ; wikibase:statementProperty ?ps .
    FILTER(?prop IN (wd:P31, wd:P580, wd:P582, wd:P449, wd:P1113, wd:P136, wd:P161, wd:P57, wd:P58, wd:P1476, wd:P856, wd:P1874))
    OPTIONAL { ?st pq:P453 ?char }
    OPTIONAL { ?st pq:P1545 ?ord }
    OPTIONAL { ?o wdt:P569 ?birth }
    SERVICE wikibase:label { bd:serviceParam wikibase:language "ko,en" . ?o rdfs:label ?oLabel . ?char rdfs:label ?charLabel }
  } UNION {
    ?item rdfs:label ?o . FILTER(LANG(?o) IN ("ko","en")) BIND(LANG(?o) AS ?lang) BIND("label" AS ?p)
  } UNION {
    ?item skos:altLabel ?o . FILTER(LANG(?o) IN ("ko","en")) BIND(LANG(?o) AS ?lang) BIND("alias" AS ?p)
  } UNION {
    ?article schema:about ?item ; schema:isPartOf <https://ko.wikipedia.org/> ; schema:name ?o . BIND("sitelink" AS ?p)
  }
}
"""

# " (드라마)", " (2016년 드라마)" and the like on Korean Wikipedia article titles.
_DISAMBIG = re.compile(r"\s*\((?:\d{4}년 )?(?:드라마|텔레비전 드라마|영화|웹 드라마|웹드라마)\)$")

# Wikidata broadcaster / platform items -> broadcaster.code (V5 + V12 seeds).
BROADCASTER_BY_QID: dict[str, str] = {
    "Q498825": "kbs",  # KBS
    "Q624509": "kbs",  # KBS2
    "Q777278": "kbs",  # KBS1
    "Q482607": "mbc",  # MBC
    "Q10854650": "mbc",  # MBC TV
    "Q928831": "sbs",  # SBS
    "Q16172404": "sbs",  # SBS TV
    "Q213097": "jtbc",
    "Q333424": "tvn",
    "Q626419": "ocn",
    "Q6729143": "mbn",
    "Q492438": "channel_a",
    "Q486605": "tv_chosun",
    "Q12618747": "ena",
    "Q490182": "mnet",
    "Q6714697": "mbc_every1",
    "Q12580927": "ebs",
    "Q907311": "netflix",
    "Q54958752": "disney_plus",
    "Q12621401": "tving",
    "Q65233413": "wavve",
    "Q116638614": "coupang_play",
    "Q7088285": "genie_tv",
    "Q21825231": "kakao_tv",
    "Q64822152": "naver_tv",
}

# Original networks first, then cable, then platforms: when P449 lists several,
# the archive files the drama under the earliest tier it aired on.
NETWORK_PRIORITY: list[str] = [
    "kbs", "mbc", "sbs", "tvn", "jtbc",
    "ocn", "mbn", "channel_a", "tv_chosun", "ena", "mnet", "mbc_every1", "ebs",
    "netflix", "disney_plus", "tving", "wavve", "coupang_play", "genie_tv", "kakao_tv",
    "naver_tv",
]


def _broadcaster_priority(code: str) -> int:
    return NETWORK_PRIORITY.index(code) if code in NETWORK_PRIORITY else len(NETWORK_PRIORITY)


# Genre label keywords (ko/en, lowercase) -> genre.code. First match wins per label.
GENRE_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("로맨틱 코미디", "romantic comedy"), "romance"),
    (("로맨스", "romance", "연애"), "romance"),
    (("코미디", "comedy", "시트콤", "sitcom"), "comedy"),
    (("판타지", "fantasy"), "fantasy"),
    (("스릴러", "thriller"), "thriller"),
    (("미스터리", "추리", "mystery"), "mystery"),
    (("범죄", "crime"), "crime"),
    (("액션", "action"), "action"),
    (("의학", "medical"), "medical"),
    (("법정", "legal", "법률"), "legal"),
    (("사극", "시대극", "역사", "historical", "period"), "historical"),
    (("가족", "family"), "family"),
    (("청춘", "youth", "coming-of-age", "학원"), "youth"),
    (("멜로", "melodrama"), "melodrama"),
    (("공포", "horror"), "horror"),
    (("공상과학", "science fiction", "sf"), "sf"),
    (("일일", "daily"), "daily"),
    (("오피스", "office", "workplace", "직장"), "office"),
]

_QID = re.compile(r"^Q\d+$")
_ENTITY = re.compile(r"/entity/(Q\d+)$")


class WikidataParseError(ValueError):
    pass


def detail_url(qid: str) -> str:
    from urllib.parse import urlencode

    return f"{SPARQL_ENDPOINT}?{urlencode({'format': 'json', 'query': DETAIL_QUERY % qid})}"


def _qid(uri: str) -> str | None:
    m = _ENTITY.search(uri)
    return m.group(1) if m else None


def _date(value: str | None, field: str) -> date | None:
    try:
        return parse_date(value)
    except DateParseError as exc:
        raise WikidataParseError(f"{field}: {exc}") from exc


def _soft_date(value: str | None) -> date | None:
    """Optional dates (a person's birth) may be Wikidata 'unknown value' nodes or odd
    precisions; those become None instead of failing the whole drama."""
    try:
        return parse_date(value)
    except DateParseError:
        return None


def genre_codes(labels: list[str]) -> list[str]:
    codes: list[str] = []
    for label in labels:
        low = label.lower()
        for keywords, code in GENRE_KEYWORDS:
            if any(k in low for k in keywords):
                if code not in codes:
                    codes.append(code)
                # "로맨틱 코미디" carries both
                if keywords[0] == "로맨틱 코미디" and "comedy" not in codes:
                    codes.append("comedy")
                break
    return sorted(codes)


def parse(body: bytes) -> NormalizedDrama:
    try:
        rows = json.loads(body.decode("utf-8"))["results"]["bindings"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise WikidataParseError(f"not a SPARQL JSON result: {exc}") from exc
    if not rows:
        raise WikidataParseError("empty result (item deleted or query returned nothing)")

    item = _qid(rows[0]["item"]["value"]) if "item" in rows[0] else None
    if not item:
        raise WikidataParseError("result has no ?item binding")

    labels: dict[str, str] = {}
    aliases: list[str] = []
    props: dict[str, list[dict]] = defaultdict(list)
    sitelink: str | None = None
    for r in rows:
        p = r["p"]["value"]
        if p == "label":
            labels[r["lang"]["value"]] = r["o"]["value"]
        elif p == "alias":
            aliases.append(r["o"]["value"])
        elif p == "sitelink":
            sitelink = clean(_DISAMBIG.sub("", r["o"]["value"]))
        else:
            props[p.rsplit("/", 1)[1]].append(r)

    def values(pid: str) -> list[str]:
        return [r["o"]["value"] for r in props.get(pid, [])]

    def label_of(r: dict) -> str | None:
        lab = clean(r.get("oLabel", {}).get("value"))
        return None if not lab or _QID.match(lab) else lab

    original = [clean(v) for v in values("P1476")]
    # Korean label, else the original title, else the kowiki article title (items created
    # from a sitelink alone often have no label at all), else the English label.
    title_ko = (
        clean(labels.get("ko"))
        or (original[0] if original else None)
        or sitelink
        or clean(labels.get("en"))
    )
    if not title_ko:
        raise WikidataParseError(f"{item}: no usable title")
    title_en = clean(labels.get("en"))
    alias_set: list[NormalizedAlias] = []
    seen = {normalize_key(title_ko)}
    for a in [*original, *aliases, *([sitelink] if sitelink else [])]:
        a = clean(a)
        if a and normalize_key(a) and normalize_key(a) not in seen and not a.startswith("-"):
            seen.add(normalize_key(a))
            alias_set.append(NormalizedAlias(alias=a, alias_normalized=normalize_key(a)))

    starts = sorted(d for d in (_date(v, "P580") for v in values("P580")) if d)
    ends = sorted(d for d in (_date(v, "P582") for v in values("P582")) if d)
    episodes = None
    for v in values("P1113"):
        try:
            episodes = int(float(v))
            break
        except ValueError:
            continue

    # A drama often lists its network and the OTT that streams it (P449: KBS, Netflix).
    # The archive is organised by the original network, so those win over platforms.
    mapped = [
        code
        for code in (BROADCASTER_BY_QID.get(_qid(r["o"]["value"]) or "") for r in props.get("P449", []))
        if code
    ]
    broadcaster_code = min(mapped, key=_broadcaster_priority) if mapped else None

    genre_labels = [g for g in (label_of(r) for r in props.get("P136", [])) if g]
    genres = genre_codes(genre_labels)
    classes = {q for q in (_qid(r["o"]["value"]) for r in props.get("P31", [])) if q}
    program_kind, _ = classify(classes=classes, genre_labels=genre_labels)

    def credits_for(pid: str, credit_type: str) -> list[NormalizedCredit]:
        out: list[NormalizedCredit] = []
        seen_people: set[str] = set()
        for r in props.get(pid, []):
            person_qid = _qid(r["o"]["value"])
            name = label_of(r)
            if not person_qid or not name or person_qid in seen_people:
                continue
            seen_people.add(person_qid)
            ordinal = r.get("ord", {}).get("value")
            character = clean(r.get("charLabel", {}).get("value"))
            if character and _QID.match(character):
                character = None
            out.append(
                NormalizedCredit(
                    person=NormalizedPerson(
                        external_id=person_qid,
                        name_ko=name,
                        name_normalized=normalize_key(name),
                        birth_date=_soft_date(r.get("birth", {}).get("value")),
                    ),
                    credit_type=credit_type,
                    character_name=character,
                    billing_order=int(ordinal) if ordinal and ordinal.isdigit() else None,
                    is_main_cast=bool(ordinal and ordinal.isdigit() and int(ordinal) <= 4),
                )
            )
        return out

    return NormalizedDrama(
        external_id=item,
        title_ko=title_ko,
        title_en=title_en if title_en and title_en != title_ko else None,
        title_normalized=normalize_key(title_ko),
        aliases=alias_set,
        broadcaster_code=broadcaster_code,
        start_date=starts[0] if starts else None,
        end_date=ends[-1] if ends else None,
        episode_count=episodes,
        genres=genres,
        credits=[
            *credits_for("P161", "ACTOR"),
            *credits_for("P57", "DIRECTOR"),
            *credits_for("P58", "WRITER"),
        ],
        links=official_links(values("P856"), values("P1874"), broadcaster_code),
        program_kind=program_kind,
    )


def official_links(
    websites: list[str], netflix_ids: list[str], broadcaster_code: str | None
) -> list[NormalizedLink]:
    """P856 official website -> the broadcaster's page (or a generic official page);
    P1874 Netflix ID -> the title page on Netflix. https only (quality gate rule);
    the link validator checks them afterwards."""
    out: list[NormalizedLink] = []
    seen: set[str] = set()
    for url in websites:
        url = clean(url) or ""
        if not url.startswith("https://") or url in seen:
            continue
        seen.add(url)
        out.append(
            NormalizedLink(
                provider_code=broadcaster_code or "official",
                url=url,
                link_type="BROADCASTER_PAGE",
            )
        )
    for nid in netflix_ids:
        nid = (clean(nid) or "").strip()
        if not nid.isdigit():
            continue
        url = f"https://www.netflix.com/title/{nid}"
        if url in seen:
            continue
        seen.add(url)
        out.append(NormalizedLink(provider_code="netflix", url=url, link_type="OTT_DETAIL"))
    return out
