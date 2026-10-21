import json
import tempfile
import unittest
from pathlib import Path

from cs2_market_bot.config import load_config
from cs2_market_bot.errors import ConfigError

ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def test_example_watchlist_loads(self) -> None:
        rules = load_config(ROOT / "watchlist.example.json")
        self.assertEqual(rules.budget_cents, 2000)
        self.assertEqual(rules.max_unit_price_cents, 2000)
        self.assertEqual(rules.max_purchases, 2)
        self.assertEqual(rules.items[0], "AK-47 | Redline (Field-Tested)")

    def test_minimal_file_uses_safe_defaults(self) -> None:
        rules = self._load({"items": ["AWP | Asiimov (Field-Tested)"], "budget_cents": 500, "max_unit_price_cents": 250})
        self.assertEqual(rules.max_purchases, 1)
        self.assertEqual(rules.min_volume, 25)
        self.assertEqual(str(rules.min_discount), "0.15")
        self.assertEqual(str(rules.max_discount), "0.75")

    def test_item_objects_are_accepted(self) -> None:
        rules = self._load(
            {
                "items": [{"market_hash_name": "AWP | Asiimov (Field-Tested)"}],
                "budget_cents": 500,
                "max_unit_price_cents": 250,
            }
        )
        self.assertEqual(rules.items, ("AWP | Asiimov (Field-Tested)",))

    def test_rejects_secrets_and_unknown_keys(self) -> None:
        with self.assertRaises(ConfigError) as secret:
            self._load(
                {
                    "items": ["AWP | Asiimov (Field-Tested)"],
                    "budget_cents": 500,
                    "max_unit_price_cents": 250,
                    "sessionid": "nope",
                }
            )
        self.assertIn("STEAM_SESSION_ID", str(secret.exception))
        with self.assertRaises(ConfigError):
            self._load(
                {
                    "items": ["AWP | Asiimov (Field-Tested)"],
                    "budget_cents": 500,
                    "max_unit_price_cents": 250,
                    "base_url": "https://example.com",
                }
            )

    def test_rejects_missing_spend_caps_and_duplicates(self) -> None:
        with self.assertRaises(ConfigError):
            self._load({"items": ["AWP | Asiimov (Field-Tested)"], "max_unit_price_cents": 250})
        with self.assertRaises(ConfigError):
            self._load(
                {
                    "items": ["AWP | Asiimov (Field-Tested)", "AWP | Asiimov (Field-Tested)"],
                    "budget_cents": 500,
                    "max_unit_price_cents": 250,
                }
            )

    def test_rejects_a_hammering_interval_against_steam(self) -> None:
        with self.assertRaises(ConfigError):
            self._load(
                {
                    "items": ["AWP | Asiimov (Field-Tested)"],
                    "budget_cents": 500,
                    "max_unit_price_cents": 250,
                    "request_interval_seconds": 0,
                }
            )

    def test_localhost_tests_may_disable_pacing(self) -> None:
        rules = self._load(
            {
                "items": ["AWP | Asiimov (Field-Tested)"],
                "budget_cents": 500,
                "max_unit_price_cents": 250,
                "request_interval_seconds": 0,
                "poll_seconds": 0,
            },
            enforce_pacing=False,
        )
        self.assertEqual(rules.request_interval_seconds, 0)

    def _load(self, payload: dict, **kwargs: object):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "watch.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return load_config(path, **kwargs)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
