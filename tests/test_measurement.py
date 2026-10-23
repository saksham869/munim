from __future__ import annotations

import pytest

from munim.measurement import STOP, UNCERTAIN, WORKED, CohortPrior, Outcome, evaluate

MARGIN = 1_200


def test_clear_win_is_called_worked():
    o = Outcome(treated_n=200, treated_returned=90, holdout_n=50, holdout_returned=7, spend_paise=90 * 1_500,
                avg_basket_paise=35_000)
    r = evaluate(o, MARGIN, samples=5_000, seed=1)
    assert r.verdict == WORKED
    assert r.prob_profitable > 0.9
    assert r.net_paise > 0


def test_no_effect_is_stopped():
    o = Outcome(200, 30, 50, 8, 30 * 1_500, 35_000)
    r = evaluate(o, MARGIN, samples=5_000, seed=1)
    assert r.verdict == STOP
    assert r.prob_profitable < 0.2


def test_tiny_samples_stay_uncertain_rather_than_pretend():
    o = Outcome(8, 3, 2, 0, 3 * 1_500, 35_000)
    r = evaluate(o, MARGIN, samples=5_000, seed=1)
    assert r.verdict == UNCERTAIN
    assert r.lift_p95_bps - r.lift_p05_bps > 4_000  # honest, wide interval


def test_pooled_baseline_narrows_the_answer():
    o = Outcome(32, 13, 9, 5, 13 * 1_500, 39_531)
    solo = evaluate(o, MARGIN, samples=5_000, seed=3)
    pooled = evaluate(o, MARGIN, prior=CohortPrior(2_242, 60), samples=5_000, seed=3)
    assert (pooled.lift_p95_bps - pooled.lift_p05_bps) < (solo.lift_p95_bps - solo.lift_p05_bps)
    assert pooled.prior == {"baseline_bps": 2_242, "strength": 60}


def test_seeded_runs_are_reproducible():
    o = Outcome(32, 13, 9, 5, 19_500, 39_531)
    assert evaluate(o, MARGIN, seed=42, samples=3_000) == evaluate(o, MARGIN, seed=42, samples=3_000)


def test_incremental_money_adds_up():
    o = Outcome(100, 40, 25, 5, 40 * 1_500, 30_000)
    r = evaluate(o, MARGIN, samples=5_000, seed=9)
    assert r.incremental_margin_paise == pytest.approx(r.incremental_revenue_paise * 0.12, abs=2)
    assert r.net_paise == pytest.approx(r.incremental_margin_paise - r.spend_paise, abs=1)


def test_zero_spend_is_handled():
    r = evaluate(Outcome(20, 0, 5, 0, 0, 30_000), MARGIN, samples=2_000, seed=1)
    assert r.roi is None


@pytest.mark.parametrize("bad", [Outcome(10, 11, 5, 1, 0, 1), Outcome(10, 1, 5, -1, 0, 1), Outcome(0, 0, 5, 1, 0, 1)])
def test_impossible_outcomes_are_rejected(bad):
    with pytest.raises(ValueError):
        evaluate(bad, MARGIN, samples=100)
