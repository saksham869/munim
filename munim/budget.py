"""Weekly growth budget.

A campaign reserves its worst-case spend when it is authorized. When results
come in, the reservation is replaced by what was actually paid and the rest
goes back to that week's budget. Reservations are checked again at commit
time, so two approvals racing for the last rupees cannot both win.
"""

from __future__ import annotations

import threading


class BudgetError(Exception):
    pass


class WeeklyBudget:
    def __init__(self, weekly_paise: int):
        if weekly_paise < 0:
            raise ValueError("weekly budget cannot be negative")
        self.weekly_paise = weekly_paise
        self._entries: dict = {}
        self._lock = threading.Lock()

    def _used(self, week: int) -> int:
        used = 0
        for e in self._entries.values():
            if e["week"] == week:
                used += e["spent"] if e["spent"] is not None else e["committed"]
        return used

    def remaining(self, week: int) -> int:
        with self._lock:
            return self.weekly_paise - self._used(week)

    def commit(self, campaign_id: str, amount_paise: int, week: int) -> int:
        with self._lock:
            if campaign_id in self._entries:
                raise BudgetError(f"{campaign_id} already holds a reservation")
            if amount_paise < 0:
                raise BudgetError("reservation cannot be negative")
            left = self.weekly_paise - self._used(week)
            if amount_paise > left:
                raise BudgetError(f"reservation of {amount_paise} paise exceeds {left} paise left")
            self._entries[campaign_id] = {"week": week, "committed": amount_paise, "spent": None}
            return left - amount_paise

    def settle(self, campaign_id: str, spent_paise: int) -> int:
        """Record actual spend. Returns paise released back to the budget."""
        with self._lock:
            e = self._entries.get(campaign_id)
            if e is None:
                raise BudgetError(f"{campaign_id} has no reservation")
            if e["spent"] is not None:
                raise BudgetError(f"{campaign_id} is already settled")
            if spent_paise < 0:
                raise BudgetError("spend cannot be negative")
            if spent_paise > e["committed"]:
                raise BudgetError("spend above the reservation; the passport cap was breached")
            e["spent"] = spent_paise
            return e["committed"] - spent_paise

    def release(self, campaign_id: str) -> int:
        with self._lock:
            e = self._entries.pop(campaign_id, None)
            return 0 if e is None else e["committed"]

    def snapshot(self) -> dict:
        with self._lock:
            return {cid: dict(e) for cid, e in self._entries.items()}
