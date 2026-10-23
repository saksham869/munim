#!/usr/bin/env python3
"""Run Munim on your own payments export.

Validates the file, computes segments and backtested return rates, then shows
what Munim decides when a growth agent proposes a win-back offer, using the
owner's rules from the command line.

    python3 scripts/import_payments.py examples/sample_payments.csv
    python3 scripts/import_payments.py payments.csv --budget 500 --margin 12 --keep 6 --ask 300

Set MUNIM_ID_SALT to keep pseudonymised ids stable between runs.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from munim.agent import ReferenceAgent  # noqa: E402
from munim.engine import Munim, SimClock  # noqa: E402
from munim.ingest import IngestError, load_payments_csv  # noqa: E402
from munim.models import MerchantPolicy  # noqa: E402
from munim.money import fmt_inr as inr  # noqa: E402
from munim.money import fmt_pct as pct  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--budget", type=int, default=500, help="weekly growth budget, rupees")
    ap.add_argument("--margin", type=int, default=12, help="gross margin, percent")
    ap.add_argument("--keep", type=int, default=6, help="margin to keep on every bill, percent")
    ap.add_argument("--ask", type=int, default=300, help="ask the owner above this worst-case spend, rupees")
    ap.add_argument("--today", type=date.fromisoformat, default=None, help="YYYY-MM-DD; default: day after the last payment")
    args = ap.parse_args()

    salt = os.environ.get("MUNIM_ID_SALT", "").encode() or os.urandom(16)
    try:
        data = load_payments_csv(pathlib.Path(args.csv), salt=salt, today=args.today)
    except (IngestError, OSError) as exc:
        print(f"Could not use {args.csv}: {exc}", file=sys.stderr)
        return 1
    r = data.report
    print(f"{r.rows} rows: {r.loaded} payments loaded, {r.rejected} rejected, {r.duplicates_dropped} duplicate(s) dropped; "
          f"{r.customers} customers, {r.first_date} to {r.last_date}")
    for line, msg in r.errors[:10]:
        print(f"  line {line}: {msg}")
    for w in r.warnings:
        print(f"  note: {w}")

    policy = MerchantPolicy(merchant_id="imported-shop", weekly_budget_paise=args.budget * 100,
                            gross_margin_bps=args.margin * 100, keep_margin_bps=args.keep * 100,
                            approval_threshold_paise=args.ask * 100)
    munim = Munim(policy, data, clock=SimClock(data.today, today_date=args.today or date.fromisoformat(r.last_date)),
                  secret=os.urandom(32))
    print("\nWhat Munim computed from your payments")
    print(f"  {'group':34s} {'customers':>9s} {'back in 14 days anyway':>23s} {'average bill':>13s}")
    for s in munim.segments.values():
        print(f"  {s.name:34s} {len(s.customer_ids):9d} {pct(s.baseline_return_bps):>23s} {inr(s.avg_basket_paise):>13s}")

    seg = munim.segment("lapsed_regulars")
    if len(seg.customer_ids) == 0:
        print("\nNo lapsed regulars in this history, so there is no win-back offer to test.")
        return 0
    agent = ReferenceAgent("your shop")
    p1 = agent.win_back_greedy(seg, policy.merchant_id, "winback-a1")
    d1 = munim.propose(p1)
    print(f"\nAgent: {inr(p1.reward_paise)} cashback on {inr(p1.min_bill_paise)}+ for {len(seg.customer_ids)} lapsed regulars, "
          f"nobody held back -> {d1.decision}")
    for reason in d1.reasons:
        print(f"  [{reason.effect}] {reason.en}")
    p2 = agent.replan(p1, d1, seg)
    if p2 is None:
        print("\nThe agent gives up: no offer worth sending fits these rules.")
        return 0
    d2 = munim.propose(p2)
    print(f"\nAgent replans: {inr(p2.reward_paise)} on {inr(p2.min_bill_paise)}+, {p2.holdout_pct}% held back -> {d2.decision}")
    for reason in d2.reasons:
        print(f"  [{reason.effect}] {reason.en}")
    print(f"\nLedger: {len(munim.ledger.entries)} entries, intact: {munim.verify_ledger()['intact']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
