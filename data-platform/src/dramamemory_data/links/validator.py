"""Official link validation rules — docs/AIRFLOW_DAGS.md §10.

Pure: the DAG does the HTTP, this module decides what a response means for a
given provider. Two rules from the design doc drive everything:

  * a 403 alone is not a dead link (bot walls, geo walls) -> ACCESS_DENIED /
    REGION_RESTRICTED, never NOT_FOUND;
  * a redirect that leaves the provider's own site (login page, home page,
    "content not available") is not AVAILABLE either -> REDIRECTED.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

# provider.code -> (host suffixes that count as "still on the provider's site",
#                   redirect paths that mean the title is gone or gated)
ProviderRule = tuple[tuple[str, ...], tuple[str, ...]]

PROVIDER_RULES: dict[str, ProviderRule] = {
    "kbs": (("kbs.co.kr",), ()),
    "mbc": (("imbc.com", "mbc.co.kr"), ()),
    "sbs": (("sbs.co.kr",), ()),
    "jtbc": (("jtbc.co.kr",), ()),
    "tvn": (("tving.com", "cjenm.com", "tvn.co.kr"), ()),
    "ocn": (("tving.com", "cjenm.com"), ()),
    "netflix": (("netflix.com",), ("/browse", "/login", "/kr", "/")),
    "tving": (("tving.com",), ("/", "/onboarding", "/login")),
    "wavve": (("wavve.com",), ("/", "/login", "/member")),
    "disney_plus": (("disneyplus.com",), ("/", "/login", "/home", "/welcome")),
    "coupang_play": (("coupangplay.com",), ("/", "/login")),
    "watcha": (("watcha.com",), ("/", "/sign_in")),
}
DEFAULT_RULE: ProviderRule = ((), ())

# Region walls come back as 403 or as a redirect to a country landing page.
REGION_MARKERS = ("/geo", "not-available", "unavailable", "region")


@dataclass(frozen=True)
class Verdict:
    status: str          # streaming_link.availability_status
    http_status: int | None
    final_url: str | None
    note: str


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _on_provider(url: str, provider: str) -> bool:
    hosts, _ = PROVIDER_RULES.get(provider, DEFAULT_RULE)
    host = _host(url)
    return not hosts or any(host == h or host.endswith("." + h) for h in hosts)


def classify(
    provider: str,
    original_url: str,
    *,
    http_status: int | None,
    final_url: str | None,
    error: str | None = None,
) -> Verdict:
    """Map one HTTP outcome to an availability status."""
    if error is not None:
        return Verdict("TEMPORARY_ERROR", http_status, final_url, f"request failed: {error}")
    assert http_status is not None
    final = final_url or original_url

    if http_status in (404, 410):
        return Verdict("NOT_FOUND", http_status, final, "provider answered gone")
    region_marker = any(m in final.lower() for m in REGION_MARKERS)
    if http_status == 451 or (http_status == 403 and region_marker):
        return Verdict("REGION_RESTRICTED", http_status, final, "region wall")
    if http_status in (401, 403):
        return Verdict("ACCESS_DENIED", http_status, final, "403/401 is not proof of a dead link")
    if http_status == 429 or http_status >= 500:
        return Verdict("TEMPORARY_ERROR", http_status, final, "retry on the next run")
    if 200 <= http_status < 300:
        if not _on_provider(final, provider):
            return Verdict("REDIRECTED", http_status, final, "left the provider's site")
        _, gone_paths = PROVIDER_RULES.get(provider, DEFAULT_RULE)
        path = urlsplit(final).path.rstrip("/") or "/"
        if final != original_url and path in gone_paths:
            return Verdict("REDIRECTED", http_status, final, "redirected to a landing page")
        if any(m in final.lower() for m in REGION_MARKERS):
            return Verdict("REGION_RESTRICTED", http_status, final, "region landing page")
        return Verdict("AVAILABLE", http_status, final, "ok")
    if 300 <= http_status < 400:
        return Verdict("REDIRECTED", http_status, final, "redirect not followed")
    return Verdict("UNKNOWN", http_status, final, f"unexpected HTTP {http_status}")
