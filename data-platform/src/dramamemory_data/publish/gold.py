"""Publish one resolved staging record into the canonical schema — docs/AIRFLOW_DAGS.md §9.

Runs inside a single transaction owned by the caller:

    create/update canonical rows
    write provenance (source_entity_map with external_ref)
    increment canonical_version
    insert outbox event

Entities the resolver marked CREATE_NEW get one last deterministic lookup right
before insert, because an earlier record in the same batch may have created them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from dramamemory_data.entity_resolution import matching
from dramamemory_data.entity_resolution.repo import PostgresRepo
from dramamemory_data.normalization.models import (
    NormalizedArtist,
    NormalizedDrama,
    NormalizedPerson,
    NormalizedSong,
)
from dramamemory_data.normalization.text import slugify


@dataclass
class PublishResult:
    drama_id: int
    created: bool
    persons: dict[str, int] = field(default_factory=dict)
    songs: dict[str, int] = field(default_factory=dict)
    artists: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _one(cur, sql: str, params: tuple) -> Any:
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else None


def unique_slug(cur, base: str, year: int | None, table: str) -> str:
    """base, base-year, base-year-2, ... until free."""
    candidates = [base]
    if year:
        candidates.append(f"{base}-{year}")
    for candidate in candidates:
        if _one(cur, f"SELECT 1 FROM {table} WHERE slug = %s", (candidate,)) is None:
            return candidate
    stem = candidates[-1]
    n = 2
    while _one(cur, f"SELECT 1 FROM {table} WHERE slug = %s", (f"{stem}-{n}",)) is not None:
        n += 1
    return f"{stem}-{n}"


def _map(
    cur,
    *,
    source_record_id: int,
    canonical_type: str,
    canonical_id: int,
    external_ref: str | None,
    match: dict[str, Any],
) -> None:
    cur.execute(
        """
        INSERT INTO source_entity_map
            (source_record_id, canonical_type, canonical_id, match_method, decision,
             confidence, external_ref)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            source_record_id,
            canonical_type,
            canonical_id,
            match.get("method", "NONE"),
            match.get("decision", "CREATE_NEW"),
            match.get("confidence"),
            external_ref,
        ),
    )


# ---------------------------------------------------------------------------
# drama
# ---------------------------------------------------------------------------
def _broadcaster_id(cur, code: str | None) -> int | None:
    if not code:
        return None
    return _one(cur, "SELECT id FROM broadcaster WHERE code = %s", (code,))


