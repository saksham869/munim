"""Did the campaign make the merchant money? Measured against the holdout, not assumed.

Return rates in the treated group and the holdout get Beta posteriors. The
holdout can borrow strength from a pooled baseline of similar merchants
(CohortPrior): one kirana's holdout is a handful of people, but the network
has seen the same kind of customer at thousands of shops.

The verdict is about money, not lift: P(incremental margin > cashback paid).
Risk-neutral rule: STOP when the offer is more likely losing money than making it
(P(profit) < 0.5); WORKED once P(profit) >= 0.75; UNCERTAIN (keep running) in between.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import asdict, dataclass

WORKED, STOP, UNCERTAIN = "WORKED", "STOP", "UNCERTAIN"


@dataclass(frozen=True)
class CohortPrior:
    """Baseline return rate pooled across similar merchants, worth `strength` pseudo-customers."""

    baseline_bps: int
    strength: int

    def params(self) -> tuple:
        mean = self.baseline_bps / 10_000
        return mean * self.strength, (1 - mean) * self.strength


@dataclass(frozen=True)
class Outcome:
    treated_n: int
    treated_returned: int
    holdout_n: int
    holdout_returned: int
    spend_paise: int
    avg_basket_paise: int


@dataclass(frozen=True)
class Result:
    treated_n: int
    treated_returned: int
    holdout_n: int
    holdout_returned: int
    treated_rate_bps: int
    holdout_rate_bps: int
    lift_mean_bps: int
    lift_p05_bps: int
    lift_p95_bps: int
    prob_lift_positive: float
    prob_profitable: float
    spend_paise: int
    incremental_visits: float
    incremental_revenue_paise: int
    incremental_margin_paise: int
    net_paise: int
    roi: float | None
    verdict: str
    prior: dict | None

    def to_dict(self) -> dict:
        return asdict(self)


def stable_seed(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")


def evaluate(
    outcome: Outcome,
    gross_margin_bps: int,
    prior: CohortPrior | None = None,
    samples: int = 20_000,
    seed: int = 0,
    worked_at: float = 0.75,
    stop_below: float = 0.50,
) -> Result:
    o = outcome
    if not (0 <= o.treated_returned <= o.treated_n and 0 <= o.holdout_returned <= o.holdout_n):
        raise ValueError("returned counts must lie between 0 and the group size")
    if o.treated_n <= 0 or o.holdout_n <= 0:
        raise ValueError("both groups need at least one customer")

    at, bt = 1 + o.treated_returned, 1 + o.treated_n - o.treated_returned
    a0, b0 = prior.params() if prior else (1.0, 1.0)
    ah, bh = a0 + o.holdout_returned, b0 + o.holdout_n - o.holdout_returned

    margin_per_visit = o.avg_basket_paise * gross_margin_bps / 10_000
    value_per_unit_lift = o.treated_n * margin_per_visit

    rng = random.Random(seed)
    lifts = []
    wins = profits = 0
    for _ in range(samples):
        d = rng.betavariate(at, bt) - rng.betavariate(ah, bh)
        lifts.append(d)
        if d > 0:
            wins += 1
        if d * value_per_unit_lift > o.spend_paise:
            profits += 1
    lifts.sort()

    def q(f: float) -> float:
        return lifts[int(f * (samples - 1))]

    lift_mean = sum(lifts) / samples
    incr_visits = lift_mean * o.treated_n
    incr_revenue = incr_visits * o.avg_basket_paise
    incr_margin = incr_visits * margin_per_visit
    net = incr_margin - o.spend_paise
    p_profit = profits / samples

    if p_profit >= worked_at:
        verdict = WORKED
    elif p_profit < stop_below:
        verdict = STOP
    else:
        verdict = UNCERTAIN

    return Result(
        treated_n=o.treated_n,
        treated_returned=o.treated_returned,
        holdout_n=o.holdout_n,
        holdout_returned=o.holdout_returned,
        treated_rate_bps=round(10_000 * o.treated_returned / o.treated_n),
        holdout_rate_bps=round(10_000 * o.holdout_returned / o.holdout_n),
        lift_mean_bps=round(lift_mean * 10_000),
        lift_p05_bps=round(q(0.05) * 10_000),
        lift_p95_bps=round(q(0.95) * 10_000),
        prob_lift_positive=round(wins / samples, 3),
        prob_profitable=round(p_profit, 3),
        spend_paise=o.spend_paise,
        incremental_visits=round(incr_visits, 1),
        incremental_revenue_paise=round(incr_revenue),
        incremental_margin_paise=round(incr_margin),
        net_paise=round(net),
        roi=round(incr_margin / o.spend_paise, 2) if o.spend_paise > 0 else None,
        verdict=verdict,
        prior=asdict(prior) if prior else None,
    )
