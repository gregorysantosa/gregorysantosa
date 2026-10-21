"""Command line entry for scan, discover, and the guarded buy loop."""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.parse

from cs2_market_bot.bot import Bot
from cs2_market_bot.client import SteamMarketClient, resolve_base_url
from cs2_market_bot.config import load_config
from cs2_market_bot.errors import ConfigError, LedgerError, SteamAuthError, SteamError
from cs2_market_bot.ledger import load_ledger


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cs2-market-bot")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Price the watchlist once. Never buys.")
    scan.add_argument("--config", required=True)

    run = sub.add_parser("run", help="Watch the list. Purchases are sent only with --live.")
    run.add_argument("--config", required=True)
    run.add_argument("--live", action="store_true", help="Spend wallet funds. Omit this for a dry run.")
    run.add_argument("--once", action="store_true", help="Take one pass and exit.")
    run.add_argument("--state", default="cs2-market-bot-state.json")

    discover = sub.add_parser("discover", help="Score a market search. Never buys.")
    discover.add_argument("--config", required=True)
    discover.add_argument("--query", default="")
    discover.add_argument("--count", type=int, default=10)

    args = parser.parse_args(argv)
    if args.command == "discover" and not 1 <= args.count <= 20:
        print("count must be from 1 to 20.", file=sys.stderr)
        return 2

    try:
        base_url = resolve_base_url(os.environ.get("STEAM_MARKET_BASE_URL"))
        local = urllib.parse.urlparse(base_url).hostname in ("127.0.0.1", "localhost")
        rules = load_config(args.config, enforce_pacing=not local)
    except (ConfigError, SteamError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    live = args.command == "run" and bool(args.live)
    try:
        client = _build_client(rules, live=live, base_url=base_url)
    except SteamAuthError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    if args.command == "scan":
        print("Scan only. No purchases will be sent.", file=sys.stderr)
        Bot(client=client, rules=rules, live=False).run_once(purchase=False)
        return 0

    if args.command == "discover":
        print("Discover only. No purchases will be sent.", file=sys.stderr)
        Bot(client=client, rules=rules, live=False).discover(args.query, args.count)
        return 0

    if not live:
        print("Dry run only. No purchases will be sent. Pass --live to buy.", file=sys.stderr)
    else:
        print(
            f"Live mode. Budget {rules.budget_cents} cents, "
            f"max {rules.max_purchases} purchases, "
            f"max unit price {rules.max_unit_price_cents} cents.",
            file=sys.stderr,
        )

    try:
        ledger = load_ledger(args.state)
    except LedgerError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    bot = Bot(
        client=client,
        rules=rules,
        live=live,
        ledger=ledger,
        state_path=args.state if live else None,
    )
    try:
        while True:
            bot.run_once(purchase=True)
            if args.once:
                return 0
            time.sleep(rules.poll_seconds)
    except SteamAuthError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        return 0


def _build_client(rules, *, live: bool, base_url: str) -> SteamMarketClient:
    session_id = ""
    login_secure = ""
    if live:
        session_id = os.environ.get("STEAM_SESSION_ID", "").strip()
        login_secure = os.environ.get("STEAM_LOGIN_SECURE", "").strip()
    client = SteamMarketClient(
        currency=rules.currency,
        session_id=session_id,
        login_secure=login_secure,
        min_interval=rules.request_interval_seconds,
        base_url=base_url,
    )
    if live:
        client.ensure_auth()
    return client


if __name__ == "__main__":
    raise SystemExit(main())
