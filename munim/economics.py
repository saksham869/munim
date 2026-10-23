"""Pure arithmetic behind every spending decision.

No model, no network, no clock. Money is integer paise; rates are integer
basis points (1 bp = 0.01%). Every function here is mirrored line for line in
docs/rules.js and the two are checked against each other in tests/test_parity.py.
"""

from __future__ import annotations

BPS = 10_000


def ceil_div(a: int, b: int) -> int:
    return -(-a // b)


def reward_ceiling_paise(min_bill_paise: int, gross_margin_bps: int, keep_margin_bps: int) -> int:
    """Largest cashback that still leaves `keep_margin_bps` of margin on the smallest qualifying bill.

    A ₹250 minimum bill at 12% gross margin, keeping 6%, allows ₹250 x 6% = ₹15.
    Rounded down, so the floor is never crossed by a paisa.
    """
    headroom = gross_margin_bps - keep_margin_bps
    if headroom <= 0 or min_bill_paise <= 0:
        return 0
    return (min_bill_paise * headroom) // BPS


def min_bill_for_reward_paise(reward_paise: int, gross_margin_bps: int, keep_margin_bps: int) -> int | None:
    """Smallest minimum bill at which `reward_paise` respects the margin floor."""
    headroom = gross_margin_bps - keep_margin_bps
    if headroom <= 0:
        return None
    return ceil_div(reward_paise * BPS, headroom)


def margin_per_bill_paise(bill_paise: int, gross_margin_bps: int) -> int:
    return (bill_paise * gross_margin_bps) // BPS


def typical_min_bill_paise(avg_basket_paise: int) -> int:
    """A minimum bill most regular baskets clear: 85% of the average basket, rounded down to ₹50."""
    target = avg_basket_paise * 85 // 100
    return max(5_000, (target // 5_000) * 5_000)


def break_even_lift_bps(baseline_bps: int, basket_paise: int, gross_margin_bps: int, reward_paise: int) -> int | None:
    """Extra return rate a campaign needs before it stops losing money.

    Cashback is paid to everyone who comes back, including the people who would
    have come back anyway. With baseline return rate p, typical bill B, margin m
    and reward r, the campaign breaks even when the extra return rate L satisfies

        L * B * m = (p + L) * r      =>      L* = p * r / (B * m - r)

    Returns None when r >= B * m: the offer loses money even if every visit is new.
    """
    margin_scaled = basket_paise * gross_margin_bps
    reward_scaled = reward_paise * BPS
    if margin_scaled <= reward_scaled:
        return None
    return ceil_div(baseline_bps * reward_scaled, margin_scaled - reward_scaled)


def max_reward_for_lift_paise(baseline_bps: int, basket_paise: int, gross_margin_bps: int, max_lift_bps: int) -> int:
    """Largest reward whose break-even lift stays within `max_lift_bps`.

    From p * r / (B * m - r) <= L  =>  r <= L * B * m / (p + L).
    """
    denom = (baseline_bps + max_lift_bps) * BPS
    if denom <= 0:
        return 0
    return (max_lift_bps * basket_paise * gross_margin_bps) // denom


def split_counts(n_eligible: int, holdout_pct: int) -> tuple[int, int]:
    """(treated, holdout) sizes. The holdout is rounded up so it is never empty when asked for."""
    holdout = ceil_div(n_eligible * holdout_pct, 100) if holdout_pct > 0 else 0
    holdout = min(holdout, n_eligible)
    return n_eligible - holdout, holdout
