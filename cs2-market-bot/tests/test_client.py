import unittest

from cs2_market_bot.client import (
    HttpResponse,
    SteamMarketClient,
    classify_buy_response,
    resolve_base_url,
)
from cs2_market_bot.errors import SteamAuthError, SteamError, SteamRateLimitError
from cs2_market_bot.models import Listing
from helpers import NAME


class ScriptedTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def request(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> HttpResponse:
        self.calls.append((method, url, headers, body))
        return self.responses.pop(0)


class Clock:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def overview_body() -> bytes:
    return b'{"success": true, "lowest_price": "$8.00", "median_price": "$10.00", "volume": "40"}'


class ClientTests(unittest.TestCase):
    def test_paces_public_reads_and_keeps_cookies_off_them(self) -> None:
        clock = Clock()
        transport = ScriptedTransport(
            [
                HttpResponse(200, overview_body(), {}),
                HttpResponse(200, overview_body(), {}),
            ]
        )
        client = SteamMarketClient(
            currency=1,
            session_id="session-secret",
            login_secure="login-secret",
            min_interval=5,
            transport=transport,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        quote = client.price_overview(NAME)
        client.price_overview(NAME)
        self.assertEqual(quote.lowest_cents, 800)
        self.assertEqual(clock.sleeps, [5])
        self.assertNotIn("Cookie", transport.calls[0][2])
        self.assertIn("market_hash_name=AK-47+%7C+Redline+%28Field-Tested%29", transport.calls[0][1])

    def test_retries_a_rate_limited_read_and_not_a_buy(self) -> None:
        clock = Clock()
        transport = ScriptedTransport(
            [
                HttpResponse(429, b"", {}),
                HttpResponse(200, overview_body(), {}),
            ]
        )
        client = SteamMarketClient(
            currency=1,
            min_interval=0,
            transport=transport,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        client.price_overview(NAME)
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(clock.sleeps, [1])

        buy_transport = ScriptedTransport([HttpResponse(429, b"", {})])
        buyer = SteamMarketClient(
            currency=1,
            session_id="session-secret",
            login_secure="login-secret",
            min_interval=0,
            transport=buy_transport,
            clock=Clock().monotonic,
            sleep=lambda seconds: None,
        )
        with self.assertRaises(SteamRateLimitError):
            buyer.buy_listing(NAME, Listing("42", 700, 100))
        self.assertEqual(len(buy_transport.calls), 1)

    def test_buy_posts_one_unit_with_the_session_cookie(self) -> None:
        transport = ScriptedTransport([HttpResponse(200, b'{"success": 1}', {})])
        client = SteamMarketClient(
            currency=1,
            session_id="session-secret",
            login_secure="login-secret",
            min_interval=0,
            transport=transport,
            clock=lambda: 0.0,
            sleep=lambda seconds: None,
        )
        result = client.buy_listing(NAME, Listing("42", 700, 100))
        self.assertEqual(result.status, "purchased")
        method, url, headers, body = transport.calls[0]
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith("/market/buylisting/42"))
        self.assertEqual(headers["Cookie"], "sessionid=session-secret; steamLoginSecure=login-secret")
        encoded = body.decode() if body else ""
        self.assertIn("quantity=1", encoded)
        self.assertIn("subtotal=700", encoded)
        self.assertIn("fee=100", encoded)
        self.assertIn("total=800", encoded)
        self.assertNotIn("session-secret", url)

    def test_buy_requires_a_session_and_rejects_cookie_injection(self) -> None:
        client = SteamMarketClient(currency=1, min_interval=0)
        with self.assertRaises(SteamAuthError):
            client.buy_listing(NAME, Listing("42", 700, 100))
        injected = SteamMarketClient(currency=1, session_id="a; b", login_secure="c", min_interval=0)
        with self.assertRaises(SteamAuthError):
            injected.ensure_auth()

    def test_classifies_purchase_responses(self) -> None:
        self.assertEqual(classify_buy_response(200, {"success": 1}).status, "purchased")
        self.assertEqual(
            classify_buy_response(200, {"wallet_info": {"success": 1}}).status,
            "purchased",
        )
        held = classify_buy_response(200, {"success": 22, "need_confirmation": True, "message": "confirm"})
        self.assertEqual(held.status, "held")
        self.assertEqual(classify_buy_response(200, {"success": 8, "message": "sold"}).status, "rejected")
        self.assertEqual(classify_buy_response(200, None).status, "held")
        self.assertEqual(classify_buy_response(500, {"success": 0}).status, "held")

    def test_base_url_override_stays_on_localhost(self) -> None:
        self.assertEqual(resolve_base_url(None), "https://steamcommunity.com")
        self.assertEqual(resolve_base_url("http://127.0.0.1:9"), "http://127.0.0.1:9")
        with self.assertRaises(SteamError):
            resolve_base_url("https://example.com")


if __name__ == "__main__":
    unittest.main()
