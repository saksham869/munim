"""Trusted analytics on the merchant's own payment history.

Segments, their baseline return rates and their average baskets are computed
here, deterministically, from transactions. The growth agent receives the
results. It never supplies them, so it cannot claim a low baseline to make an
offer look profitable.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .models import Segment


@dataclass(frozen=True)
class Txn:
    day: int
    hour: int
    customer_id: str
    amount_paise: int


def index_visits(txns) -> dict:
    """customer_id -> sorted distinct visit days."""
    days = defaultdict(set)
    for t in txns:
        days[t.customer_id].add(t.day)
    return {cid: sorted(ds) for cid, ds in days.items()}


# ---------------------------------------------------------------- segment rules
# Each rule maps (visits, reference day d) to the set of customers in the segment on day d.
# "The last N days" means visit days x with d - N < x <= d.


def lapsed_regulars(visits: dict, d: int, pre_days: int = 90, gap_days: int = 21, min_visits: int = 8) -> set:
    """Came often before, then stopped: >= min_visits in (d-pre_days, d-gap_days], none in (d-gap_days, d]."""
    out = set()
    for cid, days in visits.items():
        if any(d - gap_days < x <= d for x in days):
            continue
        if sum(1 for x in days if d - pre_days < x <= d - gap_days) >= min_visits:
            out.add(cid)
    return out


def one_time_recent(visits: dict, d: int, newest_gap: int = 7, oldest: int = 45) -> set:
    """Exactly one visit ever, made between 1 and 6 weeks before d."""
    out = set()
    for cid, days in visits.items():
        past = [x for x in days if x <= d]
        if len(past) == 1 and d - oldest < past[0] <= d - newest_gap:
            out.add(cid)
    return out


def occasional_active(visits: dict, d: int, lookback: int = 60, recent: int = 14) -> set:
    """2 to 6 visits in the last 60 days, at least one in the last 14."""
    out = set()
    for cid, days in visits.items():
        n = sum(1 for x in days if d - lookback < x <= d)
        if 2 <= n <= 6 and any(d - recent < x <= d for x in days):
            out.add(cid)
    return out


RULES = {
    "lapsed_regulars": (
        lapsed_regulars,
        "Regulars who stopped coming",
        "Came 8+ times in the 3 months before, not seen for 3+ weeks",
    ),
    "one_time_recent": (
        one_time_recent,
        "First-timers who never came back",
        "Exactly one visit, 1 to 6 weeks ago",
    ),
    "occasional_active": (
        occasional_active,
        "Occasional shoppers",
        "2 to 6 visits in 60 days, seen in the last 2 weeks",
    ),
}

# Used only when a rule has no history to backtest against. High on purpose:
# an unknown baseline should make the payback check stricter, not looser.
UNKNOWN_BASELINE_BPS = 5_000


def backtest_return_rate(visits: dict, rule, today: int, window_days: int, weeks: int = 8) -> tuple:
    """Of customers who fit the rule on past reference days, what share came back within window_days?

    Reference days are today - window - 7k for k = 0..weeks-1, so every
    measured window ends before today. Returns (rate_bps, members, returned).
    """
    members = returned = 0
    for k in range(weeks):
        d = today - window_days - 7 * k
        if d <= 0:
            break
        for cid in rule(visits, d):
            members += 1
            if any(d < x <= d + window_days for x in visits[cid]):
                returned += 1
    if members == 0:
        return UNKNOWN_BASELINE_BPS, 0, 0
    return round(10_000 * returned / members), members, returned


def average_basket(txns, customer_ids, today: int, lookback: int = 120) -> int:
    ids = set(customer_ids)
    amounts = [t.amount_paise for t in txns if t.customer_id in ids and today - lookback < t.day <= today]
    if not amounts:
        amounts = [t.amount_paise for t in txns if today - lookback < t.day <= today] or [0]
    return round(sum(amounts) / len(amounts))


def build_segments(txns, today: int, window_days: int = 14) -> list:
    visits = index_visits(txns)
    segments = []
    for kind, (rule, name, description) in RULES.items():
        members = tuple(sorted(rule(visits, today)))
        rate, n_members, n_returned = backtest_return_rate(visits, rule, today, window_days)
        segments.append(
            Segment(
                segment_id=f"{kind}@day{today}",
                kind=kind,
                name=name,
                description=description,
                customer_ids=members,
                baseline_return_bps=rate,
                avg_basket_paise=average_basket(txns, members, today),
                window_days=window_days,
                backtest_members=n_members,
                backtest_returned=n_returned,
            )
        )
    return segments
