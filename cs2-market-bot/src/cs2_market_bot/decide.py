"""Compare a live CS2 listing with the item's usual traded price.

The usual price is the median of recent sales reported by Steam's public
priceoverview endpoint. Both that median and the lowest listing are
buyer-facing amounts (item price plus Steam and CS2 fees).

A listing is eligible when its price sits between two bounds:

* ceiling: median times ``(1 - min_discount)``, also capped by the per-item
  max price
* floor: median times ``(1 - max_discount)``

The floor refuses discounts so deep that they are more likely a bad price
read or an illiquid outlier than a normal underpriced listing.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from cs2_market_bot.models import Decision, Quote, Rules


def evaluate(quote: Quote, rules: Rules) -> Decision:
    shared = {
        "market_hash_name": quote.market_hash_name,
        "lowest_cents": quote.lowest_cents,
        "median_cents": quote.median_cents,
        "volume": quote.volume,
    }
    if quote.median_cents is None or quote.median_cents <= 0:
        return Decision(action="skip", reason="no usual traded price", **shared)
    if quote.lowest_cents is None or quote.lowest_cents <= 0:
        return Decision(action="skip", reason="no current listing", **shared)
    if quote.volume is None or quote.volume < rules.min_volume:
        return Decision(action="skip", reason="volume below minimum", **shared)

    ceiling = min(
        _portion_cents(quote.median_cents, Decimal(1) - rules.min_discount),
        rules.max_unit_price_cents,
    )
    floor = _portion_cents(quote.median_cents, Decimal(1) - rules.max_discount)
    discount = _format_discount(quote.median_cents, quote.lowest_cents)
    priced = {
        **shared,
        "discount": discount,
        "floor_cents": floor,
        "ceiling_cents": ceiling,
    }
    if ceiling <= 0 or ceiling < floor:
        return Decision(action="skip", reason="price cap is below the safety floor", **priced)
    if quote.lowest_cents > ceiling:
        return Decision(action="skip", reason="not below the usual price by enough", **priced)
    if quote.lowest_cents < floor:
        return Decision(action="skip", reason="discount is past the safety cap", **priced)
    return Decision(action="buy", reason="below the usual traded price", **priced)


def _portion_cents(median_cents: int, keep_ratio: Decimal) -> int:
    amount = (Decimal(median_cents) * keep_ratio).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(amount)


def _format_discount(median_cents: int, lowest_cents: int) -> str:
    ratio = Decimal(median_cents - lowest_cents) / Decimal(median_cents)
    return f"{ratio.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP):.4f}"
