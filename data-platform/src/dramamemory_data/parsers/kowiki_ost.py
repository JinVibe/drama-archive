"""OST tracks from a Korean Wikipedia drama article (source `kowiki`, CC BY-SA 4.0).

Wikidata carries almost no soundtrack data; kowiki articles do, in a fairly
regular shape under a "사운드 트랙"/"OST" heading:

    {{음반 정보 | 음반명 = 도깨비 OST Part. 1 | 가수명 = [[찬열]], [[펀치 (가수)|펀치]]
                | 발매년월일 = 2016년 12월 3일 ... }}
    === Part. 1 ===
    {{곡 목록 | 제목1 = 'Stay With Me' | 주1 = 찬열, 펀치 | 재생시간1 = 3:12
              | 제목2 = Stay With Me (Inst.) ... }}

and, in older articles, a wikitable with 제목/가수 columns. This parser reads
both, skips instrumentals, and gives every track a stable synthetic external id
(`<qid>:ost:p<part>:t<track>`) so re-runs map onto the same song rows.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import date

from dramamemory_data.normalization.models import (
    NormalizedArtist,
    NormalizedSong,
    NormalizedSongArtist,
)
from dramamemory_data.normalization.text import clean, normalize_key

PARSER_VERSION = "kowiki_ost/1"

_HEADING = re.compile(r"^(={2,})\s*(.*?)\s*\1\s*$", re.M)
_OST_HEADING = re.compile(r"OST|O\.S\.T|사운드\s*트랙|삽입곡|음악", re.I)
_PART = re.compile(r"(?:part|파트|pt)\.?\s*(\d+)", re.I)
_DATE = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_DURATION = re.compile(r"^(\d{1,2}):(\d{2})$")
_INSTRUMENTAL = re.compile(r"\(\s*inst\.?\s*\)|\binst\.?\b|\bMR\b|instrumental", re.I)
_ARTIST_SPLIT = re.compile(r"\s*(?:,|&|·|/|\bfeat\b\.?|\bft\b\.?|\bx\b|\bwith\b|및)\s*", re.I)
_TAG = re.compile(r"<[^>]+>")
_LINK = re.compile(r"\[\[([^\]|]*)(?:\|([^\]]*))?\]\]")
_TEMPLATE_INLINE = re.compile(r"\{\{[^{}]*\}\}")


@dataclass
class Album:
    part_no: int | None = None
    release_date: date | None = None
    artists: list[str] = field(default_factory=list)


def strip_wiki(value: str | None) -> str:
    """Wikitext -> plain text: links to their label, tags/templates/quotes dropped."""
    if not value:
        return ""
    s = _LINK.sub(lambda m: m.group(2) or m.group(1), value)
    s = _TEMPLATE_INLINE.sub("", s)
    s = _TAG.sub("", s)
    s = html.unescape(s).replace("'''", "").replace("''", "")
    s = s.strip().strip("'\"“”‘’")
    return clean(s) or ""


def ost_section(wikitext: str) -> str:
    """Text under the first OST-like heading, up to the next heading of the same or a
    higher level. Empty when the article has no such section."""
    for m in _HEADING.finditer(wikitext):
        if _OST_HEADING.search(m.group(2)):
            level = len(m.group(1))
            rest = wikitext[m.end() :]
            nxt = re.search(rf"^={{2,{level}}}[^=]", rest, re.M)
            return rest[: nxt.start()] if nxt else rest
    return ""


def templates(text: str, name: str) -> list[tuple[int, dict[str, str]]]:
    """(offset, params) for every {{name ...}} template, params split on top-level pipes."""
    out: list[tuple[int, dict[str, str]]] = []
    needle = "{{" + name
    pos = 0
    while (start := text.find(needle, pos)) != -1:
        depth = 0
        i = start
        while i < len(text):
            if text.startswith("{{", i):
                depth += 1
                i += 2
            elif text.startswith("}}", i):
                depth -= 1
                i += 2
                if depth == 0:
                    break
            else:
                i += 1
        body = text[start + 2 : i - 2]
        out.append((start, _split_params(body)))
        pos = i
    return out


def _split_params(body: str) -> dict[str, str]:
    parts: list[str] = []
    depth_t = depth_l = 0
    cur: list[str] = []
    i = 0
    while i < len(body):
        two = body[i : i + 2]
        if two == "{{":
            depth_t += 1
        elif two == "}}":
            depth_t -= 1
        elif two == "[[":
            depth_l += 1
        elif two == "]]":
            depth_l -= 1
        if body[i] == "|" and depth_t == 0 and depth_l == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(body[i])
        i += 1
    parts.append("".join(cur))
    params: dict[str, str] = {}
    for p in parts[1:]:
        key, _, value = p.partition("=")
        if key.strip():
            params[key.strip()] = value.strip()
    return params


_NOT_AN_ARTIST = re.compile(r"^(various artists|v\.?a\.?|여러 가수|various)$", re.I)


def split_artists(value: str) -> list[str]:
    names = [strip_wiki(n) for n in _ARTIST_SPLIT.split(strip_wiki(value)) if n and n.strip()]
    seen: list[str] = []
    for n in names:
        if n and normalize_key(n) and n not in seen and not _NOT_AN_ARTIST.match(n):
            seen.append(n)
    return seen


def _album(params: dict[str, str]) -> Album:
    title = strip_wiki(params.get("음반명") or params.get("앨범명") or "")
    part = _PART.search(title)
    d = _DATE.search(params.get("발매년월일") or params.get("발매일") or "")
    release = None
    if d:
        try:
            release = date(int(d.group(1)), int(d.group(2)), int(d.group(3)))
        except ValueError:
            release = None
    return Album(
        part_no=int(part.group(1)) if part else None,
        release_date=release,
        artists=split_artists(params.get("가수명") or params.get("가수") or ""),
    )


def _duration(value: str | None) -> int | None:
    m = _DURATION.match((value or "").strip())
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _tracks_from_template(params: dict[str, str]) -> list[tuple[str, list[str], int | None]]:
    out = []
    n = 1
    while f"제목{n}" in params:
        title = strip_wiki(params[f"제목{n}"])
        artists = split_artists(params.get(f"주{n}") or params.get(f"가수{n}") or "")
        out.append((title, artists, _duration(params.get(f"재생시간{n}"))))
        n += 1
    return out


_TABLE = re.compile(r"^\{\|.*?^\|\}", re.M | re.S)


def _column(cols: list[str], *names: str) -> int | None:
    for i, c in enumerate(cols):
        if any(n in c for n in names):
            return i
    return None


def _tracks_from_tables(text: str) -> list[tuple[str, list[str], int | None, int | None]]:
    """Wikitable rows (title, artists, duration, part) — column roles from the header."""
    out = []
    for table in _TABLE.findall(text):
        rows = [r for r in re.split(r"^\|-.*$", table, flags=re.M)]
        header = rows[0] if rows else ""
        cols = [
            strip_wiki(c)
            for c in re.split(r"\n!|!!", header)
            if c.strip() and not c.startswith("{|")
        ]

        ti = _column(cols, "제목", "곡명", "곡")
        ai = _column(cols, "가수", "아티스트", "노래", "부른")
        di = _column(cols, "재생", "길이")
        pi = _column(cols, "파트", "Part", "part")
        if ti is None or ai is None:
            continue
        for row in rows[1:]:
            cells = [strip_wiki(c) for c in re.split(r"\n\||\|\|", row) if c.strip()]
            if len(cells) <= max(ti, ai):
                continue
            part = None
            if pi is not None and pi < len(cells):
                m = _PART.search(cells[pi]) or re.search(r"(\d+)", cells[pi])
                part = int(m.group(1)) if m else None
            out.append(
                (
                    cells[ti],
                    split_artists(cells[ai]),
                    _duration(cells[di]) if di is not None and di < len(cells) else None,
                    part,
                )
            )
    return out


def parse(wikitext: str, *, qid: str) -> list[NormalizedSong]:
    section = ost_section(wikitext)
    if not section:
        return []
    events: list[tuple[int, str, object]] = []
    for pos, params in templates(section, "음반 정보"):
        events.append((pos, "album", _album(params)))
    for pos, params in templates(section, "곡 목록"):
        events.append((pos, "tracks", _tracks_from_template(params)))
    events.sort(key=lambda e: e[0])

    songs: list[NormalizedSong] = []
    seen: set[tuple[str, int | None]] = set()
    album = Album()
    track_no = 0

    def add(title: str, artists: list[str], duration: int | None, part: int | None, release):
        nonlocal track_no
        if not title or _INSTRUMENTAL.search(title):
            return
        if not artists and part is None:
            return  # score cue on a full-soundtrack album: no singer, no part
        key = (normalize_key(title), part)
        if not key[0] or key in seen:
            return
        seen.add(key)
        track_no += 1
        songs.append(
            NormalizedSong(
                external_id=f"{qid}:ost:p{part or 0}:t{track_no}",
                title=title,
                title_normalized=key[0],
                release_date=release,
                duration_seconds=duration,
                artists=[
                    NormalizedSongArtist(
                        artist=NormalizedArtist(name=n, name_normalized=normalize_key(n)),
                        role="PERFORMER",
                        sort_order=i + 1,
                    )
                    for i, n in enumerate(artists)
                ],
                part_no=part,
                track_no=track_no,
            )
        )

    for _, kind, payload in events:
        if kind == "album":
            album = payload  # type: ignore[assignment]
            continue
        for title, artists, duration in payload:  # type: ignore[union-attr]
            add(title, artists or album.artists, duration, album.part_no, album.release_date)

    if not songs:
        for title, artists, duration, part in _tracks_from_tables(section):
            add(title, artists, duration, part, None)
    return songs
