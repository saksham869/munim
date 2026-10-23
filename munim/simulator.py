"""A synthetic kirana for demos, tests and the measurement evaluation.

Nothing here is real customer data. Each synthetic customer has a known daily
visit probability, so the simulator knows the true baseline and the true
effect of an offer, and we can check whether Munim's measurement recovers them.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .insights import RULES, Txn, backtest_return_rate, index_visits
from .measurement import CohortPrior, Outcome

# Day 0 of the history is a Monday. Index = day % 7.
WEEKDAY_FACTOR = (1.0, 0.85, 0.85, 1.0, 1.05, 1.15, 1.1)
HOURS = tuple(range(7, 23))
HOUR_WEIGHTS = (6, 9, 9, 7, 5, 4, 3, 2, 2, 3, 6, 9, 10, 9, 6, 3)


@dataclass
class SimCustomer:
    customer_id: str
    kind: str
    daily_rate: float
    lapse_day: int | None
    post_lapse_rate: float
    basket_median_paise: int
    basket_sigma: float
    consented: bool
    offers_30d: int

    def rate_on(self, day: int) -> float:
        base = self.post_lapse_rate if self.lapse_day is not None and day >= self.lapse_day else self.daily_rate
        return min(0.95, base * WEEKDAY_FACTOR[day % 7])


class SyntheticKirana:
    merchant_id = "sharma-general-store"
    display_name = "Sharma General Store"
    city = "Ghaziabad"

    def __init__(self, seed: int = 2026, n_customers: int = 700, days: int = 180):
        self.seed = seed
        self.days = days
        self.today = days  # history covers days 0..days-1; "today" has no visits yet
        rng = random.Random(seed)
        self.customers: dict = {}
        for i in range(n_customers):
            cid = f"c{i:04d}"
            u = rng.random()
            if u < 0.25:
                kind, rate, median = "regular", rng.uniform(2.0, 3.0) / 7, rng.uniform(260, 380)
            elif u < 0.60:
                kind, rate, median = "occasional", rng.uniform(0.25, 0.55) / 7, rng.uniform(200, 320)
            else:
                kind, rate, median = "rare", rng.uniform(0.03, 0.10) / 7, rng.uniform(150, 300)
            lapse = None
            if kind == "regular":
                v = rng.random()
                if v < 0.22:
                    lapse = rng.randint(40, days - 21)  # ordinary churn
                elif v < 0.40:
                    lapse = rng.randint(days - 56, days - 21)  # a quick-commerce dark store opened nearby
            r = rng.random()
            self.customers[cid] = SimCustomer(
                customer_id=cid,
                kind=kind,
                daily_rate=rate,
                lapse_day=lapse,
                post_lapse_rate=rng.uniform(0.007, 0.015),
                basket_median_paise=round(median) * 100,
                basket_sigma=0.35,
                consented=rng.random() < 0.93,
                offers_30d=2 if r < 0.02 else 1 if r < 0.06 else 0,
            )
        self.txns: list = []
        for day in range(days):
            for c in self.customers.values():
                if rng.random() < c.rate_on(day):
                    hour = rng.choices(HOURS, HOUR_WEIGHTS)[0]
                    self.txns.append(Txn(day, hour, c.customer_id, self._basket(rng, c)))

    # ------------------------------------------------------------ data views

    @property
    def consented(self) -> frozenset:
        return frozenset(cid for cid, c in self.customers.items() if c.consented)

    @property
    def offers_last_30d(self) -> dict:
        return {cid: c.offers_30d for cid, c in self.customers.items() if c.offers_30d}

    def set_consent(self, cid: str, value: bool) -> None:
        self.customers[cid].consented = value

    def set_offers_30d(self, cid: str, n: int) -> None:
        self.customers[cid].offers_30d = n

    # ------------------------------------------------------------ ground truth

    @staticmethod
    def _basket(rng: random.Random, c: SimCustomer) -> int:
        rupees = c.basket_median_paise / 100 * math.exp(c.basket_sigma * rng.gauss(0, 1))
        return int(min(3_000, max(30, round(rupees)))) * 100

    def true_return_prob(self, cid: str, start_day: int, window_days: int) -> float:
        c = self.customers[cid]
        stay_away = 1.0
        for d in range(start_day, start_day + window_days):
            stay_away *= 1 - c.rate_on(d)
        return 1 - stay_away

    def simulate_campaign(self, *, treated, holdout, start_day: int, window_days: int, true_lift: float,
                          min_bill_paise: int, reward_paise: int, seed: int) -> tuple:
        """Simulate who comes back. Treated customers' return probability rises by `true_lift`."""
        rng = random.Random(seed)
        t_returned, baskets, truth = 0, [], []
        for cid in sorted(treated):
            base = self.true_return_prob(cid, start_day, window_days)
            truth.append(base)
            if rng.random() < min(0.98, base + true_lift):
                t_returned += 1
                baskets.append(max(self._basket(rng, self.customers[cid]), min_bill_paise))
        h_returned = 0
        for cid in sorted(holdout):
            base = self.true_return_prob(cid, start_day, window_days)
            truth.append(base)
            if rng.random() < base:
                h_returned += 1
        if baskets:
            avg = round(sum(baskets) / len(baskets))
        else:
            avg = round(sum(max(self.customers[c].basket_median_paise, min_bill_paise) for c in treated) / max(1, len(treated)))
        outcome = Outcome(
            treated_n=len(treated),
            treated_returned=t_returned,
            holdout_n=len(holdout),
            holdout_returned=h_returned,
            spend_paise=reward_paise * t_returned,
            avg_basket_paise=avg,
        )
        truth_info = {
            "true_baseline_bps": round(10_000 * sum(truth) / max(1, len(truth))),
            "true_lift_bps": round(10_000 * true_lift),
        }
        return outcome, truth_info


def pooled_priors(n_merchants: int = 20, base_seed: int = 10_000, window_days: int = 14, strength: int = 60) -> dict:
    """Baseline return rates pooled over a network of similar synthetic kiranas.

    This stands in for what Paytm can see across thousands of real merchants:
    for each segment kind, the share of such customers who came back on their own.
    """
    totals = {kind: [0, 0] for kind in RULES}
    for i in range(n_merchants):
        sim = SyntheticKirana(seed=base_seed + i)
        visits = index_visits(sim.txns)
        for kind, (rule, _, _) in RULES.items():
            _, members, returned = backtest_return_rate(visits, rule, sim.today, window_days)
            totals[kind][0] += members
            totals[kind][1] += returned
    return {
        kind: CohortPrior(baseline_bps=round(10_000 * r / m) if m else 5_000, strength=strength)
        for kind, (m, r) in totals.items()
    }
