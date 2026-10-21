"""Quotes, listings, and the limits that gate a purchase."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


CS2_APPID = 730


@dataclass(frozen=True)
class Rules:
    """Spend and discount limits loaded from the watchlist file."""

    currency: int
    min_discount: Decimal
    max_discount: Decimal
    min_volume: int
    max_unit_price_cents: int
    budget_cents: int
    max_purchases: int
    listings_per_item: int
    request_interval_seconds: float
    poll_seconds: float
    items: tuple[str, ...]


@dataclass(frozen=True)
class Quote:
    """Recent trade value versus the cheapest listing, from priceoverview."""

    market_hash_name: str
    lowest_cents: int | None
    median_cents: int | None
    volume: int | None


@dataclass(frozen=True)
class Listing:
    """One purchasable listing. Amounts are the buyer's currency cents."""

    listing_id: str
    subtotal_cents: int
    fee_cents: int

    @property
    def total_cents(self) -> int:
        return self.subtotal_cents + self.fee_cents


@dataclass(frozen=True)
class Decision:
    """Whether the current cheapest listing is far enough under the median."""

    market_hash_name: str
    action: str
    reason: str
    lowest_cents: int | None = None
    median_cents: int | None = None
    volume: int | None = None
    discount: str | None = None
    floor_cents: int | None = None
    ceiling_cents: int | None = None


@dataclass(frozen=True)
class BuyResult:
    """Outcome of one buylisting call.

    ``held`` means the request's fate is unclear (Steam asked for a
    confirmation, or the body could not be read). Callers must keep the
    reserved budget in that case.
    """

    status: str
    message: str
