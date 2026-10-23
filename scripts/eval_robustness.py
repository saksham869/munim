#!/usr/bin/env python3
"""Does pooled measurement still help when the pooled baseline is wrong?

scripts/eval_measurement.py draws each shop's true return rate around the same
22.4% that the pooled prior is centred on. A real network prior will be off by
some amount, so this script re-runs the same 1,000 campaigns (identical draws,
paired comparison) with the prior deliberately shifted and with weaker and
stronger prior strengths, and repeats the headline comparison over several
seeds to show how much it moves by chance.

Writes docs/data/robustness.json (and a .js copy for the demo page).

    python3 scripts/eval_robustness.py           # about 2 minutes
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from munim.economics import split_counts  # noqa: E402
from munim.measurement import STOP, CohortPrior, Outcome, evaluate  # noqa: E402

GROSS_MARGIN_BPS = 1_200
REWARD_PAISE = 1_500
BASKET_PAISE = 35_000
HOLDOUT_PCT = 20
TRUE_MEAN_BPS = 2_242  # network mean the simulated shops are drawn around (same as eval_measurement.py)
SHOP_SPREAD = 40
PRIOR_STRENGTH = 60

PRIOR_SHIFTS_BPS = (-1_000, -500, 0, 500, 1_000)  # prior centre minus the true network mean
STRENGTHS = (20, 60, 120)


def binomial(rng: random.Random, n: int, p: float) -> int:
    return sum(1 for _ in range(n) if rng.random() < p)


def campaigns(trials: int, seed: int) -> list:
    """The same generator as eval_measurement.py, kept separate so the draws can be reused across priors."""
    rng = random.Random(seed)
    m = GROSS_MARGIN_BPS / 10_000
    mean = TRUE_MEAN_BPS / 10_000
    out = []
    for _ in range(trials):
        n = rng.randint(20, 60)
        n_t, n_h = split_counts(n, HOLDOUT_PCT)
        p_h = rng.betavariate(mean * SHOP_SPREAD, (1 - mean) * SHOP_SPREAD)
        lift = 0.0 if rng.random() < 0.4 else rng.uniform(0.05, 0.30)
        p_t = min(0.98, p_h + lift)
        x_t, x_h = binomial(rng, n_t, p_t), binomial(rng, n_h, p_h)
        net = n_t * ((p_t - p_h) * BASKET_PAISE * m - p_t * REWARD_PAISE)
        out.append((Outcome(n_t, x_t, n_h, x_h, REWARD_PAISE * x_t, BASKET_PAISE), net))
    return out


def score(cases: list, prior, samples: int, seed: int) -> dict:
    right = prof = prof_stopped = lose = lose_kept = 0
    net_kept = 0.0
    for i, (outcome, net) in enumerate(cases):
        r = evaluate(outcome, GROSS_MARGIN_BPS, prior=prior, samples=samples, seed=seed * 1_000_003 + i)
        kept = r.verdict != STOP
        profitable = net > 0
        right += kept == profitable
        if profitable:
            prof += 1
            prof_stopped += not kept
        else:
            lose += 1
            lose_kept += kept
        net_kept += net if kept else 0
    n = len(cases)
    return {
        "correct_rate": round(right / n, 3),
        "profitable_offers_stopped_rate": round(prof_stopped / prof, 3) if prof else None,
        "losing_offers_kept_rate": round(lose_kept / lose, 3) if lose else None,
        "net_per_campaign_paise": round(net_kept / n),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trials", type=int, default=1_000)
    ap.add_argument("--samples", type=int, default=4_000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--seeds", type=int, default=5, help="extra seeds for the spread of the headline numbers")
    ap.add_argument("--out", default=str(ROOT / "docs" / "data" / "robustness.json"))
    args = ap.parse_args()

    cases = campaigns(args.trials, args.seed)
    shop_only = score(cases, None, args.samples, args.seed)

    shifted = []
    for shift in PRIOR_SHIFTS_BPS:
        r = score(cases, CohortPrior(TRUE_MEAN_BPS + shift, PRIOR_STRENGTH), args.samples, args.seed)
        shifted.append({"prior_centre_bps": TRUE_MEAN_BPS + shift, "shift_pp": shift / 100, **r})
    strengths = []
    for k in STRENGTHS:
        r = score(cases, CohortPrior(TRUE_MEAN_BPS, k), args.samples, args.seed)
        strengths.append({"strength": k, **r})

    spread = []
    for s in range(1, args.seeds + 1):
        c = campaigns(args.trials, 100 + s)
        spread.append({"seed": 100 + s,
                       "shop_only": score(c, None, args.samples, 100 + s),
                       "pooled": score(c, CohortPrior(TRUE_MEAN_BPS, PRIOR_STRENGTH), args.samples, 100 + s)})

    report = {
        "generated_by": "scripts/eval_robustness.py",
        "synthetic": True,
        "trials": args.trials,
        "samples_per_evaluation": args.samples,
        "seed": args.seed,
        "true_network_mean_bps": TRUE_MEAN_BPS,
        "decision": "stop if P(profit) < 0.50, else keep",
        "shop_only": shop_only,
        "pooled_with_shifted_prior": shifted,
        "pooled_with_prior_strength": strengths,
        "seed_spread": spread,
    }
    out = pathlib.Path(args.out)
    out.write_text(json.dumps(report, indent=1))
    out.with_suffix(".js").write_text("window.MUNIM_ROBUSTNESS = " + json.dumps(report) + ";\n")

    print(f"{args.trials} campaigns, seed {args.seed}. Shop-only: right {shop_only['correct_rate']:.1%}, "
          f"good offers stopped {shop_only['profitable_offers_stopped_rate']:.1%}, "
          f"losing kept {shop_only['losing_offers_kept_rate']:.1%}, net/campaign {shop_only['net_per_campaign_paise'] / 100:.2f}\n")
    print("Pooled prior centre vs truth   right   good stopped   losing kept   net/campaign (Rs)")
    for r in shifted:
        print(f"  {r['shift_pp']:+6.1f} pp  ({r['prior_centre_bps'] / 100:4.1f}%)     {r['correct_rate']:6.1%}   "
              f"{r['profitable_offers_stopped_rate']:8.1%}      {r['losing_offers_kept_rate']:8.1%}      "
              f"{r['net_per_campaign_paise'] / 100:7.2f}")
    print("\nPrior strength (correct centre)  right   good stopped   losing kept   net/campaign (Rs)")
    for r in strengths:
        print(f"  {r['strength']:5d}                      {r['correct_rate']:6.1%}   "
              f"{r['profitable_offers_stopped_rate']:8.1%}      {r['losing_offers_kept_rate']:8.1%}      "
              f"{r['net_per_campaign_paise'] / 100:7.2f}")
    print("\nOther seeds (shop-only vs pooled):")
    for r in spread:
        a, b = r["shop_only"], r["pooled"]
        print(f"  seed {r['seed']}: right {a['correct_rate']:.1%} vs {b['correct_rate']:.1%}; "
              f"net/campaign {a['net_per_campaign_paise'] / 100:.2f} vs {b['net_per_campaign_paise'] / 100:.2f}")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
