"""Silver-layer record models. This is the JSON stored in staging_record.payload.

Everything a source can tell us about one drama, already normalized, with no
canonical IDs yet — entity resolution assigns those.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

CreditType = Literal["ACTOR", "DIRECTOR", "WRITER", "PRODUCER"]
ArtistRole = Literal["PERFORMER", "COMPOSER", "LYRICIST", "FEATURING"]
LinkType = Literal[
    "OFFICIAL_VOD", "BROADCASTER_PAGE", "OTT_DETAIL", "OFFICIAL_CLIP", "OFFICIAL_OST"
]


class NormalizedPerson(BaseModel):
    external_id: str | None = None
    name_ko: str
    name_en: str | None = None
    name_normalized: str
    birth_date: date | None = None


class NormalizedCredit(BaseModel):
    person: NormalizedPerson
    credit_type: CreditType
    character_name: str | None = None
    billing_order: int | None = None
    is_main_cast: bool = False


class NormalizedArtist(BaseModel):
    external_id: str | None = None
    name: str
    name_normalized: str


class NormalizedSongArtist(BaseModel):
    artist: NormalizedArtist
    role: ArtistRole = "PERFORMER"
    sort_order: int


class NormalizedSong(BaseModel):
    external_id: str | None = None
    title: str
    title_normalized: str
    release_date: date | None = None
    duration_seconds: int | None = None
    artists: list[NormalizedSongArtist] = Field(default_factory=list)
    part_no: int | None = None
    track_no: int | None = None


class NormalizedAlias(BaseModel):
    alias: str
    alias_normalized: str
    language_code: str | None = None
    alias_type: str | None = None


class NormalizedLink(BaseModel):
    provider_code: str
    url: str
    link_type: LinkType
    region_code: str = "KR"


class NormalizedDrama(BaseModel):
    external_id: str
    title_ko: str
    title_en: str | None = None
    title_normalized: str
    aliases: list[NormalizedAlias] = Field(default_factory=list)
    broadcaster_code: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    episode_count: int | None = None
    runtime_minutes: int | None = None
    synopsis: str | None = None
    official_page_url: str | None = None
    genres: list[str] = Field(default_factory=list)
    credits: list[NormalizedCredit] = Field(default_factory=list)
    osts: list[NormalizedSong] = Field(default_factory=list)
    links: list[NormalizedLink] = Field(default_factory=list)
    # normalization.program_kind: sources whose classes mix variety/reality shows in
    # with dramas set this; the quality gate rejects NOT_DRAMA.
    program_kind: Literal["DRAMA", "NOT_DRAMA", "UNKNOWN"] = "DRAMA"

    @property
    def start_year(self) -> int | None:
        return self.start_date.year if self.start_date else None
