import unittest

from cs2_market_bot.errors import MoneyParseError
from cs2_market_bot.money import parse_price_to_cents, parse_volume


class ParsePriceTests(unittest.TestCase):
    def test_usd_prices(self) -> None:
        self.assertEqual(parse_price_to_cents("$12.34"), 1234)
        self.assertEqual(parse_price_to_cents("$1,234.56"), 123456)
        self.assertEqual(parse_price_to_cents("$0.03"), 3)
        self.assertEqual(parse_price_to_cents("$5"), 500)
        self.assertEqual(parse_price_to_cents("$1,234"), 123400)

    def test_euro_prices(self) -> None:
        self.assertEqual(parse_price_to_cents("12,34€"), 1234)
        self.assertEqual(parse_price_to_cents("1.234,56€"), 123456)
        self.assertEqual(parse_price_to_cents("0,03€"), 3)

    def test_rejects_text_without_a_number(self) -> None:
        with self.assertRaises(MoneyParseError):
            parse_price_to_cents("n/a")

    def test_volume_ignores_thousands_separators(self) -> None:
        self.assertEqual(parse_volume("1,234"), 1234)
        self.assertEqual(parse_volume("40"), 40)


if __name__ == "__main__":
    unittest.main()
