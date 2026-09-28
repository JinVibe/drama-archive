from datetime import date

from dramamemory_data.entity_resolution.matching import (
    DramaCandidate,
    PersonCandidate,
    SongCandidate,
    resolve_artist,
    resolve_drama,
    resolve_person,
    resolve_record,
    resolve_song,
)
from dramamemory_data.normalization.models import (
    NormalizedArtist,
    NormalizedCredit,
    NormalizedDrama,
    NormalizedPerson,
    NormalizedSong,
    NormalizedSongArtist,
)


class FakeRepo:
    def __init__(self, *, mapped=None, dramas=None, persons=None, songs=None, artists=None):
        self.mapped = mapped or {}
        self.dramas = dramas or {}
        self.persons = persons or {}
        self.songs = songs or {}
        self.artists = artists or {}

    def mapped_canonical_id(self, source_id, canonical_type, external_ref):
        return self.mapped.get((source_id, canonical_type, external_ref))

    def dramas_by_title(self, t, source_id=None):
        return list(self.dramas.get(t, []))

    def persons_by_name(self, n, source_id=None):
        return list(self.persons.get(n, []))

    def songs_by_title(self, t):
        return list(self.songs.get(t, []))

    def artist_by_name(self, n):
        return self.artists.get(n)


def test_candidate_known_under_another_id_of_the_same_source_is_a_different_entity():
    # 박소현 the actress (Q6783618) is already mapped; the director 박소현 arrives as
    # Q109120194 with no birth date: name-only match must not open a review.
    actress = PersonCandidate(
        971, "박소현", date(1971, 2, 11), external_refs=frozenset({"Q6783618"})
    )
    repo = FakeRepo(persons={"박소현": [actress]})
    director = NormalizedPerson(
        external_id="Q109120194", name_ko="박소현", name_normalized="박소현"
    )
    m = resolve_person(director, 1, repo, None)
    assert m.decision == "CREATE_NEW" and m.canonical_id is None
    # without any external id on the candidate the old name-only rule still applies
    plain = PersonCandidate(971, "박소현", None)
    assert (
        resolve_person(director, 1, FakeRepo(persons={"박소현": [plain]}), None).decision
        == "REVIEW"
    )
    # same for dramas: 연애시대 (SBS 2006, Q97971216) vs a new item Q623446 with the same title
    sbs = DramaCandidate(1661, "연애시대", "sbs", 2006, external_refs=frozenset({"Q97971216"}))
    other = _drama(
        external_id="Q623446",
        title_ko="연애시대",
        title_normalized="연애시대",
        broadcaster_code=None,
        start_date=None,
    )
    assert resolve_drama(other, 1, FakeRepo(dramas={"연애시대": [sbs]})).decision == "CREATE_NEW"


def _drama(**kw) -> NormalizedDrama:
    base = dict(
        external_id="x",
        title_ko="도깨비",
        title_normalized="도깨비",
        broadcaster_code="tvn",
        start_date=date(2016, 12, 2),
    )
    base.update(kw)
    return NormalizedDrama(**base)


def _person(**kw) -> NormalizedPerson:
    base = dict(name_ko="공유", name_normalized="공유")
    base.update(kw)
    return NormalizedPerson(**base)


# --- drama -----------------------------------------------------------------
def test_drama_external_ref_wins():
    repo = FakeRepo(mapped={(1, "DRAMA", "x"): 42})
    m = resolve_drama(_drama(), 1, repo)
    assert (m.decision, m.canonical_id, m.method, m.confidence) == (
        "AUTO_MERGE",
        42,
        "EXTERNAL_ID",
        1.0,
    )


def test_drama_no_candidates_creates_new():
    assert resolve_drama(_drama(), 1, FakeRepo()).decision == "CREATE_NEW"


def test_drama_title_broadcaster_year_is_deterministic():
    repo = FakeRepo(dramas={"도깨비": [DramaCandidate(7, "도깨비", "tvn", 2016)]})
    m = resolve_drama(_drama(), 1, repo)
    assert (m.decision, m.canonical_id, m.method) == ("AUTO_MERGE", 7, "DETERMINISTIC")


def test_drama_title_only_goes_to_review():
    repo = FakeRepo(dramas={"도깨비": [DramaCandidate(7, "도깨비", None, None)]})
    m = resolve_drama(_drama(), 1, repo)
    assert (m.decision, m.confidence) == ("REVIEW", 0.8)


def test_drama_same_title_different_year_is_a_remake():
    repo = FakeRepo(dramas={"도깨비": [DramaCandidate(7, "도깨비", "tvn", 2005)]})
    m = resolve_drama(_drama(), 1, repo)
    assert m.decision == "CREATE_NEW"
    assert m.signals["conflicting_candidates"] == 1


def test_drama_alias_match():
    repo = FakeRepo(dramas={"goblin": [DramaCandidate(7, "도깨비", "tvn", 2016)]})
    from dramamemory_data.normalization.models import NormalizedAlias

    d = _drama(
        title_normalized="쓸쓸하고찬란하도깨비",
        aliases=[NormalizedAlias(alias="Goblin", alias_normalized="goblin")],
    )
    assert resolve_drama(d, 1, repo).canonical_id == 7


