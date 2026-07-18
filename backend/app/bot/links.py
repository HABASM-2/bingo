"""Build Mini App deep-link URLs for per-game WebApp buttons."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.core.config import settings

VALID_GAMES = frozenset({"bingo", "dama", "aviator", "plinko", "lotto", "home"})


def normalize_game_id(value: str | None) -> str | None:
    if not value:
        return None
    game = value.strip().lower()
    if game in VALID_GAMES:
        return game
    return None


def parse_start_param(start_param: str | None) -> tuple[str | None, str | None]:
    """Parse Telegram startapp / start_param into (game, lang).

    Accepted forms: ``dama``, ``dama_en``, ``dama_am``, ``game_dama``.
    """
    if not start_param:
        return None, None
    raw = start_param.strip().lower().replace("-", "_")
    if not raw:
        return None, None

    parts = [p for p in raw.split("_") if p]
    if not parts:
        return None, None

    game: str | None = None
    lang: str | None = None

    if parts[0] == "game" and len(parts) >= 2:
        game = normalize_game_id(parts[1])
        if len(parts) >= 3 and parts[2] in {"en", "am"}:
            lang = parts[2]
        return game, lang

    if parts[0] in VALID_GAMES:
        game = parts[0]
        if len(parts) >= 2 and parts[1] in {"en", "am"}:
            lang = parts[1]
        return game, lang

    if parts[0] in {"en", "am"} and len(parts) >= 2:
        lang = parts[0]
        game = normalize_game_id(parts[1])
        return game, lang

    return None, None


def build_webapp_url(
    game: str | None = None,
    *,
    lang: str | None = None,
    base_url: str | None = None,
) -> str:
    """Return Mini App URL with optional ``game`` / ``lang`` query params."""
    base = (base_url if base_url is not None else settings.TELEGRAM_WEBAPP_URL) or ""
    base = base.strip()
    if not base:
        return ""

    split = urlsplit(base)
    query = dict(parse_qsl(split.query, keep_blank_values=True))

    normalized_game = normalize_game_id(game)
    if normalized_game and normalized_game != "home":
        query["game"] = normalized_game
    else:
        query.pop("game", None)

    if lang in {"en", "am"}:
        query["lang"] = lang
    else:
        query.pop("lang", None)

    return urlunsplit(
        (
            split.scheme,
            split.netloc,
            split.path,
            urlencode(query),
            split.fragment,
        )
    )


def build_startapp_payload(game: str | None = None, *, lang: str | None = None) -> str:
    """Payload for ``t.me/Bot?startapp=...`` (alphanumeric + underscore)."""
    normalized_game = normalize_game_id(game) or "home"
    if lang in {"en", "am"}:
        return f"{normalized_game}_{lang}"
    return normalized_game


def build_invite_link(referral_code: str | None) -> str:
    """Bot deep-link used by /invite and Mini App share: ``t.me/<bot>?start=<ref>``."""
    code = (referral_code or "").strip()
    username = (settings.TELEGRAM_BOT_USERNAME or "").strip().lstrip("@")
    if not code or not username:
        return ""
    return f"https://t.me/{username}?start={code}"
