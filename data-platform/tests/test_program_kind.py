from dramamemory_data.normalization.program_kind import classify

TV_SERIES = "Q5398426"
WEB_SERIES = "Q526877"
VARIETY = "Q336181"
FILM = "Q11424"
WEBCOMIC = "Q213369"


def test_drama_genre_wins():
    kind, reasons = classify(classes={TV_SERIES}, genre_labels=["romance television series"])
    assert kind == "DRAMA" and reasons == ["genre romance television series"]


def test_reality_show_filed_as_television_series():
    # 런닝맨: class variety show + television series, genre reality television
    kind, reasons = classify(classes={VARIETY, TV_SERIES}, genre_labels=["리얼리티 방송"])
    assert kind == "NOT_DRAMA"
    assert reasons[0].startswith("class Q336181")


def test_talk_show_genre_only():
    assert classify(classes={TV_SERIES}, genre_labels=["토크 쇼"])[0] == "NOT_DRAMA"


def test_no_signal_is_unknown():
    # 스트릿댄스 걸스 파이터: television series, no genre — needs kowiki categories
    assert classify(classes={TV_SERIES})[0] == "UNKNOWN"


def test_kowiki_categories_decide_unknowns():
    assert classify(
        classes={TV_SERIES}, kowiki_categories=["2021년 대한민국의 텔레비전 예능 프로그램"]
    ) == ("NOT_DRAMA", ["kowiki category 2021년 대한민국의 텔레비전 예능 프로그램"])
    assert classify(classes={TV_SERIES}, kowiki_categories=["2021년 텔레비전 드라마"]) == (
        "DRAMA",
        ["kowiki category"],
    )


def test_kowiki_drama_category_beats_wikidata_signals():
    # 미남이시네요 is tagged both "music television" and "텔레비전 드라마"
    mixed = ["music television", "텔레비전 드라마"]
    assert (
        classify(
            classes={TV_SERIES},
            genre_labels=mixed,
            kowiki_categories=["2009년 텔레비전 드라마", "SBS 수목드라마"],
        )[0]
        == "DRAMA"
    )
    assert classify(classes={TV_SERIES}, genre_labels=mixed)[0] == "UNKNOWN"


def test_film_class_alone_is_only_a_hint():
    # KBS 드라마 스페셜 단막극 are often "film" on Wikidata: the categories decide
    assert classify(classes={FILM})[0] == "UNKNOWN"
    assert classify(classes={FILM}, kowiki_categories=["2014년 텔레비전 드라마"])[0] == "DRAMA"
    assert classify(classes={FILM}, genre_labels=["다큐멘터리 영화"])[0] == "NOT_DRAMA"
    assert classify(classes={FILM, WEB_SERIES}, genre_labels=["로맨스 영화"])[0] == "DRAMA"


def test_webcomic_sharing_an_item_with_its_web_drama():
    assert classify(classes={WEBCOMIC, WEB_SERIES})[0] == "UNKNOWN"
    assert classify(classes={WEBCOMIC})[0] == "UNKNOWN"


def test_episode_and_list_articles_are_never_dramas():
    # an anthology episode (단막극) with a drama genre or kowiki drama category is a drama
    assert classify(classes={"Q21191270"}, genre_labels=["텔레비전 드라마"])[0] == "DRAMA"
    assert classify(classes={"Q21191270"})[0] == "UNKNOWN"
    assert classify(classes={"Q13406463"})[0] == "NOT_DRAMA"
    # "2016년 대한민국의 텔레비전 드라마 목록" sits in a drama category on kowiki
    assert classify(
        classes={"Q13406463"}, kowiki_categories=["2016년 텔레비전 드라마"]
    )[0] == "NOT_DRAMA"
    # a "…목록" category is a list signal, not a drama signal
    assert classify(
        classes={TV_SERIES}, kowiki_categories=["대한민국의 텔레비전 드라마 목록"]
    )[0] == "NOT_DRAMA"
