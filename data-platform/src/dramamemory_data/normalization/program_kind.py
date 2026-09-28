"""Is this Wikidata item a drama at all?

Wikidata's "television series" class covers variety shows, talk shows and
reality programmes as well as dramas, so a class filter alone let 《런닝맨》 and
《스트릿댄스 걸스 파이터》 into the catalog. This module turns the signals we can
get without an LLM — instance-of classes, genre items/labels and (when known)
Korean Wikipedia categories — into one of three kinds:

    DRAMA       at least one drama signal and no non-drama signal
    NOT_DRAMA   at least one non-drama signal and no drama signal
    UNKNOWN     neither, or both (the caller may look up kowiki categories,
                which are the strongest signal we have, and classify again)

Deterministic and unit-tested; the discovery DAG, the Wikidata parser and the
quality gate all use the same rules.
"""

from __future__ import annotations

import re
from typing import Literal

ProgramKind = Literal["DRAMA", "NOT_DRAMA", "UNKNOWN"]

# Classes (P31) that mean "a scripted series": their presence neutralises the
# weak non-drama classes below (a web drama adapted from a webcomic can share
# an item with the comic).
SERIES_CLASSES: frozenset[str] = frozenset(
    {
        "Q5398426",  # television series
        "Q526877",  # web series
        "Q1259759",  # miniseries
        "Q482612",  # Korean drama
        "Q24855895",  # web drama
        "Q15416",  # television program
        "Q3464665",  # television series season
        "Q61704031",  # web series season
        "Q506240",  # television film
        "Q98701476",  # television film broadcast in two parts
        "Q12623153",  # KBS2 daily drama
        "Q6863157",  # MBC weekend drama
    }
)
# Classes that are drama by definition.
DRAMA_CLASSES: frozenset[str] = frozenset(
    {
        "Q482612",
        "Q24855895",
        "Q12623153",
        "Q6863157",
        "Q506240",
        "Q98701476",
    }
)
# Classes that are never a drama, whatever else the item claims.
STRONG_NON_DRAMA_CLASSES: frozenset[str] = frozenset(
    {
        "Q336181",  # variety show
        "Q622812",  # talk show
        "Q173799",  # entertainment
        "Q21191270",  # television series episode
        "Q13406463",  # Wikimedia list article
        "Q18340514",  # events in a specific year
        "Q2155186",  # program block
        "Q581714",  # animated series
        "Q63952888",  # animated television series
        "Q1555508",  # radio program
        "Q1132548",  # news program
    }
)
# Classes that are not a drama unless a series class is also present.
WEAK_NON_DRAMA_CLASSES: frozenset[str] = frozenset(
    {
        "Q11424",  # film
        "Q7725634",  # literary work
        "Q21198342",  # Japanese manga series
        "Q74262765",  # Korean manga series
        "Q7978994",  # webtoon
        "Q213369",  # webcomic
    }
)

# Genre (P136) labels, ko/en. Drama genres name a kind of fiction.
DRAMA_GENRE = re.compile(
    r"드라마|drama|시트콤|sitcom|thriller|스릴러|mystery|미스터리|crime|범죄|fantasy|판타지"
    r"|romance|romantic|로맨|melodrama|멜로|사극|시대극|역사물|historical|action|액션"
    r"|science fiction|\bsf\b|horror|공포|comedy|코미디|희극|adventure|lgbt|coming-of-age"
    r"|supernatural|추리|web series|웹 시리즈|superhero|soap|\bwar\b|teen|틴|학원|특촬물"
    r"|tokusatsu|noir|누아르|omnibus|옴니버스|anthology|musical|뮤지컬|sports drama",
    re.IGNORECASE,
)
NON_DRAMA_GENRE = re.compile(
    r"리얼리티|reality|버라이어티|variety|토크|talk show|게임 쇼|game show|music television"
    r"|music program|음악 프로그램|travel|여행|다큐|documentary|기행|competition|경연"
    r"|서바이벌|survival|퀴즈|quiz|cooking|요리|뉴스|news|\bsport\b|스포츠|award|시상"
    r"|애니메이션|animat|makeover|dating show|연애 프로그램|infotainment|교양",
    re.IGNORECASE,
)

# Korean Wikipedia categories. "…드라마" categories are curated by people and
# beat every Wikidata signal.
KOWIKI_DRAMA_CATEGORY = re.compile(r"드라마")
KOWIKI_LIST_CATEGORY = re.compile(r"목록")
KOWIKI_NON_DRAMA_CATEGORY = re.compile(
    r"예능|리얼리티|버라이어티|토크 ?쇼|음악 프로그램|오디션|다큐멘터리|시사|교양|뉴스|스포츠"
    r"|퀴즈|게임 쇼|경연|서바이벌|애니메이션|영화|만화|소설|웹툰|목록"
)


def classify(
    *,
    classes: set[str] | frozenset[str] | list[str] = (),
    genre_labels: list[str] | tuple[str, ...] = (),
    kowiki_categories: list[str] | tuple[str, ...] | None = None,
) -> tuple[ProgramKind, list[str]]:
    """Return (kind, reasons). Reasons are short strings for the manifest/issue log."""
    cls = frozenset(classes)
    drama: list[str] = []
    non: list[str] = []

    # An episode, a list article, a variety show: never a drama, whatever kowiki
    # files it under ("2016년 대한민국의 텔레비전 드라마 목록" sits in a drama category).
    strong = cls & STRONG_NON_DRAMA_CLASSES
    if strong:
        return "NOT_DRAMA", [f"class {sorted(strong)[0]}"]

    if kowiki_categories:
        drama_cats = [
            c for c in kowiki_categories
            if KOWIKI_DRAMA_CATEGORY.search(c) and not KOWIKI_LIST_CATEGORY.search(c)
        ]
        if drama_cats:
            return "DRAMA", ["kowiki category"]
        hits = [c for c in kowiki_categories if KOWIKI_NON_DRAMA_CATEGORY.search(c)]
        if hits:
            non.append(f"kowiki category {hits[0]}")

    if cls & DRAMA_CLASSES:
        drama.append(f"class {sorted(cls & DRAMA_CLASSES)[0]}")
    # Film / comic / novel classes without a series class are only a hint: a 단막극
    # is often filed as "film" on Wikidata yet sits in kowiki's drama categories, so
    # on their own they leave the verdict UNKNOWN for the categories to settle.

    for label in genre_labels:
        if DRAMA_GENRE.search(label):
            drama.append(f"genre {label}")
        elif NON_DRAMA_GENRE.search(label):
            non.append(f"genre {label}")

    if drama and not non:
        return "DRAMA", drama[:2]
    if non and not drama:
        return "NOT_DRAMA", non[:2]
    if drama and non:
        return "UNKNOWN", [*drama[:1], *non[:1]]
    return "UNKNOWN", []
