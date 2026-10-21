# CS2 market bot

Watches Counter-Strike 2 listings on the Steam Community Market and buys one when the price a buyer pays is below the item's usual traded price.

The usual price is the median of recent sales from Steam's public price overview. The current price is the cheapest listing. Both amounts already include the Steam fee and the CS2 fee. A listing is eligible only when it falls inside a discount band and inside the spend caps in the watchlist.

Valve's Steam Subscriber Agreement prohibits bots and other automation of the Community Market. Running this against a live account can spend Steam wallet funds and can lead Valve to restrict that account. Use an account you own. The bot does not log in with a password and it does not approve Steam Guard prompts.

## Technologies used

- Python 3.11 or newer
- The standard library only at runtime: `argparse`, `json`, `urllib`, `decimal`, `gzip`, and `dataclasses`
- Steam Community Market HTTP endpoints for CS2 (app id 730): `priceoverview`, `search/render`, listing `render`, and `buylisting`
- A JSON watchlist for items and spend caps
- `STEAM_SESSION_ID` and `STEAM_LOGIN_SECURE` environment variables for a live session
- `unittest` for the test suite
- setuptools, optional, if you want the `cs2-market-bot` console script from `pyproject.toml`

There is no third-party package to install before a scan or a dry run. There is no Steam Web API key. Public reads go out without the session cookie.

## How to turn it on

From `cs2-market-bot`:

1. Copy the example watchlist and edit the names and the spend caps. Prices in that file are cents. `budget_cents` and `max_unit_price_cents` are required.

   ```bash
   cp watchlist.example.json watchlist.json
   ```

2. Price the list once. This path never buys.

   ```bash
   PYTHONPATH=src python3 -m cs2_market_bot scan --config watchlist.json
   ```

3. Take one dry-run pass. It prints the orders it would send and does not write the state file.

   ```bash
   PYTHONPATH=src python3 -m cs2_market_bot run --config watchlist.json --once
   ```

4. Turn on live buying only after the dry run looks right. Export the two cookies from your own logged-in `steamcommunity.com` browser session (developer tools, cookies for that site), then start the loop:

   ```bash
   export STEAM_SESSION_ID="your sessionid"
   export STEAM_LOGIN_SECURE="your steamLoginSecure"
   PYTHONPATH=src python3 -m cs2_market_bot run --config watchlist.json --live
   ```

   Add `--once` to take a single pass and exit. Omit it to keep polling. Stop the loop with Ctrl-C.

   The process prints a one-line budget summary, then posts to `https://steamcommunity.com/market/buylisting/<id>` with `subtotal`, `fee`, `total`, and `quantity=1`. Buys are not retried.

Optional install, after which the same commands work as `cs2-market-bot` without `PYTHONPATH`:

```bash
python3 -m pip install -e .
cs2-market-bot scan --config watchlist.json
```

## Items

The example watchlist ships with two CS2 market hash names:

- `AK-47 | Redline (Field-Tested)`
- `AWP | Asiimov (Field-Tested)`

The example caps one item and one run at $20, so a scan skips those skins while they trade above that. Raise `max_unit_price_cents` and `budget_cents`, or replace the names, before you expect a purchase.

Add other items as exact `market_hash_name` strings. A search can suggest names. It scores them with the same rules and never buys:

```bash
PYTHONPATH=src python3 -m cs2_market_bot discover --config watchlist.json --query "AK-47" --count 10
```

`--count` is from 1 to 20. An empty `--query` asks Steam for heavily listed CS2 items. Copy a name you want into `items` yourself.

Each `items` entry can be a string or `{"market_hash_name": "..."}`. Names must be unique and non-empty.

## What a pass does

1. Read `priceoverview` for each market hash name on the watchlist (app id 730).
2. Compare the lowest listing with the median sale:
   - ceiling = median × (1 − `min_discount`), and never above `max_unit_price_cents`
   - floor = median × (1 − `max_discount`)
3. Skip the item unless the 24 hour volume is at least `min_volume` and the lowest price is between the floor and the ceiling.
4. Load the current listings and keep that check on the actual `converted_price + converted_fee` Steam would charge.
5. Buy one unit (`quantity` 1) until the budget or the purchase count is used up.

With the example limits, a median of $10.00 and a 15% minimum discount sets the ceiling at $8.50. The 75% safety cap sets the floor at $2.50. Listings outside that band are left alone. The floor is there so a broken price read or a one-off outlier is not treated as a normal deal.

`scan` and `discover` never place an order. `run` without `--live` is a dry run. Wallet purchases happen only with `run --live`.

## Watchlist fields

| Field | Meaning |
| --- | --- |
| `items` | Exact CS2 `market_hash_name` values |
| `currency` | Steam currency id. `1` is USD. Default `1` |
| `min_discount` | How far under the median a listing must be. Default `0.15` |
| `max_discount` | Deepest discount still allowed. Default `0.75`. `1` turns the floor off |
| `min_volume` | Minimum 24 hour sales. Default `25` |
| `max_unit_price_cents` | Most you will pay for one item, fees included. Required |
| `budget_cents` | Most one process will commit, including unresolved buys. Required |
| `max_purchases` | How many listings one process may commit. Default `1` |
| `listings_per_item` | How many live listings to inspect. Default `5`, maximum `20` |
| `request_interval_seconds` | Pause between Steam requests. Minimum `3` against Steam. Default `5` |
| `poll_seconds` | Pause between passes. Minimum `15` against Steam. Default `90` |

Display prices are parsed as currencies with two decimal places (USD, EUR, GBP, and similar). Session cookies, passwords, and API keys are rejected if they appear in this file.

## Commands

```bash
PYTHONPATH=src python3 -m cs2_market_bot scan --config watchlist.json
PYTHONPATH=src python3 -m cs2_market_bot discover --config watchlist.json --query "AK-47" --count 10
PYTHONPATH=src python3 -m cs2_market_bot run --config watchlist.json --once
PYTHONPATH=src python3 -m cs2_market_bot run --config watchlist.json --live --once --state cs2-market-bot-state.json
```

| Command | What it does |
| --- | --- |
| `scan --config` | Price the watchlist once. Never buys |
| `discover --config [--query] [--count]` | Score a market search. Never buys |
| `run --config [--once] [--state]` | Dry run. Prints orders and does not save them |
| `run --config --live [--once] [--state]` | Spend wallet funds on eligible listings |

`--state` defaults to `cs2-market-bot-state.json` in the current directory.

## Live mode and the state file

Do not put `STEAM_SESSION_ID` or `STEAM_LOGIN_SECURE` in the watchlist. The loader rejects session and password fields. Public market reads are not sent with the cookie.

Before the POST, the listing is written to the state file as `pending`. After Steam answers:

- `bought` — Steam accepted the purchase
- `held` — Steam asked for confirmation, rate-limited the POST, or the response was unreadable. The cents stay reserved so a restart does not send that listing again
- the row is removed when Steam clearly rejects the purchase

A held row still counts against `budget_cents` and `max_purchases`. Delete a row only after you have checked the wallet and the inventory.

The market account needs Steam Guard already enabled. This bot does not generate or submit Steam Guard confirmations. If Steam holds a purchase for confirmation, finish or cancel it in the Steam client.

## Tests

```bash
cd cs2-market-bot
PYTHONPATH=src python3 -m unittest discover -s tests -v
```
