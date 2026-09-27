import pytest

from ai_api.retrieval.query import analyze


@pytest.mark.parametrize(
    ("raw", "year_from", "year_to", "broadcaster", "text"),
    [
        ("2016년 tvN 공유 판타지", 2016, 2016, "tvn", "공유 판타지"),
        ("2016년쯤 겨울에 공유 나온 판타지", 2015, 2017, None, "겨울에 공유 판타지"),
        ("2010년대 초반 SBS에서 했던 의학 드라마", 2010, 2013, "sbs", "의학"),
        ("90년대 후반 KBS 드라마", 1996, 1999, "kbs", ""),
        ("2010년대 드라마", 2010, 2019, None, ""),
        ("00년대 초반 멜로", 2000, 2003, None, "멜로"),
        ("호텔 배경에 아이유 나온 드라마", None, None, None, "호텔 아이유"),
        ("도깨비", None, None, None, "도깨비"),
        ("2016 tvn", 2016, 2016, "tvn", ""),  # constraints only
    ],
)
def test_analyze(raw, year_from, year_to, broadcaster, text):
    plan = analyze(raw)
    assert (plan.year_from, plan.year_to, plan.broadcaster) == (year_from, year_to, broadcaster)
    assert plan.text == text


def test_extract_constraints_can_be_disabled():
    plan = analyze("2016년 tvN 공유 나온 드라마", extract_constraints=False)
    assert plan.year_from is None and plan.broadcaster is None
    assert plan.text == "2016년 tvN 공유"


def test_two_digit_year_with_qualifier():
    plan = analyze("16년쯤 공유")
    assert (plan.year_from, plan.year_to) == (2015, 2017)
    assert plan.text == "공유"


def test_has_constraints_flag():
    assert analyze("공유").has_constraints is False
    assert analyze("2016년 공유").has_constraints is True
    assert analyze("jtbc 드라마").has_constraints is True
