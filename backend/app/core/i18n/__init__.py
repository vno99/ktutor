import json
from pathlib import Path

from starlette.requests import Request

MESSAGES_DIR = Path(__file__).parent


def _load_catalog(locale: str) -> dict:
    path = MESSAGES_DIR / f"messages_{locale}.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        # Fallback to French
        with open(MESSAGES_DIR / "messages_fr.json", "r", encoding="utf-8") as f:
            return json.load(f)


def get_locale(request: Request) -> str:
    """Read locale from Accept-Language header; default fr, fallback en."""
    accept_lang = request.headers.get("accept-language", "")
    if not accept_lang:
        return "fr"
    # Simple parser: take first segment before ;q=... or space
    primary = accept_lang.split(",")[0].strip()
    lang_part = primary.split(";")[0].strip()
    lang = lang_part.lower()[:2]
    if lang in ("en", "fr"):
        return lang
    # Fallback if unknown or empty
    if "en" in accept_lang.lower():
        return "en"
    return "fr"


def get_message(locale: str, section: str, key: str) -> str:
    catalog = _load_catalog(locale)
    return catalog.get(section, {}).get(key, key)
