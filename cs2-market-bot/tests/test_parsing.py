import unittest

from cs2_market_bot.parsing import hash_names_from_search, listings_from_payload, quote_from_payload
from helpers import NAME


class ParsingTests(unittest.TestCase):
    def test_quote_from_a_successful_overview(self) -> None:
        quote = quote_from_payload(
            NAME,
            {"success": True, "lowest_price": "$8.00", "median_price": "$10.00", "volume": "1,234"},
        )
        self.assertEqual(quote.lowest_cents, 800)
        self.assertEqual(quote.median_cents, 1000)
        self.assertEqual(quote.volume, 1234)

    def test_failed_overview_has_no_prices(self) -> None:
        quote = quote_from_payload(NAME, {"success": False})
        self.assertIsNone(quote.lowest_cents)
        self.assertIsNone(quote.median_cents)

    def test_listings_keep_the_requested_currency_only(self) -> None:
        payload = {
            "listinginfo": {
                "1": {
                    "listingid": "1",
                    "converted_price": 100,
                    "converted_fee": 15,
                    "converted_currencyid": 2003,
                },
                "2": {
                    "listingid": "2",
                    "converted_price": 700,
                    "converted_fee": 100,
                    "converted_currencyid": 2001,
                },
                "3": {"listingid": "3", "converted_price": 50, "converted_fee": 8},
                "bad": {"listingid": "nope", "converted_price": 50, "converted_fee": 8},
                "4": {"listingid": "4", "price": 50, "fee": 8},
            }
        }
        listings = listings_from_payload(payload, currency=1)
        self.assertEqual([item.listing_id for item in listings], ["3", "2"])
        self.assertEqual(listings[1].total_cents, 800)

    def test_search_results_stay_on_cs2(self) -> None:
        payload = {
            "results": [
                {"hash_name": "Sticker | Other", "asset_description": {"appid": 570, "market_hash_name": "Dota Item"}},
                {"asset_description": {"appid": 730, "market_hash_name": NAME}},
                {"hash_name": NAME},
            ]
        }
        self.assertEqual(hash_names_from_search(payload), [NAME])


if __name__ == "__main__":
    unittest.main()
