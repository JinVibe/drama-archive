"""Parser for the curated `dramamemory.drama.v1` JSON format.

This is the hand-written input format used by the `manual` and `local_seed`
sources (see data-platform/seed/README.md). It is intentionally forgiving on
dates/whitespace and strict on structure.
"""

from __future__ import annotations

import json
from datetime import date

from pydantic import BaseModel, Field, ValidationError

from dramamemory_data.normalization.dates import DateParseError, parse_date
from dramamemory_data.normalization.models import (
    ArtistRole,
    CreditType,
    LinkType,
    NormalizedAlias,
    NormalizedArtist,
    NormalizedCredit,
    NormalizedDrama,
    NormalizedLink,
    NormalizedPerson,
    NormalizedSong,
    NormalizedSongArtist,
)
from dramamemory_data.normalization.text import clean, normalize_broadcaster, normalize_key

FORMAT = "dramamemory.drama.v1"
PARSER_VERSION = "dramamemory_json/1"


class RawPerson(BaseModel):
    external_id: str | None = None
    name_ko: str
    name_en: str | None = None
    birth_date: str | None = None


class RawCredit(BaseModel):
    person: RawPerson
    type: CreditType = "ACTOR"
    character: str | None = None
    billing_order: int | None = None
    main: bool = False


class RawArtist(BaseModel):
    external_id: str | None = None
    name: str
    role: ArtistRole = "PERFORMER"


class RawSong(BaseModel):
    external_id: str | None = None
    title: str
    artists: list[str | RawArtist] = Field(default_factory=list)
    release_date: str | None = None
    duration_seconds: int | None = None
    part_no: int | None = None
    track_no: int | None = None


class RawLink(BaseModel):
    provider: str
    url: str
    type: LinkType
    region: str = "KR"


class RawDramaV1(BaseModel):
    format: str
    external_id: str
    title_ko: str
    title_en: str | None = None
    aliases: list[str] = Field(default_factory=list)
    broadcaster: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    episode_count: int | None = None
    runtime_minutes: int | None = None
    synopsis: str | None = None
    official_page_url: str | None = None
    genres: list[str] = Field(default_factory=list)
    credits: list[RawCredit] = Field(default_factory=list)
    ost: list[RawSong] = Field(default_factory=list)
    links: list[RawLink] = Field(default_factory=list)


class DramaJsonParseError(ValueError):
    pass


def _date(value: str | None, field: str) -> date | None:
    try:
        return parse_date(value)
    except DateParseError as exc:
        raise DramaJsonParseError(f"{field}: {exc}") from exc


def _person(raw: RawPerson) -> NormalizedPerson:
    name_ko = clean(raw.name_ko)
    if not name_ko:
        raise DramaJsonParseError("credit person name_ko is empty")
    return NormalizedPerson(
        external_id=clean(raw.external_id),
        name_ko=name_ko,
        name_en=clean(raw.name_en),
        name_normalized=normalize_key(name_ko),
        birth_date=_date(raw.birth_date, "person.birth_date"),
    )


def _song(raw: RawSong) -> NormalizedSong:
    title = clean(raw.title)
    if not title:
        raise DramaJsonParseError("ost title is empty")
    artists: list[NormalizedSongArtist] = []
    for order, entry in enumerate(raw.artists, start=1):
        raw_artist = RawArtist(name=entry) if isinstance(entry, str) else entry
        name = clean(raw_artist.name)
        if not name:
            raise DramaJsonParseError(f"ost {title!r}: artist name is empty")
        artists.append(
            NormalizedSongArtist(
                artist=NormalizedArtist(
                    external_id=clean(raw_artist.external_id),
                    name=name,
                    name_normalized=normalize_key(name),
                ),
                role=raw_artist.role,
                sort_order=order,
            )
        )
    return NormalizedSong(
        external_id=clean(raw.external_id),
        title=title,
        title_normalized=normalize_key(title),
        release_date=_date(raw.release_date, "ost.release_date"),
        duration_seconds=raw.duration_seconds,
        artists=artists,
        part_no=raw.part_no,
        track_no=raw.track_no,
    )


def parse(body: bytes) -> NormalizedDrama:
    try:
        raw = RawDramaV1.model_validate(json.loads(body.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DramaJsonParseError(f"not valid UTF-8 JSON: {exc}") from exc
    except ValidationError as exc:
        raise DramaJsonParseError(f"schema violation: {exc.errors()[0]['msg']} at "
                                  f"{'.'.join(str(p) for p in exc.errors()[0]['loc'])}") from exc

    if raw.format != FORMAT:
        raise DramaJsonParseError(f"unsupported format {raw.format!r}, expected {FORMAT!r}")

    title_ko = clean(raw.title_ko)
    if not title_ko:
        raise DramaJsonParseError("title_ko is empty")

    aliases = [
        NormalizedAlias(alias=a, alias_normalized=normalize_key(a))
        for a in (clean(x) for x in raw.aliases)
        if a and normalize_key(a) != normalize_key(title_ko)
    ]

    return NormalizedDrama(
        external_id=raw.external_id.strip(),
        title_ko=title_ko,
        title_en=clean(raw.title_en),
        title_normalized=normalize_key(title_ko),
        aliases=aliases,
        broadcaster_code=normalize_broadcaster(raw.broadcaster) or None,
        start_date=_date(raw.start_date, "start_date"),
        end_date=_date(raw.end_date, "end_date"),
        episode_count=raw.episode_count,
        runtime_minutes=raw.runtime_minutes,
        synopsis=clean(raw.synopsis),
        official_page_url=clean(raw.official_page_url),
        genres=sorted({normalize_key(g) for g in raw.genres if normalize_key(g)}),
        credits=[
            NormalizedCredit(
                person=_person(c.person),
                credit_type=c.type,
                character_name=clean(c.character),
                billing_order=c.billing_order,
                is_main_cast=c.main,
            )
            for c in raw.credits
        ],
        osts=[_song(s) for s in raw.ost],
        links=[
            NormalizedLink(
                provider_code=normalize_key(link.provider),
                url=link.url.strip(),
                link_type=link.type,
                region_code=link.region.upper(),
            )
            for link in raw.links
        ],
    )
