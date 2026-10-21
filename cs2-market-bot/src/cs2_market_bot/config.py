"""Load the watchlist and the spend limits that go with it."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from cs2_market_bot.errors import ConfigError
from cs2_market_bot.models import Rules

_SECRET_KEYS = {
    "sessionid",
    "session_id",
    "steam_login_secure",
    "steamid",
    "password",
    "shared_secret",
    "identity_secret",
    "api_key",
    "cookie",
    "cookies",
}

_OPTIONAL_DEFAULTS = {
    "currency": 1,
    "min_discount": "0.15",
    "max_discount": "0.75",
    "min_volume": 25,
    "max_purchases": 1,
    "listings_per_item": 5,
    "request_interval_seconds": 5,
    "poll_seconds": 90,
}

_ALLOWED_KEYS = set(_OPTIONAL_DEFAULTS) | {"max_unit_price_cents", "budget_cents", "items"}


def load_config(path: str | Path, *, enforce_pacing: bool = True) -> Rules:
    """Read a watchlist JSON file.

    ``budget_cents`` and ``max_unit_price_cents`` are required so a short file
    cannot spend an unbounded amount. Session cookies are rejected if they
    appear here; they belong in the environment, not in a committed file.
    """

    raw_path = Path(path)
    try:
        data = json.loads(raw_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config not found: {raw_path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"config is not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ConfigError("config must be a JSON object")

    for required in ("max_unit_price_cents", "budget_cents", "items"):
        if required not in data:
            raise ConfigError(f"missing {required}")

    unknown = set(data) - _ALLOWED_KEYS
    if unknown:
        secret = sorted(key for key in unknown if key.lower() in _SECRET_KEYS)
        if secret:
            raise ConfigError(
                "refusing secrets in the config file ("
                + ", ".join(secret)
                + "). Set STEAM_SESSION_ID and STEAM_LOGIN_SECURE in the environment."
            )
        raise ConfigError("unknown config keys: " + ", ".join(sorted(unknown)))

    merged = dict(_OPTIONAL_DEFAULTS)
    merged.update(data)
    currency = _positive_int(merged["currency"], "currency")
    if currency > 100:
        raise ConfigError("currency is out of range")
    min_discount = _ratio(merged["min_discount"], "min_discount")
    max_discount = _ratio(merged["max_discount"], "max_discount", allow_one=True)
    if min_discount <= 0 or min_discount >= 1:
        raise ConfigError("min_discount must be greater than 0 and less than 1")
    if max_discount <= min_discount or max_discount > 1:
        raise ConfigError("max_discount must be greater than min_discount and at most 1")

    interval = _non_negative_number(merged["request_interval_seconds"], "request_interval_seconds")
    poll = _non_negative_number(merged["poll_seconds"], "poll_seconds")
    if enforce_pacing:
        if interval < 3:
            raise ConfigError("request_interval_seconds must be at least 3")
        if poll < 15:
            raise ConfigError("poll_seconds must be at least 15")

    listings_per_item = _positive_int(merged["listings_per_item"], "listings_per_item")
    if listings_per_item > 20:
        raise ConfigError("listings_per_item must be at most 20")

    return Rules(
        currency=currency,
        min_discount=min_discount,
        max_discount=max_discount,
        min_volume=_positive_int(merged["min_volume"], "min_volume"),
        max_unit_price_cents=_positive_int(merged["max_unit_price_cents"], "max_unit_price_cents"),
        budget_cents=_positive_int(merged["budget_cents"], "budget_cents"),
        max_purchases=_positive_int(merged["max_purchases"], "max_purchases"),
        listings_per_item=listings_per_item,
        request_interval_seconds=float(interval),
        poll_seconds=float(poll),
        items=_item_names(merged["items"]),
    )


def _item_names(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError("items must be a non-empty list of market hash names")
    names: list[str] = []
    for entry in value:
        if isinstance(entry, str):
            name = entry.strip()
        elif isinstance(entry, dict):
            if set(entry) != {"market_hash_name"}:
                raise ConfigError("item objects only accept market_hash_name")
            raw_name = entry.get("market_hash_name")
            if not isinstance(raw_name, str):
                raise ConfigError("market_hash_name must be a string")
            name = raw_name.strip()
        else:
            raise ConfigError("each item must be a market hash name")
        if not name:
            raise ConfigError("market hash name is empty")
        names.append(name)
    if len(names) != len(set(names)):
        raise ConfigError("duplicate market hash names")
    return tuple(names)


def _ratio(value: object, label: str, *, allow_one: bool = False) -> Decimal:
    try:
        ratio = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ConfigError(f"{label} must be a number") from exc
    upper = Decimal(1) if allow_one else Decimal("0.9999")
    if ratio <= 0 or ratio > upper:
        raise ConfigError(f"{label} is out of range")
    return ratio


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{label} must be an integer")
    if value < 1:
        raise ConfigError(f"{label} must be at least 1")
    return value


def _non_negative_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{label} must be a number")
    if value < 0:
        raise ConfigError(f"{label} cannot be negative")
    return float(value)
