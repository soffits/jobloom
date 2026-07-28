from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {
    "trk",
    "trackingId",
    "refId",
    "lipi",
    "midToken",
    "midSig",
    "from",
    "src",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "vjk",
    "advn",
    "adid",
    "fromjk",
    "tk",
}


def canonicalize_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(str(url).strip())
    if not parts.scheme or not parts.netloc:
        return str(url).strip() or None
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k not in TRACKING_PARAMS
        ],
        doseq=True,
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), host, path, query, ""))
