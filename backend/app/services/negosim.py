"""Negotiation simulator — 10 (spec 10_NEGOSIM): rehearse without touching live systems.

Deterministic counterpart model (no LLM needed for the mechanics): the simulated
supplier concedes along a concession ladder in response to buyer moves, bounded
by its walk-away price. Every round is scored; the session ends at accept,
walk-away, or round limit. NOTHING here touches RFQs/quotes/orders — pure
simulation rows, always labeled as such. Live negotiation support stays human-led.
"""
from __future__ import annotations


class NegoError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def simulate(*, list_price_minor: int, walk_away_minor: int, buyer_offers_minor: list[int],
             max_rounds: int = 5, concession_bp: int = 1500) -> dict:
    """Simulate rounds. Supplier opens at list, concedes `concession_bp` of the
    remaining gap per buyer move, never below walk-away. Accept when offer >= ask."""
    if list_price_minor <= 0 or walk_away_minor <= 0 or walk_away_minor >= list_price_minor:
        raise NegoError("NEGO_SETUP_INVALID", "need 0 < walk_away < list_price")
    if not 1 <= max_rounds <= 10:
        raise NegoError("NEGO_ROUNDS_INVALID", "max_rounds must be 1..10")
    if not 0 < concession_bp <= 10_000:
        raise NegoError("NEGO_CONCESSION_INVALID", "concession_bp must be 1..10000")
    if not buyer_offers_minor:
        raise NegoError("NEGO_NO_MOVES", "at least one buyer offer required")
    ask = list_price_minor
    rounds: list[dict] = []
    settled = None
    for i, offer in enumerate(buyer_offers_minor[:max_rounds], start=1):
        if offer <= 0:
            raise NegoError("NEGO_OFFER_INVALID", f"round {i}: offer must be positive")
        if offer >= ask:
            rounds.append({"round": i, "buyer": offer, "supplier": ask, "event": "accepted"})
            settled = ask
            break
        gap = ask - max(offer, walk_away_minor)
        step = max(1, gap * concession_bp // 10_000)
        ask = max(walk_away_minor, ask - step)
        rounds.append({"round": i, "buyer": offer, "supplier": ask, "event": "countered"})
    outcome: dict = {"rounds": rounds, "result": "accepted" if settled is not None else "walk_away",
                     "settled_minor": settled}
    if settled is None:
        if rounds:
            rounds[-1]["event"] = "walk_away"
        outcome["score"] = 0
    else:
        saving_bp = (list_price_minor - settled) * 10_000 // list_price_minor
        outcome["score"] = max(0, min(1000, saving_bp // 10))  # 1 point per 0.1% saved, capped
    return outcome
