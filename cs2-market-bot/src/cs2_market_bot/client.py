"""HTTP client for the public CS2 market reads and one authenticated buy.

Public reads use priceoverview, search/render, and the listing render
endpoint. A purchase is a single POST to ``/market/buylisting/<id>`` using the
caller's own ``sessionid`` and ``steamLoginSecure`` cookies. Buys are not
retried: a retry can charge the wallet twice.
"""

from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from cs2_market_bot.errors import SteamAuthError, SteamError, SteamRateLimitError
from cs2_market_bot.models import BuyResult, CS2_APPID, Listing, Quote
from cs2_market_bot.parsing import hash_names_from_search, listings_from_payload, quote_from_payload

_USER_AGENT = "cs2-market-bot/0.1"
_MAX_BODY_BYTES = 2_000_000
_GET_ATTEMPTS = 4


@dataclass
class HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str]


class UrllibTransport:
    """stdlib HTTP transport that does not follow redirects."""

    def request(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> HttpResponse:
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        opener = urllib.request.build_opener(_NoRedirect())
        try:
            with opener.open(request, timeout=30) as response:
                return _read_response(response.status, response.headers, response.read(_MAX_BODY_BYTES + 1))
        except urllib.error.HTTPError as exc:
            raw = exc.read(_MAX_BODY_BYTES + 1)
            return _read_response(exc.code, exc.headers, raw)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class SteamMarketClient:
    def __init__(
        self,
        *,
        currency: int,
        session_id: str = "",
        login_secure: str = "",
        min_interval: float = 5.0,
        base_url: str = "https://steamcommunity.com",
        transport: object | None = None,
        clock=time.monotonic,
        sleep=time.sleep,
    ) -> None:
        if min_interval < 0:
            raise ValueError("min_interval cannot be negative")
        self.currency = currency
        self.session_id = session_id
        self.login_secure = login_secure
        self.min_interval = min_interval
        self.base_url = base_url.rstrip("/")
        self.transport = transport or UrllibTransport()
        self._clock = clock
        self._sleep = sleep
        self._last_request: float | None = None

    def ensure_auth(self) -> None:
        if not self.session_id or not self.login_secure:
            raise SteamAuthError("Live mode needs STEAM_SESSION_ID and STEAM_LOGIN_SECURE.")
        for label, value in (("STEAM_SESSION_ID", self.session_id), ("STEAM_LOGIN_SECURE", self.login_secure)):
            if any(char in value for char in "\r\n;"):
                raise SteamAuthError(f"{label} contains illegal characters.")

    def price_overview(self, market_hash_name: str) -> Quote:
        query = urllib.parse.urlencode(
            {
                "appid": CS2_APPID,
                "currency": self.currency,
                "market_hash_name": market_hash_name,
            }
        )
        payload = self._get_json(f"{self.base_url}/market/priceoverview/?{query}")
        return quote_from_payload(market_hash_name, payload)

    def listings(self, market_hash_name: str, count: int) -> list[Listing]:
        quoted = urllib.parse.quote(market_hash_name, safe="")
        query = urllib.parse.urlencode(
            {
                "start": 0,
                "count": count,
                "currency": self.currency,
                "language": "english",
                "format": "json",
            }
        )
        payload = self._get_json(f"{self.base_url}/market/listings/{CS2_APPID}/{quoted}/render/?{query}")
        return listings_from_payload(payload, self.currency)

    def search(self, query_text: str, count: int) -> list[str]:
        query = urllib.parse.urlencode(
            {
                "query": query_text,
                "start": 0,
                "count": count,
                "search_descriptions": 0,
                "sort_column": "quantity",
                "sort_dir": "desc",
                "appid": CS2_APPID,
                "norender": 1,
            }
        )
        payload = self._get_json(f"{self.base_url}/market/search/render/?{query}")
        return hash_names_from_search(payload)

    def buy_listing(self, market_hash_name: str, listing: Listing) -> BuyResult:
        """Buy one unit of an existing listing. Never retried."""

        self.ensure_auth()
        if not listing.listing_id.isdigit():
            raise SteamError("listing id is not numeric")
        quoted_name = urllib.parse.quote(market_hash_name, safe="")
        referer = f"{self.base_url}/market/listings/{CS2_APPID}/{quoted_name}"
        url = f"{self.base_url}/market/buylisting/{listing.listing_id}"
        form = urllib.parse.urlencode(
            {
                "sessionid": self.session_id,
                "currency": self.currency,
                "subtotal": listing.subtotal_cents,
                "fee": listing.fee_cents,
                "total": listing.total_cents,
                "quantity": 1,
            }
        )
        headers = self._public_headers()
        headers["Referer"] = referer
        headers["Origin"] = self.base_url
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Cookie"] = f"sessionid={self.session_id}; steamLoginSecure={self.login_secure}"
        response = self._send("POST", url, headers, form.encode())
        if response.status == 429:
            raise SteamRateLimitError("Steam rate limited a purchase request.")
        if response.status in (401, 403):
            raise SteamAuthError("Steam rejected the session while buying.")
        payload = _decode_json(response.body)
        return classify_buy_response(response.status, payload)


    def _get_json(self, url: str) -> object:
        delay = max(self.min_interval, 1.0)
        last_error: SteamError | None = None
        for attempt in range(_GET_ATTEMPTS):
            response = self._send("GET", url, self._public_headers(), None)
            if response.status == 429:
                last_error = SteamRateLimitError("Steam rate limited a market read.")
                if attempt == _GET_ATTEMPTS - 1:
                    break
                self._sleep(delay)
                delay = min(delay * 2, 60.0)
                continue
            if response.status in (401, 403):
                raise SteamError(f"Steam refused a market read ({response.status}).")
            if response.status != 200:
                raise SteamError(f"Steam market read failed ({response.status}).")
            payload = _decode_json(response.body)
            if payload is None:
                raise SteamError("Steam market read was not JSON.")
            return payload
        if last_error is None:
            raise SteamError("Steam market read failed.")
        raise last_error

    def _send(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> HttpResponse:
        self._pace()
        response = self.transport.request(method, url, headers, body)
        if len(response.body) > _MAX_BODY_BYTES:
            raise SteamError("Steam response was too large.")
        return response

    def _pace(self) -> None:
        now = self._clock()
        if self._last_request is not None:
            wait = self.min_interval - (now - self._last_request)
            if wait > 0:
                self._sleep(wait)
                now = self._clock()
        self._last_request = now

    def _public_headers(self) -> dict[str, str]:
        return {
            "User-Agent": _USER_AGENT,
            "Accept": "application/json, text/javascript, */*;q=0.1",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{self.base_url}/market/search?appid={CS2_APPID}",
        }


def classify_buy_response(status_code: int, payload: object) -> BuyResult:
    """Map Steam's buylisting response to a purchased, rejected, or held result."""

    if not isinstance(payload, dict):
        return BuyResult("held", "response was not JSON")
    message = str(payload.get("message") or "")[:200]
    success = payload.get("success")
    wallet = payload.get("wallet_info")
    if success is None and isinstance(wallet, dict):
        success = wallet.get("success")
    if success in (1, "1", True):
        return BuyResult("purchased", message)
    if payload.get("need_confirmation") or success in (22, "22"):
        return BuyResult("held", message or "Steam asked for confirmation")
    if status_code >= 500 or status_code == 429:
        return BuyResult("held", message or f"HTTP {status_code}")
    return BuyResult("rejected", message or f"HTTP {status_code}")


def resolve_base_url(value: str | None) -> str:
    """Return the Steam host, or a localhost override used by tests.

    The override exists so a test server can stand in for Steam. It will not
    point at any other host, because live mode sends the session cookie.
    """

    if not value:
        return "https://steamcommunity.com"
    parsed = urllib.parse.urlparse(value)
    host = parsed.hostname
    if parsed.scheme not in ("http", "https") or host not in ("127.0.0.1", "localhost"):
        raise SteamError("STEAM_MARKET_BASE_URL must point at 127.0.0.1 or localhost.")
    return value.rstrip("/")


def _decode_json(body: bytes) -> object | None:
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _read_response(status: int, headers, raw: bytes) -> HttpResponse:
    encoded = ""
    if headers is not None:
        encoded = headers.get("Content-Encoding", "")
    if encoded == "gzip":
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
    header_map = {key: value for key, value in headers.items()} if headers is not None else {}
    return HttpResponse(status=status, body=raw, headers=header_map)
