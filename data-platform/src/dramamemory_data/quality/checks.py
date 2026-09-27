"""Per-record checks and the batch-level gate.

ERROR issues reject the record (status REJECTED). WARN issues are recorded but
the record still publishes. The batch gate blocks the whole publish when too
much of a batch is broken — that usually means a parser or source layout change,
not bad individual records.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from dramamemory_data.normalization.models import NormalizedDrama

Severity = Literal["ERROR", "WARN"]


@dataclass(frozen=True)
class Issue:
    code: str
    severity: Severity
    message: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def check_drama(
    drama: NormalizedDrama,
    *,
    known_broadcasters: set[str],
    known_genres: set[str],
) -> list[Issue]:
    issues: list[Issue] = []
    err = lambda code, msg: issues.append(Issue(code, "ERROR", msg))  # noqa: E731
    warn = lambda code, msg: issues.append(Issue(code, "WARN", msg))  # noqa: E731

    # Completeness
    if not drama.title_ko.strip():
        err("MISSING_TITLE", "title_ko is empty")
    if not drama.external_id.strip():
        err("MISSING_EXTERNAL_ID", "external_id is empty")
    if drama.start_date is None:
        warn("MISSING_START_DATE", "no start_date; year archive cannot place this drama")
    if not drama.credits:
        warn("NO_CREDITS", "no cast/crew credits")

    # Semantic rules
    if drama.start_date and drama.end_date and drama.start_date > drama.end_date:
        err("DATE_ORDER", f"start_date {drama.start_date} after end_date {drama.end_date}")
    if drama.episode_count is not None and drama.episode_count <= 0:
        err("EPISODE_COUNT", f"episode_count must be > 0, got {drama.episode_count}")
    if drama.runtime_minutes is not None and drama.runtime_minutes <= 0:
        err("RUNTIME", f"runtime_minutes must be > 0, got {drama.runtime_minutes}")

    # Referential (taxonomy) rules
    if drama.broadcaster_code and drama.broadcaster_code not in known_broadcasters:
        err("UNKNOWN_BROADCASTER", f"broadcaster {drama.broadcaster_code!r} not in canonical list")
    for genre in drama.genres:
        if genre not in known_genres:
            warn("UNKNOWN_GENRE", f"genre {genre!r} not in taxonomy; dropped")

    # Credits
    seen: set[tuple[str, str, str | None]] = set()
    for credit in drama.credits:
        if not credit.person.name_ko.strip():
            err("CREDIT_NO_NAME", "credit without person name")
        key = (credit.person.name_normalized, credit.credit_type, credit.character_name)
        if key in seen:
            warn("DUPLICATE_CREDIT", f"duplicate credit {key}")
        seen.add(key)
        if credit.billing_order is not None and credit.billing_order <= 0:
            err("BILLING_ORDER", f"billing_order must be > 0, got {credit.billing_order}")

    # OST
    for song in drama.osts:
        if not song.title.strip():
            err("SONG_NO_TITLE", "OST entry without title")
        if song.duration_seconds is not None and song.duration_seconds <= 0:
            err("SONG_DURATION", f"duration_seconds must be > 0 for {song.title!r}")

    # Official links only, and only over https
    for link in drama.links:
        if not link.url.startswith("https://"):
            err("LINK_NOT_HTTPS", f"link must be https: {link.url}")

    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity == "ERROR" for i in issues)


class QualityGateError(RuntimeError):
    pass


def gate_batch(
    results: list[tuple[int, list[Issue]]],
    *,
    min_batch_size: int = 5,
    max_error_ratio: float = 0.5,
) -> None:
    """Raise when a large share of the batch is broken. Small batches never trip the gate."""
    if len(results) < min_batch_size:
        return
    errors = sum(1 for _, issues in results if has_errors(issues))
    ratio = errors / len(results)
    if ratio > max_error_ratio:
        raise QualityGateError(
            f"{errors}/{len(results)} records rejected ({ratio:.0%} > {max_error_ratio:.0%}); "
            "blocking gold publish — check parser/source changes"
        )
