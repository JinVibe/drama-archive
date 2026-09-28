from dramamemory_data.links.validator import classify

TVING = "https://www.tving.com/contents/P000123"


def _v(provider, url, status, final=None, error=None):
    return classify(provider, url, http_status=status, final_url=final, error=error)


def test_ok_on_provider_site_is_available():
    v = _v("tving", TVING, 200, TVING)
    assert v.status == "AVAILABLE" and v.http_status == 200


def test_404_and_410_are_not_found():
    assert _v("kbs", "https://vod.kbs.co.kr/x", 404).status == "NOT_FOUND"
    assert _v("kbs", "https://vod.kbs.co.kr/x", 410).status == "NOT_FOUND"


def test_403_alone_is_access_denied_not_dead():
    assert _v("netflix", "https://www.netflix.com/title/1", 403).status == "ACCESS_DENIED"
    assert _v("netflix", "https://www.netflix.com/title/1", 401).status == "ACCESS_DENIED"


def test_region_walls():
    assert _v("netflix", "https://www.netflix.com/title/1", 451).status == "REGION_RESTRICTED"
    v = _v("netflix", "https://www.netflix.com/title/1", 403, "https://www.netflix.com/geo/unavailable")
    assert v.status == "REGION_RESTRICTED"


def test_redirect_to_landing_page_or_off_site_is_redirected():
    assert _v("tving", TVING, 200, "https://www.tving.com/").status == "REDIRECTED"
    assert _v("tving", TVING, 200, "https://www.tving.com/login").status == "REDIRECTED"
    assert _v("tving", TVING, 200, "https://accounts.example.com/sso").status == "REDIRECTED"
    # a redirect within the provider's site to another content page is still available
    assert _v("tving", TVING, 200, "https://www.tving.com/contents/P000999").status == "AVAILABLE"


def test_server_errors_and_exceptions_are_temporary():
    assert _v("sbs", "https://programs.sbs.co.kr/x", 503).status == "TEMPORARY_ERROR"
    assert _v("sbs", "https://programs.sbs.co.kr/x", 429).status == "TEMPORARY_ERROR"
    v = _v("sbs", "https://programs.sbs.co.kr/x", None, error="timeout")
    assert v.status == "TEMPORARY_ERROR" and "timeout" in v.note


def test_unknown_provider_uses_default_rule():
    ok = _v("some_new_ott", "https://ott.example/x", 200, "https://ott.example/x")
    assert ok.status == "AVAILABLE"
    assert _v("some_new_ott", "https://ott.example/x", 302).status == "REDIRECTED"
