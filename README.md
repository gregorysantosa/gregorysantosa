![](image.png)

### My name is Gregory Santosa and I am a programmer from the Bay Area with a primary focus on developing programs in Python and C. I really enjoy creating middleware applications and learning more about how software can efficiently interact with databases.

#### Skills: C / Python / JavaScript / React / Express / HTML

## CS2 market bot

`cs2-market-bot` watches Counter-Strike 2 listings on the Steam Community Market and can buy one when the buyer-facing price is below the recent median sale. Full steps, spend caps, and the state file are in `cs2-market-bot/README.md`.

Valve's Steam Subscriber Agreement prohibits bots and other automation of the Community Market. `run --live` spends Steam wallet funds on an account you own.

### Technologies used

- Python 3.11 or newer, standard library only at runtime (`argparse`, `json`, `urllib`, `decimal`, `gzip`, `dataclasses`)
- Steam Community Market HTTP endpoints for CS2 app id 730: `priceoverview`, `search/render`, listing `render`, and `buylisting`
- A JSON watchlist, plus `STEAM_SESSION_ID` and `STEAM_LOGIN_SECURE` for a live session
- `unittest` for tests. setuptools is optional if you want the `cs2-market-bot` command

### How to turn it on

```bash
cd cs2-market-bot
cp watchlist.example.json watchlist.json
PYTHONPATH=src python3 -m cs2_market_bot scan --config watchlist.json
PYTHONPATH=src python3 -m cs2_market_bot run --config watchlist.json --once
export STEAM_SESSION_ID="your sessionid"
export STEAM_LOGIN_SECURE="your steamLoginSecure"
PYTHONPATH=src python3 -m cs2_market_bot run --config watchlist.json --live
```

`scan` and `run` without `--live` do not buy. `--once` takes a single pass. Leave `--once` off to keep polling, and turn the loop off with Ctrl-C.

### Items

- `AK-47 | Redline (Field-Tested)`
- `AWP | Asiimov (Field-Tested)`

The example caps one item and one run at $20, so those skins are skipped while they trade above that. Find other exact `market_hash_name` values with:

```bash
PYTHONPATH=src python3 -m cs2_market_bot discover --config watchlist.json --query "AK-47" --count 10
```
