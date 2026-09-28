from dramamemory_data.enrichment.broadcaster import channels_in, infer_broadcaster


def test_slot_category_decides():
    code, cat = infer_broadcaster(
        ["분류:2016년 텔레비전 드라마", "분류:SBS 금토드라마", "분류:대한민국의 텔레비전 드라마"]
    )
    assert (code, cat) == ("sbs", "분류:SBS 금토드라마")


def test_drama_category_outranks_re_airing_category():
    code, _ = infer_broadcaster(["분류:TvN의 텔레비전 드라마", "분류:넷플릭스에서 방영한 프로그램"])
    assert code == "tvn"


def test_generic_category_is_used_when_no_slot_category():
    assert infer_broadcaster(["분류:한국방송공사의 텔레비전 프로그램"])[0] == "kbs"


def test_disagreeing_slot_categories_infer_nothing():
    assert infer_broadcaster(["분류:KBS 2TV 월화드라마", "분류:MBC 수목드라마"]) == (None, None)


def test_category_naming_two_channels_does_not_vote():
    assert channels_in("분류:KBS와 MBC의 공동 제작 드라마") == {"kbs", "mbc"}
    assert infer_broadcaster(["분류:KBS와 MBC의 공동 제작 드라마"]) == (None, None)


def test_channel_patterns_do_not_cross_match():
    assert channels_in("분류:MBC 에브리원의 드라마") == {"mbc_every1"}
    assert channels_in("분류:OCN의 텔레비전 드라마") == {"ocn"}
    assert channels_in("분류:JTBC 수목드라마") == {"jtbc"}
    assert channels_in("분류:2016년 텔레비전 드라마") == set()
    assert channels_in("분류:디즈니+ 오리지널 프로그램") == {"disney_plus"}
