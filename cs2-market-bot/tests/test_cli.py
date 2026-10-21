import json
import os
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from cs2_market_bot.cli import main
from helpers import NAME


class MarketHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        self.server.calls.append(("GET", parsed.path, dict(self.headers)))  # type: ignore[attr-defined]
        if parsed.path == "/market/priceoverview/":
            name = params.get("market_hash_name", [""])[0]
            payload = self.server.overviews.get(name, {"success": False})  # type: ignore[attr-defined]
            self._json(payload)
            return
        if parsed.path.startswith("/market/listings/") and parsed.path.endswith("/render/"):
            self._json(self.server.listings_payload)  # type: ignore[attr-defined]
            return
        if parsed.path == "/market/search/render/":
            self._json(self.server.search_payload)  # type: ignore[attr-defined]
            return
        self._json({"success": False}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        parsed = urllib.parse.urlparse(self.path)
        form = urllib.parse.parse_qs(raw.decode())
        self.server.calls.append(("POST", parsed.path, dict(self.headers), form))  # type: ignore[attr-defined]
        self._json({"success": 1, "message": "bought"})

    def _json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args: object) -> None:
        return


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), MarketHandler)
        self.server.overviews = {  # type: ignore[attr-defined]
            NAME: {"success": True, "lowest_price": "$8.00", "median_price": "$10.00", "volume": "40"}
        }
        self.server.listings_payload = {  # type: ignore[attr-defined]
            "success": True,
            "listinginfo": {
                "555": {
                    "listingid": "555",
                    "converted_price": 700,
                    "converted_fee": 100,
                    "converted_currencyid": 2001,
                }
            },
        }
        self.server.search_payload = {"success": True, "results": []}  # type: ignore[attr-defined]
        self.server.calls = []  # type: ignore[attr-defined]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.directory = tempfile.TemporaryDirectory()
        self.config = Path(self.directory.name) / "watch.json"
        self.state = Path(self.directory.name) / "state.json"
        self.config.write_text(
            json.dumps(
                {
                    "items": [NAME],
                    "budget_cents": 2000,
                    "max_unit_price_cents": 2000,
                    "max_purchases": 2,
                    "request_interval_seconds": 0,
                    "poll_seconds": 0,
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        self.directory.cleanup()

    def test_dry_run_and_scan_do_not_post(self) -> None:
        env = {"STEAM_MARKET_BASE_URL": self.base, "STEAM_SESSION_ID": "", "STEAM_LOGIN_SECURE": ""}
        with patch.dict(os.environ, env, clear=False):
            scan_code = main(["scan", "--config", str(self.config)])
            dry_code = main(["run", "--config", str(self.config), "--once", "--state", str(self.state)])
        self.assertEqual(scan_code, 0)
        self.assertEqual(dry_code, 0)
        self.assertFalse(self.state.exists())
        self.assertFalse(any(call[0] == "POST" for call in self.server.calls))  # type: ignore[attr-defined]
        self.assertFalse(self.state.exists())

    def test_live_buy_posts_once_and_keeps_the_cookie_out_of_stdout(self) -> None:
        env = {
            "STEAM_MARKET_BASE_URL": self.base,
            "STEAM_SESSION_ID": "session-secret-value",
            "STEAM_LOGIN_SECURE": "login-secret-value",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("sys.stdout") as stdout, patch("sys.stderr"):
                code = main(["run", "--config", str(self.config), "--live", "--once", "--state", str(self.state)])
                second = main(["run", "--config", str(self.config), "--live", "--once", "--state", str(self.state)])
                printed = "".join(call.args[0] for call in stdout.write.call_args_list)
        self.assertEqual(code, 0)
        self.assertEqual(second, 0)
        posts = [call for call in self.server.calls if call[0] == "POST"]  # type: ignore[attr-defined]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0][1], "/market/buylisting/555")
        self.assertIn("session-secret-value", posts[0][2]["Cookie"])
        self.assertEqual(posts[0][3]["quantity"], ["1"])
        self.assertEqual(posts[0][3]["total"], ["800"])
        self.assertNotIn("session-secret-value", printed)
        self.assertNotIn("login-secret-value", printed)
        stored = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(stored["listings"]["555"]["status"], "bought")

    def test_live_without_cookies_exits_before_a_request(self) -> None:
        env = {"STEAM_MARKET_BASE_URL": self.base, "STEAM_SESSION_ID": "", "STEAM_LOGIN_SECURE": ""}
        before = len(self.server.calls)  # type: ignore[attr-defined]
        with patch.dict(os.environ, env, clear=False):
            code = main(["run", "--config", str(self.config), "--live", "--once", "--state", str(self.state)])
        self.assertEqual(code, 3)
        self.assertEqual(len(self.server.calls), before)  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main()
