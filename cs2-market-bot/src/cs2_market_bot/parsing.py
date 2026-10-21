"""Turn public Steam market JSON into quotes and listings."""

from __future__ import annotations

from cs2_market_bot.errors import MoneyParseError
from cs2_market_bot.models import Listing, Quote
from cs2_market_bot.money import parse_price_to_cents, parse_volume


def quote_from_payload(market_hash_name: str, payload: object) -> Quote:
    if not isinstance(payload, dict) or not payload.get("success"):
        return Quote(market_hash_name, None, None, None)
    return Quote(
        market_hash_name=market_hash_name,
        lowest_cents=_optional_price(payload.get("lowest_price")),
        median_cents=_optional_price(payload.get("median_price")),
        volume=_optional_volume(payload.get("volume")),
    )


def listings_from_payload(payload: object, currency: int) -> list[Listing]:
    """Keep listings whose converted wallet currency matches ``currency``.

    ``converted_price`` is what the seller receives and ``converted_fee`` is
    the Steam plus CS2 fee, both in the buyer's currency cents. Their sum is
    what a purchase charges. Rows without those fields, or in another
    currency, are ignored.
    """

    if not isinstance(payload, dict):
        return []
    info = payload.get("listinginfo")
    if not isinstance(info, dict):
        return []
    expected_currency = 2000 + currency
    listings: list[Listing] = []
    for key, row in info.items():
        if not isinstance(row, dict):
            continue
        listing_id = str(row.get("listingid") or key)
        if not listing_id.isdigit():
            continue
        if "converted_price" not in row or "converted_fee" not in row:
            continue
        wallet_currency = row.get("converted_currencyid")
        if wallet_currency is not None and wallet_currency != expected_currency:
            continue
        subtotal = row.get("converted_price")
        fee = row.get("converted_fee")
        if isinstance(subtotal, bool) or isinstance(fee, bool):
            continue
        if not isinstance(subtotal, int) or not isinstance(fee, int):
            continue
        if subtotal < 1 or fee < 1:
            continue
        listings.append(Listing(listing_id, subtotal, fee))
    listings.sort(key=lambda item: (item.total_cents, item.listing_id))
    return listings


def hash_names_from_search(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return []
    results = payload.get("results")
    if not isinstance(results, list):
        return []
    names: list[str] = []
    seen: set[str] = set()
    for row in results:
        if not isinstance(row, dict):
            continue
        asset = row.get("asset_description")
        asset_dict = asset if isinstance(asset, dict) else {}
        appid = asset_dict.get("appid", 730)
        if appid not in (730, "730"):
            continue
        raw_name = asset_dict.get("market_hash_name") or row.get("hash_name") or row.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            continue
        name = raw_name.strip()
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _optional_price(value: object) -> int | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise MoneyParseError("price was not a string")
    return parse_price_to_cents(value)


def _optional_volume(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise MoneyParseError("volume was not a string")
    return parse_volume(str(value))
