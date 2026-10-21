"""Shared fixtures for the market bot tests."""

from __future__ import annotations

from decimal import Decimal

from cs2_market_bot.models import Rules

NAME = "AK-47 | Redline (Field-Tested)"


def make_rules(**overrides: object) -> Rules:
    base: dict[str, object] = {
        "currency": 1,
        "min_discount": Decimal("0.15"),
        "max_discount": Decimal("0.75"),
        "min_volume": 25,
        "max_unit_price_cents": 5_000,
        "budget_cents": 5_000,
        "max_purchases": 3,
        "listings_per_item": 5,
        "request_interval_seconds": 0,
        "poll_seconds": 0,
        "items": (NAME,),
    }
    base.update(overrides)
    return Rules(**base)  # type: ignore[arg-type]
