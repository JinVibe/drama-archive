from datetime import date

import pytest

from dramamemory_data.normalization.models import (
    NormalizedCredit,
    NormalizedDrama,
    NormalizedLink,
    NormalizedPerson,
)
from dramamemory_data.quality.checks import (
    Issue,
    QualityGateError,
    check_drama,
    gate_batch,
    has_errors,
)

BROADCASTERS = {"tvn", "kbs"}
GENRES = {"romance", "fantasy"}


def _drama(**kw) -> NormalizedDrama:
    base = dict(
        external_id="x",
        title_ko="도깨비",
        title_normalized="도깨비",
        broadcaster_code="tvn",
        start_date=date(2016, 12, 2),
        end_date=date(2017, 1, 21),
        episode_count=16,
        credits=[
            NormalizedCredit(
                person=NormalizedPerson(name_ko="공유", name_normalized="공유"), credit_type="ACTOR"
            )
        ],
    )
    base.update(kw)
    return NormalizedDrama(**base)


def _codes(issues):
    return sorted(i.code for i in issues)


def test_clean_record_has_no_issues():
    assert check_drama(_drama(), known_broadcasters=BROADCASTERS, known_genres=GENRES) == []


@pytest.mark.parametrize(
    ("kw", "code"),
    [
        ({"start_date": date(2017, 1, 1), "end_date": date(2016, 1, 1)}, "DATE_ORDER"),
        ({"episode_count": 0}, "EPISODE_COUNT"),
        ({"runtime_minutes": -5}, "RUNTIME"),
        (
            {"links": [NormalizedLink(provider_code="x", url="http://x", link_type="OTT_DETAIL")]},
            "LINK_NOT_HTTPS",
        ),
    ],
)
def test_error_rules(kw, code):
    issues = check_drama(_drama(**kw), known_broadcasters=BROADCASTERS, known_genres=GENRES)
    assert code in _codes(issues)
    assert has_errors(issues)


def test_warn_rules_do_not_reject():
    issues = check_drama(
        _drama(genres=["romance", "isekai"], start_date=None, credits=[], broadcaster_code="hbo"),
        known_broadcasters=BROADCASTERS,
        known_genres=GENRES,
    )
    assert _codes(issues) == [
        "MISSING_START_DATE",
        "NO_CREDITS",
        "UNKNOWN_BROADCASTER",
        "UNKNOWN_GENRE",
    ]
    assert not has_errors(issues)


def test_gate_ignores_small_batches():
    bad = [Issue("X", "ERROR", "")]
    gate_batch([(1, bad), (2, bad), (3, bad)])  # 100% broken but < min_batch_size


def test_gate_blocks_mostly_broken_batch():
    bad, ok = [Issue("X", "ERROR", "")], []
    with pytest.raises(QualityGateError, match="blocking gold publish"):
        gate_batch([(1, bad), (2, bad), (3, bad), (4, bad), (5, ok)])
    gate_batch([(1, bad), (2, bad), (3, ok), (4, ok), (5, ok)])  # 40% is under the limit
