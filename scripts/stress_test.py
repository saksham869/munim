#!/usr/bin/env python3
"""Stress test of Munim's measurement claims, written by the independent judge review (23 Oct 2026).

Each scenario changes one setting of scripts/eval_measurement.py and reruns 1,000
campaigns: the pooled prior taken from the shop's own history instead of the
network, a festival or slow fortnight that shifts the true return rate away from
history, fewer offers that do nothing, and small cashback lifts. It also replays
the demo's two campaigns 400 times with the same customer groups. The results
and what was decided are in reviews/decision-log.md.

    python3 scripts/stress_test.py        # about a minute
"""
import math
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from munim.economics import split_counts
from munim.measurement import STOP, CohortPrior, Outcome, evaluate, stable_seed

M, R, B, HOLD = 0.12, 1500, 35000, 20
NET = 0.2242
SAMPLES = 2000


def binom(rng, n, p):
    return sum(1 for _ in range(n) if rng.random() < p)


def run(label, trials=1000, seed=7, null_share=0.4, lift_lo=0.05, lift_hi=0.30, shift=0.0,
        prior_kind="network", hist_n=170, spread=40):
    rng = random.Random(seed)
    net = {"keep_all": 0, "oracle": 0, "shop": 0, "pooled": 0}
    tally = {k: {"pk": 0, "ps": 0, "lk": 0, "ls": 0} for k in ("shop", "pooled")}
    for i in range(trials):
        n = rng.randint(20, 60)
        n_t, n_h = split_counts(n, HOLD)
        p_hist = rng.betavariate(NET * spread, (1 - NET) * spread)   # shop's usual (historical) baseline
        p_h = min(0.97, max(0.01, p_hist + shift))                    # this fortnight's true baseline
        lift = 0.0 if rng.random() < null_share else rng.uniform(lift_lo, lift_hi)
        p_t = min(0.98, p_h + lift)
        x_t, x_h = binom(rng, n_t, p_t), binom(rng, n_h, p_h)
        out = Outcome(n_t, x_t, n_h, x_h, R * x_t, B)
        exp_net = n_t * ((p_t - p_h) * B * M - p_t * R)
        prof = exp_net > 0
        net["keep_all"] += exp_net
        net["oracle"] += exp_net if prof else 0
        if prior_kind == "network":
            prior = CohortPrior(round(NET * 10000), 60)
        else:  # the shop's own backtested history, ~hist_n member-observations, no network at all
            est = binom(rng, hist_n, p_hist) / hist_n
            prior = CohortPrior(round(est * 10000), 60)
        for name, pr in (("shop", None), ("pooled", prior)):
            r = evaluate(out, 1200, prior=pr, samples=SAMPLES, seed=seed * 1_000_003 + i)
            kept = r.verdict != STOP
            tally[name][("p" if prof else "l") + ("k" if kept else "s")] += 1
            if kept:
                net[name] += exp_net
    def rates(t):
        prof, lose = t["pk"] + t["ps"], t["lk"] + t["ls"]
        return (f"right {100*(t['pk']+t['ls'])/trials:4.1f}%  losing-kept {100*t['lk']/max(1,lose):4.1f}%  "
                f"profitable-stopped {100*t['ps']/max(1,prof):4.1f}%")
    rs = {k: v / trials / 100 for k, v in net.items()}
    print(f"\n[{label}]  ₹/campaign: keep-all {rs['keep_all']:+.2f}  oracle {rs['oracle']:+.2f}  "
          f"shop-only {rs['shop']:+.2f}  pooled {rs['pooled']:+.2f}")
    print(f"   shop-only: {rates(tally['shop'])}")
    print(f"   pooled   : {rates(tally['pooled'])}")
    print(f"   two-round total (test round always paid): keep-all {2*rs['keep_all']:+.2f}  "
          f"pooled {rs['keep_all']+rs['pooled']:+.2f}  oracle {rs['keep_all']+rs['oracle']:+.2f}")


