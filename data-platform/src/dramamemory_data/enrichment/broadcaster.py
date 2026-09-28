"""Infer a drama's channel from its Korean Wikipedia categories.

Wikidata has no "original broadcaster" (P449) for roughly one drama in ten;
kowiki files the same dramas under slot categories such as "SBS 금토드라마" or
"TvN의 텔레비전 드라마". A category that names exactly one channel decides it;
a "…드라마" category outranks a generic "…에서 방영한 프로그램" one, and
re-airing categories that name a second channel do not override it.
"""

from __future__ import annotations

import re

# (pattern over the category title, broadcaster.code). Order matters only for
# the label; each category must match exactly one channel to count.
CHANNEL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"한국방송공사|KBS", re.I), "kbs"),
    (re.compile(r"문화방송|MBC(?! ?에브리원)", re.I), "mbc"),
    (re.compile(r"MBC ?에브리원", re.I), "mbc_every1"),
    (re.compile(r"(?<![A-Z])SBS", re.I), "sbs"),
    (re.compile(r"JTBC", re.I), "jtbc"),
    (re.compile(r"(?<![A-Za-z])tvN", re.I), "tvn"),
    (re.compile(r"(?<![A-Za-z])OCN", re.I), "ocn"),
    (re.compile(r"채널 ?A(?![A-Za-z])", re.I), "channel_a"),
    (re.compile(r"TV ?조선", re.I), "tv_chosun"),
    (re.compile(r"매일방송|(?<![A-Za-z])MBN", re.I), "mbn"),
    (re.compile(r"(?<![A-Za-z])ENA(?![A-Za-z])", re.I), "ena"),
    (re.compile(r"엠넷|(?<![A-Za-z])Mnet", re.I), "mnet"),
    (re.compile(r"한국교육방송공사|(?<![A-Za-z])EBS", re.I), "ebs"),
    (re.compile(r"넷플릭스|Netflix", re.I), "netflix"),
    (re.compile(r"디즈니 ?\+|디즈니플러스|Disney\+", re.I), "disney_plus"),
    (re.compile(r"티빙|TVING", re.I), "tving"),
    (re.compile(r"웨이브|Wavve", re.I), "wavve"),
    (re.compile(r"쿠팡 ?플레이|Coupang Play", re.I), "coupang_play"),
    (re.compile(r"지니 ?TV|올레 ?TV|Genie TV", re.I), "genie_tv"),
    (re.compile(r"카카오 ?TV|Kakao TV", re.I), "kakao_tv"),
    (re.compile(r"네이버 ?TV|Naver TV", re.I), "naver_tv"),
]

_DRAMA_CATEGORY = re.compile(r"드라마|시트콤|연속극|미니시리즈")


def channels_in(category: str) -> set[str]:
    return {code for pattern, code in CHANNEL_PATTERNS if pattern.search(category)}


def infer_broadcaster(categories: list[str]) -> tuple[str | None, str | None]:
    """(broadcaster code, the category that decided it) or (None, None).

    Only categories naming exactly one channel vote. Drama-slot categories are
    tried first; if they disagree with each other, nothing is inferred (a
    co-production or a re-airing is not ours to guess)."""
    drama_votes: dict[str, str] = {}
    other_votes: dict[str, str] = {}
    for cat in categories:
        codes = channels_in(cat)
        if len(codes) != 1:
            continue
        code = next(iter(codes))
        bucket = drama_votes if _DRAMA_CATEGORY.search(cat) else other_votes
        bucket.setdefault(code, cat)
    for votes in (drama_votes, other_votes):
        if len(votes) == 1:
            code, cat = next(iter(votes.items()))
            return code, cat
        if len(votes) > 1:
            return None, None
    return None, None
