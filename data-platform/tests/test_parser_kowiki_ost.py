from datetime import date

from dramamemory_data.parsers.kowiki_ost import ost_section, parse, split_artists, strip_wiki

GOBLIN = """
== 줄거리 ==
불멸의 도깨비.

== 사운드 트랙 ==
{{OST 안내}}
{{음반 정보
| 음반명     = <span style="color:black"> 도깨비 OST Part. 1 </span>
| 가수명     = [[찬열]], [[펀치 (가수)|펀치]]
| 발매년월일 = 2016년 12월 3일
| 음반종류   = 사운드트랙
}}
=== Part. 1 ===
{{곡 목록
| 총재생시간   = 6:24
| 제목1        = 'Stay With Me'
| 주1        = 찬열, 펀치
| 작곡1        = 이승주, 로코베리
| 재생시간1    = 3:12
| 제목2        = Stay With Me (Inst.)
| 재생시간2    = 3:12
}}
{{-}}
{{음반 정보
| 음반명     = 도깨비 OST Part. 2
| 가수명     = [[10cm (음악 그룹)|10cm]]
| 발매년월일 = 2016년 12월 10일
}}
=== Part. 2 ===
{{곡 목록
| 제목1        = '내 눈에만 보여'
| 주1          =
| 재생시간1    = 2:37
| 제목2        = 내 눈에만 보여 (Inst.)
}}

== 시청률 ==
표.
"""

TABLE = """
== OST ==
{| class="wikitable"
! 파트 !! 제목 !! 가수 !! 재생 시간
|-
| Part 1 || [[너를 위해]] || [[임재범]] || 4:10
|-
| Part 2 || 가시나무 || 조성모 & [[박효신]] || 3:58
|-
| Part 3 || 너를 위해 (MR) || || 4:10
|}
== 각주 ==
"""


def test_section_ends_at_next_heading():
    s = ost_section(GOBLIN)
    assert "Part. 2" in s and "시청률" not in s and "줄거리" not in s
    assert ost_section("== 줄거리 ==\n없음") == ""


def test_strip_wiki_and_artist_split():
    assert strip_wiki("<span style='x'> 도깨비 OST Part. 1 </span>") == "도깨비 OST Part. 1"
    assert split_artists("[[찬열]], [[펀치 (가수)|펀치]] & 10cm feat. 크러쉬") == [
        "찬열",
        "펀치",
        "10cm",
        "크러쉬",
    ]


def test_album_templates_give_part_release_and_fallback_artist():
    songs = parse(GOBLIN, qid="Q24859151")
    assert [(s.title, s.part_no, s.track_no) for s in songs] == [
        ("Stay With Me", 1, 1),
        ("내 눈에만 보여", 2, 2),
    ]  # instrumentals dropped
    first, second = songs
    assert [a.artist.name for a in first.artists] == ["찬열", "펀치"]
    assert first.release_date == date(2016, 12, 3) and first.duration_seconds == 192
    assert first.external_id == "Q24859151:ost:p1:t1"
    # 주2 empty -> the album's artist
    assert [a.artist.name for a in second.artists] == ["10cm"]
    assert second.release_date == date(2016, 12, 10)
    assert second.title_normalized == "내눈에만보여"


def test_wikitable_fallback():
    songs = parse(TABLE, qid="Q1")
    assert [(s.title, s.part_no) for s in songs] == [("너를 위해", 1), ("가시나무", 2)]
    assert [a.artist.name for a in songs[1].artists] == ["조성모", "박효신"]
    assert songs[0].duration_seconds == 250


def test_no_section_means_no_songs():
    assert parse("== 줄거리 ==\n어쩌고", qid="Q1") == []


FULL_ALBUM = """
== 사운드트랙 ==
{{음반 정보
| 음반명 = 정도전 OST
| 가수명 = Various Artists
| 발매년월일 = 2014년 5월 23일
}}
{{곡 목록
| 제목1 = 의로운 삶
| 주1 =
| 제목2 = 다정가
| 주2 = [[김윤아]]
}}
"""


def test_various_artists_is_not_an_artist_and_score_cues_are_skipped():
    assert split_artists("Various Artists") == []
    assert split_artists("효린, Various Artists") == ["효린"]
    songs = parse(FULL_ALBUM, qid="Q9")
    # 의로운 삶: no singer and no part -> a score cue, dropped; 다정가 has a singer
    got = [(s.title, [a.artist.name for a in s.artists]) for s in songs]
    assert got == [("다정가", ["김윤아"])]