def test_drama_empty_alias_key_is_ignored():
    from dramamemory_data.normalization.models import NormalizedAlias

    class Boom(FakeRepo):
        def dramas_by_title(self, t, source_id=None):
            assert t != "", "empty key must never be looked up"
            return super().dramas_by_title(t, source_id)

    d = _drama(aliases=[NormalizedAlias(alias="怪異", alias_normalized="")])
    assert resolve_drama(d, 1, Boom()).decision == "CREATE_NEW"


def test_drama_two_equal_candidates_review():
    repo = FakeRepo(
        dramas={
            "도깨비": [
                DramaCandidate(7, "도깨비", "tvn", 2016),
                DramaCandidate(8, "도깨비", "tvn", 2016),
            ]
        }
    )
    m = resolve_drama(_drama(), 1, repo)
    assert m.decision == "REVIEW" and m.signals["ambiguous"] == 2


# --- person ----------------------------------------------------------------
def test_person_already_credited_in_this_drama():
    repo = FakeRepo(persons={"공유": [PersonCandidate(3, "공유", None, frozenset({7}))]})
    m = resolve_person(_person(), 1, repo, drama_id=7)
    assert (m.decision, m.canonical_id, m.confidence) == ("AUTO_MERGE", 3, 1.0)


def test_person_name_and_birth_date():
    repo = FakeRepo(persons={"공유": [PersonCandidate(3, "공유", date(1979, 7, 10))]})
    m = resolve_person(_person(birth_date=date(1979, 7, 10)), 1, repo, drama_id=None)
    assert (m.decision, m.canonical_id, m.confidence) == ("AUTO_MERGE", 3, 0.98)


def test_person_name_only_is_review_never_auto():
    repo = FakeRepo(persons={"공유": [PersonCandidate(3, "공유", None)]})
    m = resolve_person(_person(), 1, repo, drama_id=None)
    assert (m.decision, m.canonical_id, m.confidence) == ("REVIEW", 3, 0.85)


def test_person_birth_date_conflict_creates_new():
    repo = FakeRepo(persons={"공유": [PersonCandidate(3, "공유", date(1960, 1, 1))]})
    m = resolve_person(_person(birth_date=date(1979, 7, 10)), 1, repo, drama_id=None)
    assert m.decision == "CREATE_NEW"


def test_person_homonyms_review():
    repo = FakeRepo(
        persons={"공유": [PersonCandidate(3, "공유", None), PersonCandidate(4, "공유", None)]}
    )
    m = resolve_person(_person(), 1, repo, drama_id=None)
    assert m.decision == "REVIEW" and m.signals["ambiguous"] == 2


# --- song / artist ---------------------------------------------------------
def _song(artists=("찬열", "펀치")) -> NormalizedSong:
    return NormalizedSong(
        title="Stay With Me",
        title_normalized="staywithme",
        artists=[
            NormalizedSongArtist(artist=NormalizedArtist(name=a, name_normalized=a), sort_order=i)
            for i, a in enumerate(artists, 1)
        ],
    )


def test_song_same_drama():
    repo = FakeRepo(
        songs={"staywithme": [SongCandidate(9, "staywithme", frozenset(), frozenset({7}))]}
    )
    assert resolve_song(_song(), 1, repo, drama_id=7).canonical_id == 9


def test_song_shared_artist():
    repo = FakeRepo(songs={"staywithme": [SongCandidate(9, "staywithme", frozenset({"찬열"}))]})
    m = resolve_song(_song(), 1, repo, drama_id=None)
    assert (m.decision, m.canonical_id, m.confidence) == ("AUTO_MERGE", 9, 0.98)


def test_song_same_title_other_artist_is_different_song():
    repo = FakeRepo(songs={"staywithme": [SongCandidate(9, "staywithme", frozenset({"someone"}))]})
    assert resolve_song(_song(), 1, repo, drama_id=None).decision == "CREATE_NEW"


def test_artist_by_name():
    repo = FakeRepo(artists={"찬열": 5})
    m = resolve_artist(NormalizedArtist(name="찬열", name_normalized="찬열"), 1, repo)
    assert (m.decision, m.canonical_id) == ("AUTO_MERGE", 5)
    assert (
        resolve_artist(NormalizedArtist(name="x", name_normalized="x"), 1, repo).decision
        == "CREATE_NEW"
    )


# --- whole record ----------------------------------------------------------
def test_resolve_record_shape_and_review_flag():
    d = _drama(
        credits=[
            NormalizedCredit(person=_person(external_id="gong-yoo"), credit_type="ACTOR"),
            NormalizedCredit(
                person=_person(name_ko="김은숙", name_normalized="김은숙"), credit_type="WRITER"
            ),
        ],
        osts=[_song()],
    )
    repo = FakeRepo(persons={"김은숙": [PersonCandidate(11, "김은숙", None)]}, artists={"찬열": 5})
    r = resolve_record(d, 1, repo)
    assert r["drama"]["decision"] == "CREATE_NEW"
    assert r["persons"]["gong-yoo"]["decision"] == "CREATE_NEW"
    assert r["persons"]["name:김은숙"]["decision"] == "REVIEW"
    assert r["songs"]["title:staywithme"]["decision"] == "CREATE_NEW"
    assert r["artists"]["name:찬열"]["canonical_id"] == 5
    assert r["artists"]["name:펀치"]["decision"] == "CREATE_NEW"
    assert r["needs_review"] is True