def demo_representativeness(n_seeds=400):
    """Hold the demo's exact groups fixed; replay the two campaigns under other random draws."""
    from munim.simulator import SyntheticKirana, pooled_priors
    from munim.engine import Munim, SimClock
    from munim.models import MerchantPolicy
    from munim.agent import ReferenceAgent
    sim = SyntheticKirana(seed=2026)
    priors = pooled_priors()
    pol = MerchantPolicy(merchant_id=sim.merchant_id, weekly_budget_paise=50_000, gross_margin_bps=1_200,
                         keep_margin_bps=600, approval_threshold_paise=30_000)
    m = Munim(pol, sim, clock=SimClock(sim.today), secret=b"munim-demo-secret-not-for-production", priors=priors)
    ag = ReferenceAgent()
    lap, occ = m.segment("lapsed_regulars"), m.segment("occasional_active")
    d2 = m.propose(ag.replan(ag.win_back_greedy(lap, pol.merchant_id, "winback-a1"),
                             m.propose(ag.win_back_greedy(lap, pol.merchant_id, "winback-a1")), lap))
    p3 = ag.proposal(occ, pol.merchant_id, "nudge-a1", name="n", reward_paise=1000, min_bill_paise=20000,
                     customer_ids=occ.customer_ids[:30])
    d4 = m.propose(p3)
    both_wrong_shop = both_right_pooled = 0
    for s in range(n_seeds):
        oa, _ = sim.simulate_campaign(treated=d2.treated_ids, holdout=d2.holdout_ids, start_day=sim.today,
                                      window_days=14, true_lift=0.20, min_bill_paise=25000, reward_paise=1500,
                                      seed=stable_seed(f"alt-a:{s}"))
        ob, _ = sim.simulate_campaign(treated=d4.treated_ids, holdout=d4.holdout_ids, start_day=sim.today + 7,
                                      window_days=14, true_lift=0.0, min_bill_paise=20000, reward_paise=1000,
                                      seed=stable_seed(f"alt-b:{s}"))
        sa = evaluate(oa, 1200, None, samples=SAMPLES, seed=s).verdict
        sb = evaluate(ob, 1200, None, samples=SAMPLES, seed=s).verdict
        pa = evaluate(oa, 1200, priors["lapsed_regulars"], samples=SAMPLES, seed=s).verdict
        pb = evaluate(ob, 1200, priors["occasional_active"], samples=SAMPLES, seed=s).verdict
        both_wrong_shop += (sa == STOP and sb != STOP)
        both_right_pooled += (pa != STOP and pb == STOP)
    print(f"\n[demo replayed {n_seeds}x with the same groups] shop-only gets BOTH calls wrong in "
          f"{100*both_wrong_shop/n_seeds:.1f}% of draws; pooled gets BOTH right in {100*both_right_pooled/n_seeds:.1f}%")


def tail_probs():
    def p_ge(k, n, p):
        return sum(math.comb(n, j) * p**j * (1-p)**(n-j) for j in range(k, n+1))
    a = p_ge(5, 9, 0.1844)
    b = (1 - 0.5103) ** 6
    print(f"\n[tail odds] P(>=5 of 9 holdout regulars return | true 18.4%) = {a:.4f}; "
          f"P(0 of 6 occasional return | true 51.0%) = {b:.4f}; joint = {a*b:.6f} (1 in {1/(a*b):,.0f})")


if __name__ == "__main__":
    tail_probs()
    run("A. repo setup (prior centred exactly on the shops' true mean)")
    run("B. prior = the shop's OWN 6-month history (no network)", prior_kind="shop_history")
    run("C. festival fortnight: true baseline +6 pp vs history, network prior", shift=0.06)
    run("D. slow fortnight: true baseline -6 pp vs history, network prior", shift=-0.06)
    run("E. only 20% of offers do nothing (repo assumes 40%)", null_share=0.2)
    run("F. realistic small-cashback lifts: 0-10 pp", lift_lo=0.0, lift_hi=0.10)
    demo_representativeness()
