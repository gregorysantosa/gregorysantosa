"""Decide which CS2 listings are under their usual price, then buy within the caps."""

from __future__ import annotations

import json
from dataclasses import dataclass

from cs2_market_bot.decide import evaluate
from cs2_market_bot.errors import MoneyParseError, SteamAuthError, SteamError, SteamRateLimitError
from cs2_market_bot.ledger import Ledger, save_ledger
from cs2_market_bot.models import Decision, Listing, Rules


@dataclass
class CycleReport:
    decisions: list[Decision]
    orders: list[dict[str, object]]


class Bot:
    def __init__(
        self,
        *,
        client: object,
        rules: Rules,
        live: bool,
        ledger: Ledger | None = None,
        state_path: str | None = None,
        emit=None,
    ) -> None:
        self.client = client
        self.rules = rules
        self.live = live
        self.ledger = ledger if ledger is not None else Ledger()
        self.state_path = state_path
        self.emit = emit or print_event

    def run_once(self, *, purchase: bool) -> CycleReport:
        """Price every watchlist item. Eligible listings are reserved when ``purchase`` is set.

        A dry run (``purchase`` true, ``live`` false) still walks the listings
        and consumes the in-memory budget, but it does not call the buy
        endpoint and does not write the state file.
        """

        if self.live:
            self.client.ensure_auth()
        decisions: list[Decision] = []
        orders: list[dict[str, object]] = []
        stopped = False
        for name in self.rules.items:
            decision, stop = self._quote(name)
            if decision is not None:
                decisions.append(decision)
            if stop:
                stopped = True
                break
            if purchase and decision is not None and decision.action == "buy":
                bought, stop = self._buy(decision)
                orders.extend(bought)
                if stop:
                    stopped = True
                    break
        self.emit(
            {
                "event": "cycle_done",
                "quotes": len(decisions),
                "orders": len(orders),
                "committed_cents": self.ledger.committed_cents(),
                "live": self.live,
                "stopped": stopped,
            }
        )
        return CycleReport(decisions, orders)

    def discover(self, query: str, count: int) -> list[Decision]:
        """Score items from a market search. This path never places an order."""

        names = self.client.search(query, count)
        decisions: list[Decision] = []
        for name in names:
            decision, stop = self._quote(name)
            if decision is not None:
                decisions.append(decision)
            if stop:
                break
        return decisions

    def _quote(self, name: str) -> tuple[Decision | None, bool]:
        try:
            quote = self.client.price_overview(name)
        except SteamRateLimitError as exc:
            self.emit({"event": "error", "item": name, "message": str(exc)})
            return None, True
        except (SteamError, MoneyParseError) as exc:
            self.emit({"event": "error", "item": name, "message": str(exc)})
            return Decision(name, "skip", "market read failed"), False
        decision = evaluate(quote, self.rules)
        self.emit(_decision_event(decision))
        return decision, False

    def _buy(self, decision: Decision) -> tuple[list[dict[str, object]], bool]:
        try:
            found = self.client.listings(decision.market_hash_name, self.rules.listings_per_item)
        except SteamRateLimitError as exc:
            self.emit({"event": "error", "item": decision.market_hash_name, "message": str(exc)})
            return [], True
        except SteamError as exc:
            self.emit({"event": "error", "item": decision.market_hash_name, "message": str(exc)})
            return [], False

        orders: list[dict[str, object]] = []
        considered = False
        for listing in found:
            if decision.ceiling_cents is None or listing.total_cents > decision.ceiling_cents:
                continue
            if decision.floor_cents is not None and listing.total_cents < decision.floor_cents:
                continue
            considered = True
            if self.ledger.seen(listing.listing_id):
                continue
            if not self.ledger.room_for(
                listing.total_cents,
                budget_cents=self.rules.budget_cents,
                max_purchases=self.rules.max_purchases,
            ):
                event = _order_event(
                    mode="live" if self.live else "dry_run",
                    name=decision.market_hash_name,
                    listing=listing,
                    status="skipped",
                    message="budget or purchase cap reached",
                )
                self.emit(event)
                orders.append(event)
                break
            event, stop = self._purchase(decision.market_hash_name, listing)
            orders.append(event)
            if stop:
                return orders, True
        if not considered:
            self.emit(
                {
                    "event": "listings",
                    "item": decision.market_hash_name,
                    "message": "no listing is still inside the price band",
                }
            )
        return orders, False

    def _purchase(self, name: str, listing: Listing) -> tuple[dict[str, object], bool]:
        mode = "live" if self.live else "dry_run"
        if not self.live:
            self.ledger.reserve(listing.listing_id, listing.total_cents, name)
            self.ledger.mark(listing.listing_id, "bought")
            event = _order_event(mode=mode, name=name, listing=listing, status="dry_run", message="")
            self.emit(event)
            return event, False

        # Reserve before the POST. A crash or an unreadable response keeps the
        # row so the next start does not send the same purchase again.
        self.ledger.reserve(listing.listing_id, listing.total_cents, name)
        self._save()
        try:
            result = self.client.buy_listing(name, listing)
        except SteamAuthError:
            self.ledger.release(listing.listing_id)
            self._save()
            raise
        except SteamRateLimitError as exc:
            return self._hold(name, listing, str(exc)), True
        except (SteamError, OSError) as exc:
            return self._hold(name, listing, str(exc)), True

        if result.status == "purchased":
            self.ledger.mark(listing.listing_id, "bought")
            status = "purchased"
        elif result.status == "rejected":
            self.ledger.release(listing.listing_id)
            status = "rejected"
        else:
            self.ledger.mark(listing.listing_id, "held")
            status = "held"
        self._save()
        event = _order_event(mode=mode, name=name, listing=listing, status=status, message=result.message)
        self.emit(event)
        return event, False

    def _hold(self, name: str, listing: Listing, message: str) -> dict[str, object]:
        self.ledger.mark(listing.listing_id, "held")
        self._save()
        event = _order_event(mode="live", name=name, listing=listing, status="held", message=message)
        self.emit(event)
        return event

    def _save(self) -> None:
        if self.live and self.state_path:
            save_ledger(self.state_path, self.ledger)


def print_event(event: dict[str, object]) -> None:
    print(json.dumps(event, sort_keys=True), flush=True)


def _decision_event(decision: Decision) -> dict[str, object]:
    return {
        "event": "quote",
        "item": decision.market_hash_name,
        "action": decision.action,
        "reason": decision.reason,
        "lowest_cents": decision.lowest_cents,
        "median_cents": decision.median_cents,
        "volume": decision.volume,
        "discount": decision.discount,
        "floor_cents": decision.floor_cents,
        "ceiling_cents": decision.ceiling_cents,
    }


def _order_event(
    *,
    mode: str,
    name: str,
    listing: Listing,
    status: str,
    message: str,
) -> dict[str, object]:
    return {
        "event": "order",
        "mode": mode,
        "item": name,
        "listing_id": listing.listing_id,
        "subtotal_cents": listing.subtotal_cents,
        "fee_cents": listing.fee_cents,
        "total_cents": listing.total_cents,
        "status": status,
        "message": message[:200],
    }
