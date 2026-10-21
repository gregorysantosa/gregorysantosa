import json
import tempfile
import unittest
from pathlib import Path

from cs2_market_bot.bot import Bot
from cs2_market_bot.errors import SteamAuthError, SteamError, SteamRateLimitError
from cs2_market_bot.ledger import load_ledger
from cs2_market_bot.models import BuyResult, Listing, Quote
from helpers import NAME, make_rules


class FakeMarket:
    def __init__(self) -> None:
        self.quotes: dict[str, Quote | Exception] = {}
        self.rows: dict[str, list[Listing] | Exception] = {}
        self.buys: list[tuple[str, Listing]] = []
        self.buy_error: Exception | None = None
        self.buy_result = BuyResult("purchased", "ok")
        self.names: list[str] = []

    def ensure_auth(self) -> None:
        return None

    def price_overview(self, name: str) -> Quote:
        value = self.quotes[name]
        if isinstance(value, Exception):
            raise value
        return value

    def listings(self, name: str, count: int) -> list[Listing]:
        value = self.rows[name]
        if isinstance(value, Exception):
            raise value
        return value[:count]

    def buy_listing(self, name: str, listing: Listing) -> BuyResult:
        self.buys.append((name, listing))
        if self.buy_error:
            raise self.buy_error
        return self.buy_result

    def search(self, query: str, count: int) -> list[str]:
        return self.names[:count]


def cheap_quote() -> Quote:
    return Quote(NAME, 800, 1000, 40)


def listing(listing_id: str, subtotal: int, fee: int) -> Listing:
    return Listing(listing_id, subtotal, fee)


class BotTests(unittest.TestCase):
    def test_dry_run_reserves_budget_without_buying_or_writing_state(self) -> None:
        market = FakeMarket()
        market.quotes[NAME] = cheap_quote()
        market.rows[NAME] = [listing("10", 700, 100), listing("11", 720, 100)]
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            original = '{"listings": {}}\n'
            state.write_text(original, encoding="utf-8")
            events: list[dict] = []
            bot = Bot(
                client=market,
                rules=make_rules(budget_cents=800, max_purchases=2),
                live=False,
                ledger=load_ledger(state),
                state_path=str(state),
                emit=events.append,
            )
            report = bot.run_once(purchase=True)
            saved = state.read_text(encoding="utf-8")
        self.assertEqual(market.buys, [])
        self.assertEqual(saved, original)
        self.assertEqual([order["status"] for order in report.orders], ["dry_run", "skipped"])
        self.assertTrue(all("session" not in json.dumps(event) for event in events))

    def test_live_buy_persists_and_will_not_repeat_the_listing(self) -> None:
        market = FakeMarket()
        market.quotes[NAME] = cheap_quote()
        market.rows[NAME] = [listing("10", 700, 100)]
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            bot = Bot(
                client=market,
                rules=make_rules(),
                live=True,
                state_path=str(state),
                emit=lambda event: None,
            )
            first = bot.run_once(purchase=True)
            second = bot.run_once(purchase=True)
            stored = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(first.orders[0]["status"], "purchased")
        self.assertEqual(second.orders, [])
        self.assertEqual(market.buys, [(NAME, listing("10", 700, 100))])
        self.assertEqual(stored["listings"]["10"]["status"], "bought")

    def test_rechecks_the_listing_price_against_the_band(self) -> None:
        market = FakeMarket()
        market.quotes[NAME] = cheap_quote()
        market.rows[NAME] = [listing("9", 50, 10), listing("10", 900, 50), listing("11", 700, 100)]
        bot = Bot(client=market, rules=make_rules(), live=True, emit=lambda event: None)
        report = bot.run_once(purchase=True)
        self.assertEqual([order["listing_id"] for order in report.orders], ["11"])
        self.assertEqual(market.buys[0][1].listing_id, "11")

    def test_scan_does_not_fetch_listings(self) -> None:
        market = FakeMarket()
        market.quotes[NAME] = cheap_quote()
        market.rows[NAME] = SteamError("should not fetch")
        bot = Bot(client=market, rules=make_rules(), live=False, emit=lambda event: None)
        report = bot.run_once(purchase=False)
        self.assertEqual(report.decisions[0].action, "buy")
        self.assertEqual(report.orders, [])

    def test_unknown_buy_outcome_holds_the_budget(self) -> None:
        market = FakeMarket()
        market.quotes[NAME] = cheap_quote()
        market.rows[NAME] = [listing("10", 700, 100), listing("11", 600, 90)]
        market.buy_error = TimeoutError("timed out")
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            bot = Bot(
                client=market,
                rules=make_rules(budget_cents=2_000),
                live=True,
                state_path=str(state),
                emit=lambda event: None,
            )
            report = bot.run_once(purchase=True)
            stored = load_ledger(state)
        self.assertEqual(report.orders[0]["status"], "held")
        self.assertTrue(report.decisions)
        self.assertEqual(len(market.buys), 1)
        self.assertEqual(stored.committed_cents(), 800)
        self.assertEqual(stored.listings["10"]["status"], "held")

    def test_auth_failure_releases_the_reservation(self) -> None:
        market = FakeMarket()
        market.quotes[NAME] = cheap_quote()
        market.rows[NAME] = [listing("10", 700, 100)]
        market.buy_error = SteamAuthError("rejected")
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            bot = Bot(
                client=market,
                rules=make_rules(),
                live=True,
                state_path=str(state),
                emit=lambda event: None,
            )
            with self.assertRaises(SteamAuthError):
                bot.run_once(purchase=True)
            stored = load_ledger(state)
        self.assertEqual(stored.listings, {})

    def test_rate_limit_stops_the_cycle(self) -> None:
        other = "AWP | Asiimov (Field-Tested)"
        market = FakeMarket()
        market.quotes[NAME] = SteamRateLimitError("slow down")
        market.quotes[other] = cheap_quote()
        events: list[dict] = []
        bot = Bot(
            client=market,
            rules=make_rules(items=(NAME, other)),
            live=False,
            emit=events.append,
        )
        report = bot.run_once(purchase=True)
        self.assertEqual(report.decisions, [])
        self.assertTrue(events[-1]["stopped"])

    def test_discover_never_buys(self) -> None:
        market = FakeMarket()
        market.names = [NAME]
        market.quotes[NAME] = cheap_quote()
        market.buy_error = AssertionError("discover bought")
        bot = Bot(client=market, rules=make_rules(), live=True, emit=lambda event: None)
        decisions = bot.discover("", 5)
        self.assertEqual(decisions[0].action, "buy")
        self.assertEqual(market.buys, [])

    def test_shared_budget_applies_across_items(self) -> None:
        other = "AWP | Asiimov (Field-Tested)"
        market = FakeMarket()
        market.quotes[NAME] = cheap_quote()
        market.quotes[other] = Quote(other, 800, 1000, 40)
        market.rows[NAME] = [listing("10", 700, 100)]
        market.rows[other] = [listing("20", 700, 100)]
        bot = Bot(
            client=market,
            rules=make_rules(items=(NAME, other), budget_cents=800, max_purchases=2),
            live=True,
            emit=lambda event: None,
        )
        report = bot.run_once(purchase=True)
        self.assertEqual([order["status"] for order in report.orders], ["purchased", "skipped"])
        self.assertEqual(len(market.buys), 1)


if __name__ == "__main__":
    unittest.main()