def upsert_drama(cur, drama: NormalizedDrama, match: dict[str, Any]) -> tuple[int, bool]:
    broadcaster_id = _broadcaster_id(cur, drama.broadcaster_code)
    if match["decision"] == "AUTO_MERGE" and match.get("canonical_id"):
        drama_id = int(match["canonical_id"])
        # Single-source for now: non-null incoming fields win. Multi-source trust
        # resolution (source.trust_level) comes with the second source.
        cur.execute(
            """
            UPDATE drama SET
                title_ko = %s, title_en = COALESCE(%s, title_en), title_normalized = %s,
                broadcaster_id = COALESCE(%s, broadcaster_id),
                start_date = COALESCE(%s, start_date), end_date = COALESCE(%s, end_date),
                episode_count = COALESCE(%s, episode_count),
                runtime_minutes = COALESCE(%s, runtime_minutes),
                synopsis = COALESCE(%s, synopsis),
                official_page_url = COALESCE(%s, official_page_url),
                canonical_version = canonical_version + 1
            WHERE id = %s
            """,
            (
                drama.title_ko,
                drama.title_en,
                drama.title_normalized,
                broadcaster_id,
                drama.start_date,
                drama.end_date,
                drama.episode_count,
                drama.runtime_minutes,
                drama.synopsis,
                drama.official_page_url,
                drama_id,
            ),
        )
        return drama_id, False

    slug = unique_slug(cur, slugify(drama.title_en or drama.title_ko), drama.start_year, "drama")
    drama_id = _one(
        cur,
        """
        INSERT INTO drama (slug, title_ko, title_en, title_normalized, broadcaster_id,
                           start_date, end_date, episode_count, runtime_minutes, synopsis,
                           official_page_url)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            slug,
            drama.title_ko,
            drama.title_en,
            drama.title_normalized,
            broadcaster_id,
            drama.start_date,
            drama.end_date,
            drama.episode_count,
            drama.runtime_minutes,
            drama.synopsis,
            drama.official_page_url,
        ),
    )
    return int(drama_id), True


def sync_aliases_and_genres(
    cur, drama_id: int, drama: NormalizedDrama, known_genres: set[str]
) -> None:
    for alias in drama.aliases:
        if not alias.alias_normalized:
            continue
        cur.execute(
            """
            INSERT INTO drama_alias (drama_id, alias, alias_normalized, language_code, alias_type)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (drama_id, alias_normalized) DO NOTHING
            """,
            (drama_id, alias.alias, alias.alias_normalized, alias.language_code, alias.alias_type),
        )
    genres = [g for g in drama.genres if g in known_genres]
    cur.execute("DELETE FROM drama_genre WHERE drama_id = %s", (drama_id,))
    for code in genres:
        cur.execute(
            """
            INSERT INTO drama_genre (drama_id, genre_id)
            SELECT %s, id FROM genre WHERE code = %s
            ON CONFLICT DO NOTHING
            """,
            (drama_id, code),
        )


# ---------------------------------------------------------------------------
# person / credit
# ---------------------------------------------------------------------------
def ensure_person(
    cur, person: NormalizedPerson, match: dict[str, Any], *, source_id: int, drama_id: int
) -> int:
    if match["decision"] == "AUTO_MERGE" and match.get("canonical_id"):
        return int(match["canonical_id"])
    # Last-moment lookup: an earlier record in this batch may have created them.
    late = matching.resolve_person(person, source_id, PostgresRepo(cur), drama_id)
    if late.decision == "AUTO_MERGE" and late.canonical_id:
        match.update(late.as_dict())
        return late.canonical_id
    slug = unique_slug(cur, slugify(person.name_en or person.name_ko), None, "person")
    person_id = _one(
        cur,
        """
        INSERT INTO person (slug, name_ko, name_en, name_normalized, birth_date)
        VALUES (%s, %s, %s, %s, %s) RETURNING id
        """,
        (slug, person.name_ko, person.name_en, person.name_normalized, person.birth_date),
    )
    return int(person_id)


def upsert_credit(cur, drama_id: int, person_id: int, credit) -> None:
    cur.execute(
        """
        INSERT INTO credit (drama_id, person_id, credit_type, character_name, billing_order,
                            is_main_cast)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (drama_id, person_id, credit_type, character_name) DO UPDATE SET
            billing_order = EXCLUDED.billing_order,
            is_main_cast  = EXCLUDED.is_main_cast
        """,
        (
            drama_id,
            person_id,
            credit.credit_type,
            credit.character_name,
            credit.billing_order,
            credit.is_main_cast,
        ),
    )


# ---------------------------------------------------------------------------
# song / artist / ost
# ---------------------------------------------------------------------------
def ensure_artist(cur, artist: NormalizedArtist, match: dict[str, Any], *, source_id: int) -> int:
    if match["decision"] == "AUTO_MERGE" and match.get("canonical_id"):
        return int(match["canonical_id"])
    artist_id = _one(
        cur,
        """
        INSERT INTO artist (name, name_normalized) VALUES (%s, %s)
        ON CONFLICT (name_normalized) DO UPDATE SET name = artist.name
        RETURNING id
        """,
        (artist.name, artist.name_normalized),
    )
    return int(artist_id)


def ensure_song(
    cur, song: NormalizedSong, match: dict[str, Any], *, source_id: int, drama_id: int
) -> int:
    if match["decision"] == "AUTO_MERGE" and match.get("canonical_id"):
        return int(match["canonical_id"])
    late = matching.resolve_song(song, source_id, PostgresRepo(cur), drama_id)
    if late.decision == "AUTO_MERGE" and late.canonical_id:
        match.update(late.as_dict())
        return late.canonical_id
    song_id = _one(
        cur,
        """
        INSERT INTO song (title, title_normalized, release_date, duration_seconds)
        VALUES (%s, %s, %s, %s) RETURNING id
        """,
        (song.title, song.title_normalized, song.release_date, song.duration_seconds),
    )
    return int(song_id)


def link_song_artist(cur, song_id: int, artist_id: int, role: str, sort_order: int) -> None:
    cur.execute(
        """
        INSERT INTO song_artist (song_id, artist_id, role, sort_order)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (song_id, artist_id, role) DO UPDATE SET sort_order = EXCLUDED.sort_order
        """,
        (song_id, artist_id, role, sort_order),
    )


def upsert_drama_ost(cur, drama_id: int, song_id: int, song: NormalizedSong) -> None:
    cur.execute(
        """
        INSERT INTO drama_ost (drama_id, song_id, part_no, track_no)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (drama_id, song_id) DO UPDATE SET
            part_no = EXCLUDED.part_no, track_no = EXCLUDED.track_no
        """,
        (drama_id, song_id, song.part_no, song.track_no),
    )


def upsert_links(cur, drama_id: int, drama: NormalizedDrama, source_record_id: int) -> None:
    for link in drama.links:
        cur.execute(
            """
            INSERT INTO streaming_link (drama_id, provider_code, url, link_type, region_code,
                                        source_record_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (drama_id, provider_code, url) DO UPDATE SET
                link_type = EXCLUDED.link_type,
                region_code = EXCLUDED.region_code,
                source_record_id = EXCLUDED.source_record_id
            """,
            (
                drama_id,
                link.provider_code,
                link.url,
                link.link_type,
                link.region_code,
                source_record_id,
            ),
        )


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def publish_record(
    cur,
    *,
    drama: NormalizedDrama,
    resolution: dict[str, Any],
    source_id: int,
    source_record_id: int,
    known_genres: set[str],
) -> PublishResult:
    drama_match = dict(resolution["drama"])
    drama_id, created = upsert_drama(cur, drama, drama_match)
    result = PublishResult(drama_id=drama_id, created=created)
    _map(
        cur,
        source_record_id=source_record_id,
        canonical_type="DRAMA",
        canonical_id=drama_id,
        external_ref=drama.external_id,
        match=drama_match,
    )

    sync_aliases_and_genres(cur, drama_id, drama, known_genres)

    for credit in drama.credits:
        key = matching.person_key(credit.person)
        match = dict(resolution["persons"].get(key, matching.CREATE_NEW.as_dict()))
        if key not in result.persons:
            person_id = ensure_person(
                cur, credit.person, match, source_id=source_id, drama_id=drama_id
            )
            result.persons[key] = person_id
            _map(
                cur,
                source_record_id=source_record_id,
                canonical_type="PERSON",
                canonical_id=person_id,
                external_ref=credit.person.external_id,
                match=match,
            )
        upsert_credit(cur, drama_id, result.persons[key], credit)

    for song in drama.osts:
        skey = matching.song_key(song)
        smatch = dict(resolution["songs"].get(skey, matching.CREATE_NEW.as_dict()))
        song_id = ensure_song(cur, song, smatch, source_id=source_id, drama_id=drama_id)
        result.songs[skey] = song_id
        _map(
            cur,
            source_record_id=source_record_id,
            canonical_type="SONG",
            canonical_id=song_id,
            external_ref=song.external_id,
            match=smatch,
        )
        upsert_drama_ost(cur, drama_id, song_id, song)
        for sa in song.artists:
            akey = matching.artist_key(sa.artist)
            if akey not in result.artists:
                amatch = dict(resolution["artists"].get(akey, matching.CREATE_NEW.as_dict()))
                artist_id = ensure_artist(cur, sa.artist, amatch, source_id=source_id)
                result.artists[akey] = artist_id
                _map(
                    cur,
                    source_record_id=source_record_id,
                    canonical_type="ARTIST",
                    canonical_id=artist_id,
                    external_ref=sa.artist.external_id,
                    match=amatch,
                )
            link_song_artist(cur, song_id, result.artists[akey], sa.role, sa.sort_order)

    upsert_links(cur, drama_id, drama, source_record_id)

    cur.execute(
        """
        INSERT INTO outbox_event (aggregate_type, aggregate_id, event_type, payload)
        VALUES ('DRAMA', %s, %s, %s::jsonb)
        """,
        (
            str(drama_id),
            "DRAMA_CANONICAL_CREATED" if created else "DRAMA_CANONICAL_UPDATED",
            json.dumps(
                {
                    "drama_id": drama_id,
                    "source_record_id": source_record_id,
                    "person_ids": sorted(set(result.persons.values())),
                    "song_ids": sorted(set(result.songs.values())),
                }
            ),
        ),
    )
    return result


def set_drama_status(
    cur,
    *,
    source_code: str,
    external_refs: list[str],
    status: str,
    reason: str | dict[str, str],
    only_reasons: list[str] | None = None,
) -> int:
    """Move the dramas a source maps to `external_refs` into `status` (HIDDEN or
    PUBLISHED), bumping canonical_version and writing one outbox event per row, so
    search/graph projections drop or restore them. Rows already in `status` are
    untouched; MERGED/DEPRECATED rows are never changed. Hiding records the reason
    in drama.hidden_reason; restoring only touches rows hidden for `only_reasons`
    (never a row hidden by hand). Returns the row count."""
    if not external_refs or status not in ("HIDDEN", "PUBLISHED"):
        return 0
    from_status = "PUBLISHED" if status == "HIDDEN" else "HIDDEN"
    cur.execute(
        """
        WITH target AS (
            SELECT DISTINCT d.id, m.external_ref
            FROM drama d
            JOIN source_entity_map m ON m.canonical_type = 'DRAMA' AND m.canonical_id = d.id
            JOIN source_record r ON r.id = m.source_record_id
            JOIN source s ON s.id = r.source_id
            WHERE s.code = %s AND m.external_ref = ANY(%s) AND d.status = %s
              AND (%s::text[] IS NULL OR d.hidden_reason = ANY(%s::text[]))
        )
        UPDATE drama d
        SET status = %s, canonical_version = canonical_version + 1, updated_at = now(),
            hidden_reason = CASE WHEN %s = 'HIDDEN' THEN %s::jsonb ->> t.external_ref ELSE NULL END
        FROM target t
        WHERE d.id = t.id
        RETURNING d.id, t.external_ref
        """,
        (
            source_code, external_refs, from_status, only_reasons, only_reasons, status, status,
            json.dumps(
                reason if isinstance(reason, dict) else dict.fromkeys(external_refs, reason)
            ),
        ),
    )
    rows = cur.fetchall()
    for drama_id, external_ref in rows:
        _status_event(
            cur, drama_id, status,
            {
                "source_code": source_code,
                "external_ref": external_ref,
                "reason": reason.get(external_ref) if isinstance(reason, dict) else reason,
            },
        )
    return len(rows)


def hide_upcoming(cur) -> tuple[int, int]:
    """Dramas that have not started airing are not part of the archive: PUBLISHED with
    a future start_date -> HIDDEN ('upcoming'); the day they air they come back.
    Returns (hidden, restored)."""
    cur.execute(
        """
        UPDATE drama
        SET status = 'HIDDEN', hidden_reason = 'upcoming',
            canonical_version = canonical_version + 1, updated_at = now()
        WHERE status = 'PUBLISHED' AND start_date > CURRENT_DATE
        RETURNING id, start_date::text
        """
    )
    hidden = cur.fetchall()
    for drama_id, start in hidden:
        _status_event(cur, drama_id, "HIDDEN", {"reason": "upcoming", "start_date": start})
    cur.execute(
        """
        UPDATE drama
        SET status = 'PUBLISHED', hidden_reason = NULL,
            canonical_version = canonical_version + 1, updated_at = now()
        WHERE status = 'HIDDEN' AND hidden_reason = 'upcoming' AND start_date <= CURRENT_DATE
        RETURNING id, start_date::text
        """
    )
    restored = cur.fetchall()
    for drama_id, start in restored:
        _status_event(cur, drama_id, "PUBLISHED", {"reason": "aired", "start_date": start})
    return len(hidden), len(restored)


def apply_scope(cur, broadcaster_codes: list[str]) -> tuple[int, int]:
    """The archive covers a fixed set of channels for now (product decision, 2026-09-28:
    KBS, MBC, SBS, tvN, JTBC — platforms mostly re-run what those aired). PUBLISHED
    dramas on another channel, or with no channel, -> HIDDEN ('out_of_scope');
    when the scope widens or a channel gets inferred, they come back.
    Returns (hidden, restored)."""
    cur.execute(
        """
        UPDATE drama d
        SET status = 'HIDDEN', hidden_reason = 'out_of_scope',
            canonical_version = canonical_version + 1, updated_at = now()
        FROM (SELECT d2.id, b.code
                FROM drama d2 LEFT JOIN broadcaster b ON b.id = d2.broadcaster_id
               WHERE d2.status = 'PUBLISHED'
                 AND (b.code IS NULL OR NOT (b.code = ANY(%s)))) x
        WHERE d.id = x.id
        RETURNING d.id, x.code
        """,
        (broadcaster_codes,),
    )
    hidden = cur.fetchall()
    for drama_id, code in hidden:
        _status_event(cur, drama_id, "HIDDEN", {"reason": "out_of_scope", "broadcaster": code})
    cur.execute(
        """
        UPDATE drama d
        SET status = 'PUBLISHED', hidden_reason = NULL,
            canonical_version = canonical_version + 1, updated_at = now()
        FROM broadcaster b
        WHERE b.id = d.broadcaster_id AND b.code = ANY(%s)
          AND d.status = 'HIDDEN' AND d.hidden_reason = 'out_of_scope'
          AND (d.start_date IS NULL OR d.start_date <= CURRENT_DATE)
        RETURNING d.id, b.code
        """,
        (broadcaster_codes,),
    )
    restored = cur.fetchall()
    for drama_id, code in restored:
        _status_event(cur, drama_id, "PUBLISHED", {"reason": "in_scope", "broadcaster": code})
    return len(hidden), len(restored)


def _status_event(cur, drama_id: int, status: str, payload: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO outbox_event (aggregate_type, aggregate_id, event_type, payload)
        VALUES ('DRAMA', %s, %s, %s::jsonb)
        """,
        (
            str(drama_id),
            "DRAMA_HIDDEN" if status == "HIDDEN" else "DRAMA_RESTORED",
            json.dumps({"drama_id": drama_id, **payload}),
        ),
    )
