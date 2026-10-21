"""Parse the price strings Steam puts in public market payloads.

Steam formats buyer-facing prices with a currency symbol and either a dot or
a comma as the decimal mark. Wallet charges themselves are integer cents in
the listing payload; those values are not parsed here.
"""

from __future__ import annotations

import re

from cs2_market_bot.errors import MoneyParseError

_NUMBER = re.compile(r"\d[\d.,]*")


def parse_price_to_cents(text: str) -> int:
    """Convert a display price such as ``$1,234.56`` or ``1.234,56€`` to cents.

    The parser assumes a currency with two decimal places (USD, EUR, GBP, and
    similar). Whole numbers are major units: ``$5`` is 500 cents.
    """

    match = _NUMBER.search(text.strip())
    if match is None:
        raise MoneyParseError(f"no price in {text!r}")
    major = _to_major_units(match.group(0))
    cents = int(round(major * 100))
    if cents < 0:
        raise MoneyParseError(f"negative price in {text!r}")
    return cents


def parse_volume(text: str) -> int:
    """Convert a 24h volume string such as ``1,234`` to an integer."""

    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        raise MoneyParseError(f"no volume in {text!r}")
    return int(digits)


def _to_major_units(token: str) -> float:
    if "," in token and "." in token:
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif "," in token:
        left, right = token.rsplit(",", 1)
        if len(right) in (1, 2):
            token = left.replace(",", "") + "." + right
        else:
            token = token.replace(",", "")
    elif "." in token:
        left, right = token.rsplit(".", 1)
        if "." in left and len(right) in (1, 2):
            token = left.replace(".", "") + "." + right
        elif len(right) not in (1, 2):
            token = token.replace(".", "")
    try:
        return float(token)
    except ValueError as exc:
        raise MoneyParseError(f"could not parse {token!r}") from exc
