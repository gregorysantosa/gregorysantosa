"""Remember purchases whose wallet effect is already committed.

A buy request that times out, or one Steam answers with a confirmation
prompt, is stored as ``held``. Held rows keep counting against the budget so
a restart does not send the same purchase again.
"""

from __future__ import annotations

import json
from pathlib import Path

from cs2_market_bot.errors import LedgerError

_OPEN_STATUSES = {"pending", "bought", "held"}


class Ledger:
    def __init__(self, listings: dict[str, dict[str, object]] | None = None) -> None:
        self.listings: dict[str, dict[str, object]] = dict(listings or {})

    def committed_cents(self) -> int:
        return sum(_row_total(row) for row in self.listings.values() if row.get("status") in _OPEN_STATUSES)

    def purchase_count(self) -> int:
        return sum(1 for row in self.listings.values() if row.get("status") in _OPEN_STATUSES)

    def room_for(self, total_cents: int, *, budget_cents: int, max_purchases: int) -> bool:
        if self.purchase_count() >= max_purchases:
            return False
        return self.committed_cents() + total_cents <= budget_cents

    def seen(self, listing_id: str) -> bool:
        return listing_id in self.listings

    def reserve(self, listing_id: str, total_cents: int, market_hash_name: str) -> None:
        self.listings[listing_id] = {
            "status": "pending",
            "total_cents": total_cents,
            "market_hash_name": market_hash_name,
        }

    def mark(self, listing_id: str, status: str) -> None:
        if status not in _OPEN_STATUSES:
            raise LedgerError(f"unknown listing status {status}")
        self.listings[listing_id]["status"] = status

    def release(self, listing_id: str) -> None:
        self.listings.pop(listing_id, None)


def load_ledger(path: str | Path) -> Ledger:
    file_path = Path(path)
    if not file_path.exists():
        return Ledger()
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LedgerError(f"state file is not valid JSON: {file_path}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("listings"), dict):
        raise LedgerError(f"state file is missing listings: {file_path}")
    listings: dict[str, dict[str, object]] = {}
    for listing_id, row in data["listings"].items():
        if not isinstance(listing_id, str) or not listing_id.isdigit():
            raise LedgerError("state file has a non-numeric listing id")
        if not isinstance(row, dict):
            raise LedgerError("state file has a malformed listing row")
        status = row.get("status")
        total = row.get("total_cents")
        name = row.get("market_hash_name")
        if status not in _OPEN_STATUSES or isinstance(total, bool) or not isinstance(total, int) or total < 1:
            raise LedgerError("state file has a listing row with a bad status or total")
        if not isinstance(name, str) or not name:
            raise LedgerError("state file has a listing row with no item name")
        listings[listing_id] = {
            "status": status,
            "total_cents": total,
            "market_hash_name": name,
        }
    return Ledger(listings)


def save_ledger(path: str | Path, ledger: Ledger) -> None:
    file_path = Path(path)
    payload = {"listings": ledger.listings}
    file_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _row_total(row: dict[str, object]) -> int:
    total = row.get("total_cents")
    if isinstance(total, bool) or not isinstance(total, int):
        raise LedgerError("listing total is missing")
    return total
