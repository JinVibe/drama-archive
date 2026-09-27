"""Query analysis (DM-701 lite): pull hard constraints out of a memory query.

"2016년쯤 겨울에 tvN에서 했던 공유 나오는 판타지"
  -> year=2016 (±1 when "쯤"), broadcaster=tvn, remaining text for retrieval.

Deterministic rules only. An LLM extractor can replace this later behind the same
QueryPlan shape; nothing downstream should care which produced it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

BROADCASTER_ALIASES: dict[str, str] = {
    "kbs": "kbs", "케이비에스": "kbs", "kbs2": "kbs", "kbs1": "kbs",
    "mbc": "mbc", "엠비씨": "mbc",
    "sbs": "sbs", "에스비에스": "sbs",
    "jtbc": "jtbc", "제이티비씨": "jtbc",
    "tvn": "tvn", "티비엔": "tvn", "tvN": "tvn",
}

_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*년?\s*(대|쯤|경|초|중반|말|초반|후반)?")
_TWO_DIGIT_YEAR = re.compile(r"(?<![\d])(\d{2})\s*년\s*(대|쯤|경)?(?![\d])")
_DECADE = re.compile(r"(?<!\d)((?:19|20)?\d)0\s*년대\s*(초반?|중반|후반|말)?")
_BROADCASTER = re.compile(
    "|".join(sorted((re.escape(k) for k in BROADCASTER_ALIASES), key=len, reverse=True)),
    re.IGNORECASE,
)
_FILLER = re.compile(
    r"(에서|했던|하던|나온|나왔던|나오는|출연한|출연하는|드라마|작품|뭐였지|뭐지|뭐더라|기억|"
    r"찾아줘|알려줘|있었는데|같은|느낌|배경|였던|였는데|인데|이었는데)"
)
# Particles left dangling once a filler word is removed ("배경에" -> "에").
_PARTICLE = re.compile(r"(?:(?<=\s)|^)(에서|에|의|은|는|이|가|을|를|도|로|와|과)(?=\s|$)")


@dataclass(frozen=True)
class QueryPlan:
    raw: str
    text: str                                  # retrieval text; "" when only constraints
    year_from: int | None = None
    year_to: int | None = None
    broadcaster: str | None = None
    signals: dict[str, str] = field(default_factory=dict)

    @property
    def has_constraints(self) -> bool:
        return self.year_from is not None or self.broadcaster is not None


def _year_window(year: int, qualifier: str | None) -> tuple[int, int]:
    if qualifier in ("쯤", "경"):
        return year - 1, year + 1
    return year, year


def analyze(raw: str, *, extract_constraints: bool = True) -> QueryPlan:
    """With extract_constraints=False only filler/particles are stripped: used to relax a
    query whose "year" was really part of a title (응답하라 1988)."""
    text = raw.strip()
    signals: dict[str, str] = {}
    year_from = year_to = None
    broadcaster = None

    if not extract_constraints:
        pass
    elif m := _DECADE.search(text):
        head = m.group(1)
        if len(head) == 3:                     # 201 -> 2010s
            base = int(head) * 10
        else:                                   # 9 -> 1990s, 0/1 -> 2000s/2010s
            base = (1900 if int(head) >= 5 else 2000) + int(head) * 10
        part = m.group(2) or ""
        if part.startswith("초"):
            year_from, year_to = base, base + 3
        elif part == "중반":
            year_from, year_to = base + 3, base + 6
        elif part in ("후반", "말"):
            year_from, year_to = base + 6, base + 9
        else:
            year_from, year_to = base, base + 9
        signals["decade"] = m.group(0)
        text = text.replace(m.group(0), " ")
    elif m := _YEAR.search(text):
        year_from, year_to = _year_window(int(m.group(1)), m.group(2))
        signals["year"] = m.group(0)
        text = text.replace(m.group(0), " ")
    elif m := _TWO_DIGIT_YEAR.search(text):
        yy = int(m.group(1))
        year = 2000 + yy if yy < 50 else 1900 + yy
        year_from, year_to = _year_window(year, m.group(2))
        signals["year"] = m.group(0)
        text = text.replace(m.group(0), " ")

    if extract_constraints and (m := _BROADCASTER.search(text)):
        token = m.group(0)
        broadcaster = BROADCASTER_ALIASES.get(token) or BROADCASTER_ALIASES.get(token.lower())
        signals["broadcaster"] = m.group(0)
        text = text[: m.start()] + " " + text[m.end():]

    text = _FILLER.sub(" ", text)
    text = _PARTICLE.sub(" ", text)
    # Constraint-only queries ("2016년 tvN") leave no text; retrievers then skip to the filter.
    text = re.sub(r"[\s,.?!]+", " ", text).strip()

    return QueryPlan(raw=raw, text=text, year_from=year_from, year_to=year_to,
                     broadcaster=broadcaster, signals=signals)
