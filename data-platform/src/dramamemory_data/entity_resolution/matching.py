"""Match rules — docs/DATA_MODEL.md §9, docs/AIRFLOW_DAGS.md §7.

Decision thresholds (initial hypothesis, tune against a validation set):

    >= 0.97        AUTO_MERGE
    0.80 ~ 0.97    REVIEW
    < 0.80         CREATE_NEW   (or REVIEW when candidates exist but conflict)

Deterministic signals (external id seen before, same person already credited in
this drama) short-circuit to 1.0. Name-only matches never auto-merge.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Literal, Protocol

from dramamemory_data.normalization.models import (
    NormalizedArtist,
    NormalizedDrama,
    NormalizedPerson,
    NormalizedSong,
)

Decision = Literal["AUTO_MERGE", "REVIEW", "CREATE_NEW"]
Method = Literal["EXTERNAL_ID", "DETERMINISTIC", "SCORED", "NONE"]

AUTO_THRESHOLD = 0.97
REVIEW_THRESHOLD = 0.80


@dataclass(frozen=True)
class DramaCandidate:
    id: int
    title_normalized: str
    broadcaster_code: str | None
    start_year: int | None


@dataclass(frozen=True)
class PersonCandidate:
    id: int
    name_normalized: str
    birth_date: date | None
    drama_ids: frozenset[int] = frozenset()


@dataclass(frozen=True)
class SongCandidate:
    id: int
    title_normalized: str
    artist_names: frozenset[str] = frozenset()
    drama_ids: frozenset[int] = frozenset()


class Repo(Protocol):
    def mapped_canonical_id(
        self, source_id: int, canonical_type: str, external_ref: str
    ) -> int | None: ...
    def dramas_by_title(self, title_normalized: str) -> list[DramaCandidate]: ...
    def persons_by_name(self, name_normalized: str) -> list[PersonCandidate]: ...
    def songs_by_title(self, title_normalized: str) -> list[SongCandidate]: ...
    def artist_by_name(self, name_normalized: str) -> int | None: ...


@dataclass(frozen=True)
class Match:
    decision: Decision
    canonical_id: int | None
    method: Method
    confidence: float
    signals: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _decide(score: float) -> Decision:
    if score >= AUTO_THRESHOLD:
        return "AUTO_MERGE"
    if score >= REVIEW_THRESHOLD:
        return "REVIEW"
    return "CREATE_NEW"


CREATE_NEW = Match("CREATE_NEW", None, "NONE", 0.0)


def _by_external_ref(
    repo: Repo, source_id: int, canonical_type: str, ref: str | None
) -> Match | None:
    if not ref:
        return None
    canonical_id = repo.mapped_canonical_id(source_id, canonical_type, ref)
    if canonical_id is None:
        return None
    return Match("AUTO_MERGE", canonical_id, "EXTERNAL_ID", 1.0, {"external_ref": ref})


# ---------------------------------------------------------------------------
# Drama
# ---------------------------------------------------------------------------
def resolve_drama(drama: NormalizedDrama, source_id: int, repo: Repo) -> Match:
    if m := _by_external_ref(repo, source_id, "DRAMA", drama.external_id):
        return m

    candidates = repo.dramas_by_title(drama.title_normalized)
    for alias in drama.aliases:
        candidates += [
            c for c in repo.dramas_by_title(alias.alias_normalized) if c not in candidates
        ]
    if not candidates:
        return CREATE_NEW

    scored: list[tuple[float, DramaCandidate, dict[str, Any]]] = []
    for c in candidates:
        signals: dict[str, Any] = {"title": 1.0}
        if drama.broadcaster_code and c.broadcaster_code:
            signals["broadcaster"] = 1.0 if drama.broadcaster_code == c.broadcaster_code else 0.0
        if drama.start_year and c.start_year:
            signals["start_year"] = 1.0 if drama.start_year == c.start_year else 0.0
        if signals.get("broadcaster") == 0.0 or signals.get("start_year") == 0.0:
            continue  # same title, different broadcaster/year: a remake, not a match
        known = [k for k in ("broadcaster", "start_year") if k in signals]
        score = {2: 1.0, 1: 0.9, 0: 0.8}[len(known)]
        scored.append((score, c, signals))

    if not scored:
        return Match("CREATE_NEW", None, "SCORED", 0.5, {"conflicting_candidates": len(candidates)})

    scored.sort(key=lambda t: -t[0])
    score, best, signals = scored[0]
    if len(scored) > 1 and scored[1][0] == score:
        return Match(
            "REVIEW", best.id, "SCORED", min(score, 0.9), {**signals, "ambiguous": len(scored)}
        )
    method: Method = "DETERMINISTIC" if score == 1.0 else "SCORED"
    return Match(_decide(score), best.id, method, score, signals)


# ---------------------------------------------------------------------------
# Person
# ---------------------------------------------------------------------------
def resolve_person(
    person: NormalizedPerson, source_id: int, repo: Repo, drama_id: int | None
) -> Match:
    if m := _by_external_ref(repo, source_id, "PERSON", person.external_id):
        return m

    candidates = repo.persons_by_name(person.name_normalized)
    if not candidates:
        return CREATE_NEW

    if drama_id is not None:
        credited = [c for c in candidates if drama_id in c.drama_ids]
        if len(credited) == 1:
            return Match(
                "AUTO_MERGE",
                credited[0].id,
                "DETERMINISTIC",
                1.0,
                {"name": 1.0, "same_drama_credit": 1.0},
            )

    if person.birth_date:
        same_birth = [c for c in candidates if c.birth_date == person.birth_date]
        if len(same_birth) == 1:
            return Match(
                "AUTO_MERGE", same_birth[0].id, "SCORED", 0.98, {"name": 1.0, "birth_date": 1.0}
            )
        if len(same_birth) > 1:
            return Match(
                "REVIEW",
                same_birth[0].id,
                "SCORED",
                0.9,
                {"name": 1.0, "birth_date": 1.0, "ambiguous": len(same_birth)},
            )
        # every candidate with a known birth date disagrees
        unknown_birth = [c for c in candidates if c.birth_date is None]
        if not unknown_birth:
            return Match("CREATE_NEW", None, "SCORED", 0.3, {"name": 1.0, "birth_date": 0.0})
        candidates = unknown_birth

    if len(candidates) == 1:
        return Match("REVIEW", candidates[0].id, "SCORED", 0.85, {"name": 1.0, "birth_date": None})
    return Match(
        "REVIEW", candidates[0].id, "SCORED", 0.8, {"name": 1.0, "ambiguous": len(candidates)}
    )


# ---------------------------------------------------------------------------
# Song / Artist
# ---------------------------------------------------------------------------
def resolve_song(song: NormalizedSong, source_id: int, repo: Repo, drama_id: int | None) -> Match:
    if m := _by_external_ref(repo, source_id, "SONG", song.external_id):
        return m

    candidates = repo.songs_by_title(song.title_normalized)
    if not candidates:
        return CREATE_NEW

    if drama_id is not None:
        in_drama = [c for c in candidates if drama_id in c.drama_ids]
        if len(in_drama) == 1:
            return Match(
                "AUTO_MERGE",
                in_drama[0].id,
                "DETERMINISTIC",
                1.0,
                {"title": 1.0, "same_drama": 1.0},
            )

    names = {a.artist.name_normalized for a in song.artists}
    if names:
        shared = [c for c in candidates if c.artist_names & names]
        if len(shared) == 1:
            return Match("AUTO_MERGE", shared[0].id, "SCORED", 0.98, {"title": 1.0, "artist": 1.0})
        if len(shared) > 1:
            return Match(
                "REVIEW",
                shared[0].id,
                "SCORED",
                0.9,
                {"title": 1.0, "artist": 1.0, "ambiguous": len(shared)},
            )
    # Same title, different (or unknown) artist: a different song.
    return Match("CREATE_NEW", None, "SCORED", 0.4, {"title": 1.0, "artist": 0.0})


def resolve_artist(artist: NormalizedArtist, source_id: int, repo: Repo) -> Match:
    if m := _by_external_ref(repo, source_id, "ARTIST", artist.external_id):
        return m
    artist_id = repo.artist_by_name(artist.name_normalized)
    if artist_id is None:
        return CREATE_NEW
    return Match("AUTO_MERGE", artist_id, "DETERMINISTIC", 1.0, {"name": 1.0})


# ---------------------------------------------------------------------------
# Whole record
# ---------------------------------------------------------------------------
def person_key(p: NormalizedPerson) -> str:
    return p.external_id or f"name:{p.name_normalized}"


def song_key(s: NormalizedSong) -> str:
    return s.external_id or f"title:{s.title_normalized}"


def artist_key(a: NormalizedArtist) -> str:
    return a.external_id or f"name:{a.name_normalized}"


def resolve_record(drama: NormalizedDrama, source_id: int, repo: Repo) -> dict[str, Any]:
    """Resolve a drama and everything nested in it.

    The result is stored as staging_record.resolution.
    """
    drama_match = resolve_drama(drama, source_id, repo)
    drama_id = drama_match.canonical_id if drama_match.decision == "AUTO_MERGE" else None

    persons = {
        person_key(c.person): resolve_person(c.person, source_id, repo, drama_id).as_dict()
        for c in drama.credits
    }
    songs: dict[str, Any] = {}
    artists: dict[str, Any] = {}
    for song in drama.osts:
        songs[song_key(song)] = resolve_song(song, source_id, repo, drama_id).as_dict()
        for sa in song.artists:
            artists.setdefault(
                artist_key(sa.artist), resolve_artist(sa.artist, source_id, repo).as_dict()
            )

    all_matches = [drama_match.as_dict(), *persons.values(), *songs.values(), *artists.values()]
    return {
        "drama": drama_match.as_dict(),
        "persons": persons,
        "songs": songs,
        "artists": artists,
        "needs_review": any(m["decision"] == "REVIEW" for m in all_matches),
    }
