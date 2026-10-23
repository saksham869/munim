from __future__ import annotations

import pytest

from munim import economics as eco
from munim.money import fmt_inr, fmt_pct, fmt_pp


def test_reward_ceiling_exact():
    # ₹250 bill, 12% margin, keep 6% -> ₹15
    assert eco.reward_ceiling_paise(25_000, 1_200, 600) == 1_500


def test_reward_ceiling_rounds_down_never_crosses_floor():
    assert eco.reward_ceiling_paise(25_099, 1_200, 600) == 1_505  # 1505.94 -> 1505


@pytest.mark.parametrize("gross,keep", [(600, 600), (500, 600)])
def test_no_headroom_means_no_reward(gross, keep):
    assert eco.reward_ceiling_paise(25_000, gross, keep) == 0
    assert eco.min_bill_for_reward_paise(1_000, gross, keep) is None


def test_min_bill_for_reward_rounds_up():
    assert eco.min_bill_for_reward_paise(4_000, 1_200, 600) == 66_667
    assert eco.reward_ceiling_paise(66_667, 1_200, 600) >= 4_000
    assert eco.reward_ceiling_paise(66_666, 1_200, 600) < 4_000


def test_break_even_matches_closed_form():
    # p=15%, B=₹280, m=12%, r=₹15 -> L* = .15*15/(33.6-15) = 12.097% -> 1210 bps (rounded up)
    assert eco.break_even_lift_bps(1_500, 28_000, 1_200, 1_500) == 1_210


def test_break_even_none_when_reward_eats_the_margin():
    assert eco.break_even_lift_bps(1_500, 28_000, 1_200, 3_360) is None
    assert eco.break_even_lift_bps(1_500, 28_000, 1_200, 5_000) is None


def test_break_even_is_monotonic():
    base = eco.break_even_lift_bps(1_500, 30_000, 1_200, 1_500)
    assert eco.break_even_lift_bps(1_500, 30_000, 1_200, 2_000) > base  # bigger reward
    assert eco.break_even_lift_bps(3_000, 30_000, 1_200, 1_500) > base  # more deadweight
    assert eco.break_even_lift_bps(1_500, 30_000, 1_500, 1_500) < base  # fatter margin
    assert eco.break_even_lift_bps(1_500, 40_000, 1_200, 1_500) < base  # bigger basket
    assert eco.break_even_lift_bps(0, 30_000, 1_200, 1_500) == 0  # nobody returns on their own


@pytest.mark.parametrize("baseline", [500, 1_500, 2_242, 5_132, 8_000])
@pytest.mark.parametrize("basket", [20_000, 27_732, 34_051])
def test_max_reward_for_lift_is_the_exact_boundary(baseline, basket):
    limit = 2_500
    r = eco.max_reward_for_lift_paise(baseline, basket, 1_200, limit)
    assert eco.break_even_lift_bps(baseline, basket, 1_200, r) <= limit
    nxt = eco.break_even_lift_bps(baseline, basket, 1_200, r + 1)
    assert nxt is None or nxt > limit


@pytest.mark.parametrize("n,pct,expected", [(37, 20, (29, 8)), (10, 20, (8, 2)), (5, 0, (5, 0)), (3, 50, (1, 2)), (1, 20, (0, 1))])
def test_split_counts(n, pct, expected):
    assert eco.split_counts(n, pct) == expected


def test_typical_min_bill():
    assert eco.typical_min_bill_paise(34_051) == 25_000
    assert eco.typical_min_bill_paise(30_000) == 25_000
    assert eco.typical_min_bill_paise(1_000) == 5_000


@pytest.mark.parametrize("paise,expected", [
    (0, "₹0"), (1_500, "₹15"), (1_550, "₹16"), (99_999, "₹1,000"), (123_456_789, "₹12,34,568"),
    (-1_500, "-₹15"), (10_000_000, "₹1,00,000"),
])
def test_fmt_inr(paise, expected):
    assert fmt_inr(paise) == expected


def test_fmt_inr_floor_and_decimals():
    assert fmt_inr(1_090, floor=True) == "₹10"
    assert fmt_inr(1_090) == "₹11"
    assert fmt_inr(25_050, decimals=True) == "₹250.50"


@pytest.mark.parametrize("bps,pct,pp", [(1_200, "12%", "12.0 pp"), (1_210, "12.1%", "12.1 pp"), (1_225, "12.3%", "12.3 pp"),
                                        (2_189, "21.9%", "21.9 pp"), (5, "0.1%", "0.1 pp"), (4, "0.0%", "0.0 pp")])
def test_percent_formatting_rounds_half_up(bps, pct, pp):
    assert fmt_pct(bps) == pct
    assert fmt_pp(bps) == pp
