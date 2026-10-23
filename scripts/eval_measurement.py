#!/usr/bin/env python3
"""How often does Munim keep the offers that make money and stop the ones that don't?

Simulates many small-shop campaigns with known ground truth and compares two
ways of judging them:

  shop-only  the shop's own treated vs holdout groups (flat prior)
  pooled     the same, with the holdout baseline pooled from similar shops

Decision rule in both: STOP if P(profit) < 0.50, otherwise keep running.
Writes docs/data/eval.json.

    python3 scripts/eval_measurement.py            # ~1 minute
    python3 scripts/eval_measurement.py --trials 300 --samples 2000   # quick
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
from munim.measurement import STOP, WORKED, CohortPrior, Outcome, evaluate  # noqa: E402

GROSS_MARGIN_BPS = 1_200
REWARD_PAISE = 1_500
BASKET_PAISE = 35_000
HOLDOUT_PCT = 20
NETWORK_BASELINE_BPS = 2_242  # pooled lapsed-regular baseline from munim.simulator.pooled_priors()
PRIOR_STRENGTH = 60
SHOP_SPREAD = 40  # shops' true baselines vary around the network mean (Beta concentration)


def binomial(rng: random.Random, n: int, p: float) -> int:
    return sum(1 for _ in range(n) if rng.random() < p)


def run(trials: int, samples: int, seed: int) -> dict:
    rng = random.Random(seed)
    prior = CohortPrior(NETWORK_BASELINE_BPS, PRIOR_STRENGTH)
    m = GROSS_MARGIN_BPS / 10_000
    mean = NETWORK_BASELINE_BPS / 10_000
    tallies = {name: {"profitable_kept": 0, "profitable_stopped": 0, "losing_kept": 0, "losing_stopped": 0,
                      "worked": 0, "uncertain": 0, "stop": 0, "net_of_kept_paise": 0}
               for name in ("shop_only", "pooled")}
    truth_profitable = 0
    oracle_net = keep_all_net = 0
    for i in range(trials):
        n = rng.randint(20, 60)
        n_t, n_h = split_counts(n, HOLDOUT_PCT)
        p_h = rng.betavariate(mean * SHOP_SPREAD, (1 - mean) * SHOP_SPREAD)
        lift = 0.0 if rng.random() < 0.4 else rng.uniform(0.05, 0.30)
        p_t = min(0.98, p_h + lift)
        x_t, x_h = binomial(rng, n_t, p_t), binomial(rng, n_h, p_h)
        outcome = Outcome(n_t, x_t, n_h, x_h, REWARD_PAISE * x_t, BASKET_PAISE)
        expected_net = n_t * ((p_t - p_h) * BASKET_PAISE * m - p_t * REWARD_PAISE)
        profitable = expected_net > 0
        truth_profitable += profitable
        keep_all_net += round(expected_net)
        oracle_net += round(expected_net) if profitable else 0
        for name, pr in (("shop_only", None), ("pooled", prior)):
            r = evaluate(outcome, GROSS_MARGIN_BPS, prior=pr, samples=samples, seed=seed * 1_000_003 + i)
            t = tallies[name]
            t[{WORKED: "worked", STOP: "stop"}.get(r.verdict, "uncertain")] += 1
            kept = r.verdict != STOP
            key = ("profitable_" if profitable else "losing_") + ("kept" if kept else "stopped")
            t[key] += 1
            if kept:
                t["net_of_kept_paise"] += round(expected_net)

    def summarise(t: dict) -> dict:
        prof = t["profitable_kept"] + t["profitable_stopped"]
        lose = t["losing_kept"] + t["losing_stopped"]
        return {
            **t,
            "correct_rate": round((t["profitable_kept"] + t["losing_stopped"]) / trials, 3),
            "losing_offers_kept_rate": round(t["losing_kept"] / lose, 3) if lose else None,
            "profitable_offers_stopped_rate": round(t["profitable_stopped"] / prof, 3) if prof else None,
            "worked_rate": round(t["worked"] / trials, 3),
            "uncertain_rate": round(t["uncertain"] / trials, 3),
        }

    return {
        "generated_by": "scripts/eval_measurement.py",
        "synthetic": True,
        "trials": trials,
        "samples_per_evaluation": samples,
        "seed": seed,
        "config": {
            "campaign_size": "20-60 eligible customers, 20% holdout",
            "reward_paise": REWARD_PAISE,
            "basket_paise": BASKET_PAISE,
            "gross_margin_bps": GROSS_MARGIN_BPS,
            "true_baseline": f"Beta around {NETWORK_BASELINE_BPS / 100:.1f}% (concentration {SHOP_SPREAD})",
            "true_lift": "40% of campaigns: 0; 60%: uniform 5-30 pp",
            "pooled_prior": {"baseline_bps": NETWORK_BASELINE_BPS, "strength": PRIOR_STRENGTH},
            "decision": "stop if P(profit) < 0.50, else keep",
        },
        "truly_profitable": truth_profitable,
        "truly_losing": trials - truth_profitable,
        "expected_net_per_campaign_paise": {
            "oracle": round(oracle_net / trials),
            "keep_everything": round(keep_all_net / trials),
            "shop_only": round(tallies["shop_only"]["net_of_kept_paise"] / trials),
            "pooled": round(tallies["pooled"]["net_of_kept_paise"] / trials),
        },
        "shop_only": summarise(tallies["shop_only"]),
        "pooled": summarise(tallies["pooled"]),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trials", type=int, default=1_000)
    ap.add_argument("--samples", type=int, default=4_000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=str(ROOT / "docs" / "data" / "eval.json"))
    args = ap.parse_args()
    report = run(args.trials, args.samples, args.seed)
    out = pathlib.Path(args.out)
    out.write_text(json.dumps(report, indent=1))
    # Same data as a script, so docs/index.html also works when opened straight from disk.
    out.with_suffix(".js").write_text("window.MUNIM_EVAL = " + json.dumps(report) + ";\n")
    print(f"{args.trials} simulated campaigns ({report['truly_profitable']} truly profitable, "
          f"{report['truly_losing']} truly losing money)\n")
    print(f"{'':28s}{'shop-only':>12s}{'pooled':>10s}")
    for key, label in (("correct_rate", "right keep/stop call"),
                       ("losing_offers_kept_rate", "losing offers kept"),
                       ("profitable_offers_stopped_rate", "profitable offers stopped"),
                       ("worked_rate", "verdict WORKED"),
                       ("uncertain_rate", "verdict UNCERTAIN")):
        a, b = report["shop_only"][key], report["pooled"][key]
        print(f"{label:28s}{a:>12.1%}{b:>10.1%}")
    money = report["expected_net_per_campaign_paise"]
    print("\nExpected net per campaign (paise): " + ", ".join(f"{k} {v}" for k, v in money.items()))
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
