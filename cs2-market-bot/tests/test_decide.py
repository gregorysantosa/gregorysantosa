import unittest
from decimal import Decimal

from cs2_market_bot.decide import evaluate
from cs2_market_bot.models import Quote
from helpers import NAME, make_rules


def quote(lowest: int | None, median: int | None = 1000, volume: int | None = 40) -> Quote:
    return Quote(NAME, lowest, median, volume)


class DecideTests(unittest.TestCase):
    def test_buys_at_the_ceiling_and_the_floor(self) -> None:
        rules = make_rules()
        at_ceiling = evaluate(quote(850), rules)
        at_floor = evaluate(quote(250), rules)
        self.assertEqual(at_ceiling.action, "buy")
        self.assertEqual(at_ceiling.ceiling_cents, 850)
        self.assertEqual(at_ceiling.floor_cents, 250)
        self.assertEqual(at_ceiling.discount, "0.1500")
        self.assertEqual(at_floor.action, "buy")
        self.assertEqual(at_floor.discount, "0.7500")

    def test_skips_just_outside_the_band(self) -> None:
        rules = make_rules()
        too_expensive = evaluate(quote(851), rules)
        too_cheap = evaluate(quote(249), rules)
        self.assertEqual(too_expensive.action, "skip")
        self.assertEqual(too_expensive.reason, "not below the usual price by enough")
        self.assertEqual(too_cheap.action, "skip")
        self.assertEqual(too_cheap.reason, "discount is past the safety cap")

    def test_skips_thin_or_missing_market_data(self) -> None:
        rules = make_rules()
        self.assertEqual(evaluate(quote(500, median=None), rules).reason, "no usual traded price")
        self.assertEqual(evaluate(quote(None), rules).reason, "no current listing")
        self.assertEqual(evaluate(quote(500, volume=24), rules).reason, "volume below minimum")
        self.assertEqual(evaluate(quote(500, volume=None), rules).reason, "volume below minimum")

    def test_volume_at_the_minimum_can_buy(self) -> None:
        decision = evaluate(quote(500, volume=25), make_rules())
        self.assertEqual(decision.action, "buy")

    def test_price_cap_can_close_the_band(self) -> None:
        rules = make_rules(max_unit_price_cents=100, max_discount=Decimal("0.50"))
        decision = evaluate(quote(100), rules)
        self.assertEqual(decision.action, "skip")
        self.assertEqual(decision.reason, "price cap is below the safety floor")

    def test_price_cap_lowers_the_ceiling(self) -> None:
        rules = make_rules(max_unit_price_cents=400)
        self.assertEqual(evaluate(quote(400), rules).action, "buy")
        self.assertEqual(evaluate(quote(401), rules).action, "skip")

    def test_max_discount_of_one_allows_a_deep_cut(self) -> None:
        rules = make_rules(max_discount=Decimal("1"))
        decision = evaluate(quote(100), rules)
        self.assertEqual(decision.action, "buy")
        self.assertEqual(decision.floor_cents, 0)


if __name__ == "__main__":
    unittest.main()
