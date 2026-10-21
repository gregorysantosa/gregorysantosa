# CS2 market bot

Watches Counter-Strike 2 listings on the Steam Community Market and buys one when the price a buyer pays is below the item's usual traded price.

The usual price is the median of recent sales from Steam's public price overview. The current price is the cheapest listing. Both amounts already include the Steam fee and the CS2 fee. A listing is eligible only when it falls inside a discount band and inside the spend caps in the watchlist.

Valve's Steam Subscriber Agreement prohibits bots and other automation of the Community Market. Running this against a live account can spend Steam wallet funds and can lead Valve to restrict that account. Use an account you own. The bot does not log in with a password and it does not approve Steam Guard prompts.

## What a pass does

1. Read `priceoverview` for each market hash name on the watchlist (app id 730).
2. Compare the lowest listing with the median sale:
   - ceiling = median × (1 − `min_discount`), and never above `max_unit_price_cents`
   - floor = median × (1 − `max_discount`)
3. Skip the item unless the 24 hour volume is at least `min_volume` and the lowest price is between the floor and the ceiling.
4. Load the current listings and keep that check on the actual `converted_price + converted_fee` Steam would charge.
5. Buy one unit (`quantity` 1) until the budget or the purchase count is used up.

With the example limits, a median of $10.00 and a 15% minimum discount sets the ceiling at $8.50. The 75% safety cap sets the floor at $2.50. Listings outside that band are left alone. The floor is there so a broken price read or a one-off outlier is not treated as a normal deal.

`scan` and `discover` never place an order. `run` without `--live` is a dry run: it prints the orders it would send and does not write them to the state file. Wallet purchases happen only with `run --live`.

## Setup

Python 3.11 or newer. The bot uses the standard library.

```bash
cd cs2-market-bot
PYTHONPATH=src python3 -m cs2_market_bot scan --config watchlist.example.json
```

Copy `watchlist.example.json` and edit the item names and the spend caps. Prices in that file are cents. `budget_cents` and `max_unit_price_cents` are required.

| Field | Meaning |
| --- | --- |
| `items` | Exact CS2 `market_hash_name` values |
| `currency` | Steam currency id. `1` is USD |
| `min_discount` | How far under the median a listing must be. Default `0.15` |
| `max_discount` | Deepest discount still allowed. Default `0.75`. `1` turns the floor off |
| `min_volume` | Minimum 24 hour sales. Default `25` |
| `max_unit_price_cents` | Most you will pay for one item, fees included |
| `budget_cents` | Most one process will commit, including unresolved buys |
| `max_purchases` | How many listings one process may commit. Default `1` |
| `listings_per_item` | How many live listings to inspect. Default `5`, maximum `20` |
| `request_interval_seconds` | Pause between Steam requests. Minimum `3` against Steam. Default `5` |
| `poll_seconds` | Pause between passes. Minimum `15` against Steam. Default `90` |

Display prices are parsed as currencies with two decimal places (USD, EUR, GBP, and similar).

## Commands

```bash
PYTHONPATH=src python3 -m cs2_market_bot scan --config watchlist.json
PYTHONPATH=src python3 -m cs2_market_bot discover --config watchlist.json --query "AK-47" --count 10
PYTHONPATH=src python3 -m cs2_market_bot run --config watchlist.json --once
PYTHONPATH=src python3 -m cs2_market_bot run --config watchlist.json --live --once
```

`discover` reads a public search page, then scores each name with the same rules. It never buys. Add names you want to the watchlist yourself.

Omit `--once` to keep polling. Stop with Ctrl-C.

## Live mode

Live mode reads two cookies from the environment. Put them there after you log in to `steamcommunity.com` in your own browser (developer tools, cookies for that site):

```bash
export STEAM_SESSION_ID="your sessionid"
export STEAM_LOGIN_SECURE="your steamLoginSecure"
```

Do not put those values in the watchlist file. The loader rejects session and password fields. The process prints a one-line budget summary, then posts to `https://steamcommunity.com/market/buylisting/<id>` with `subtotal`, `fee`, `total`, and `quantity=1`. Public reads are not sent with the cookie. Buys are not retried.

Before the POST, the listing is written to `cs2-market-bot-state.json` as `pending`. After Steam answers:

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
