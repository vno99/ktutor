from starlette.requests import Request

from app.core.i18n import get_locale


def _make_request(header_value: str | None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [
            (b"accept-language", header_value.encode() if header_value else b""),
        ],
    }
    return Request(scope)


def test_locale_fr():
    req = _make_request("fr")
    assert get_locale(req) == "fr"


def test_locale_en():
    req = _make_request("en")
    assert get_locale(req) == "en"


def test_locale_quality_string():
    req = _make_request("fr;q=0.9,en;q=0.8")
    assert get_locale(req) == "fr"
