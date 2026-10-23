#!/usr/bin/env python3
"""End-to-end walkthrough on a synthetic kirana.

Prints the story and writes docs/data/scenario.json, which the browser demo
replays. Every number on the demo page comes from this run of the engine.

    python3 scripts/demo.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from munim import __version__  # noqa: E402
from munim.agent import ReferenceAgent  # noqa: E402
from munim.engine import Munim, SimClock  # noqa: E402
from munim.ledger import entry_hash, verify_entries  # noqa: E402
from munim.measurement import evaluate, stable_seed  # noqa: E402
from munim.models import MerchantPolicy  # noqa: E402
from munim.money import fmt_inr as inr  # noqa: E402
from munim.simulator import SyntheticKirana, pooled_priors  # noqa: E402
from munim.summary import decision_line, outcome_line, policy_line  # noqa: E402

TRUE_LIFT_WINBACK = 0.20  # ground truth for the simulation: the win-back offer really works
TRUE_LIFT_NUDGE = 0.0  # ground truth: nudging occasional shoppers does nothing

VOICE_RULES = (
    "Munim, har hafte ₹500 tak growth pe laga sakte ho. Har bill pe kam se kam 6% munafa bachna chahiye. "
    "₹300 se upar ka kharch ho toh pehle mujhse poochna."
)


def members_view(segment, sim, cap: int) -> list:
    return [
        {"consented": sim.customers[c].consented, "capped": sim.customers[c].offers_30d >= cap}
        for c in segment.customer_ids
    ]


def proposal_view(p) -> dict:
    d = p.to_dict()
    d["segment_name"] = None
    return d


def run(seed: int, quiet: bool) -> dict:
    def say(*parts):
        if not quiet:
            print(*parts)

    sim = SyntheticKirana(seed=seed)
    priors = pooled_priors()
    policy = MerchantPolicy(
        merchant_id=sim.merchant_id,
        weekly_budget_paise=50_000,
        gross_margin_bps=1_200,
        keep_margin_bps=600,
        approval_threshold_paise=30_000,
    )
    clock = SimClock(sim.today)
    start = clock.day
    # Fixed secret and seeded passport nonces so the demo is identical on every run.
    # Production uses a random secret from a vault and random nonces.
    secret = b"munim-demo-secret-not-for-production"
    counter = iter(range(1, 1_000_000))
    munim = Munim(policy, sim, clock=clock, secret=secret, priors=priors,
                  nonce_source=lambda: hashlib.sha256(secret + str(next(counter)).encode()).hexdigest()[:24])
    agent = ReferenceAgent(sim.display_name)
    steps = []

    def step(kind: str, title: str, actor: str, **data) -> dict:
        entry = {"kind": kind, "title": title, "actor": actor, "day": clock.day - start, "date": clock.label(),
                 "ledger_seq": len(munim.ledger.entries), "ledger_head": munim.ledger.head(), **data}
        steps.append(entry)
        say(f"\n[{entry['date']}] {title}")
        if "soundbox" in data:
            say(f"   Soundbox: {data['soundbox']['hi']}")
            say(f"             {data['soundbox']['en']}")
        if "decision" in data:
            dd = data["decision"]
            say(f"   Munim: {dd['decision']}  ({', '.join(r['code'] for r in dd['reasons'])})")
            for r in dd["reasons"]:
                say(f"     - [{r['effect']}] {r['en']}")
        return entry

    # 1. Rules, set once by voice.
    step("policy", "The shop owner sets the rules, once, by voice", "merchant",
         voice=VOICE_RULES, policy=policy.to_dict(), soundbox=policy_line(policy))

    # 2. Trusted insights from the payment history.
    lapsed = munim.segment("lapsed_regulars")
    occasional = munim.segment("occasional_active")
    ids = set(lapsed.customer_ids)
    before = sum(t.amount_paise for t in sim.txns if t.customer_id in ids and start - 111 < t.day <= start - 21)
    monthly = round(before / 3 / 100_000) * 100_000  # to the nearest ₹1,000: it's an estimate
    step("insight", "Munim reads 6 months of Paytm payments", "munim",
         segments=[{**s.summary(), "members": members_view(s, sim, policy.max_offers_per_customer_30d)}
                   for s in munim.segments.values()],
         highlight={"segment_id": lapsed.segment_id, "monthly_spend_before_paise": monthly},
         merchant={"name": sim.display_name, "city": sim.city, "txns": len(sim.txns),
                   "customers": len({t.customer_id for t in sim.txns}),
                   "avg_bill_paise": round(sum(t.amount_paise for t in sim.txns) / len(sim.txns))},
         soundbox={
             "hi": f"{len(lapsed.customer_ids)} purane regular grahak 3 hafte se nahi aaye. Pehle ye milkar "
                   f"mahine mein lagbhag {inr(monthly)} ka saaman lete the.",
             "en": f"{len(lapsed.customer_ids)} regulars haven't been in for 3+ weeks. Together they used to "
                   f"spend about {inr(monthly)} a month here.",
         })

    # 3. The agent's first, greedy attempt.
    p1 = agent.win_back_greedy(lapsed, policy.merchant_id, "winback-a1")
    d1 = munim.propose(p1)
    step("decision", "The growth agent asks for too much", "agent",
         proposal=p1.to_dict(), decision=d1.to_dict(), soundbox=decision_line(p1, d1))

    # 4. It replans from Munim's constraints.
    p2 = agent.replan(p1, d1, lapsed)
    d2 = munim.propose(p2)
    step("decision", "The agent replans inside Munim's limits", "agent",
         proposal=p2.to_dict(), decision=d2.to_dict(), soundbox=decision_line(p2, d2))

    # 5. Owner approves on the Soundbox; Munim re-checks before spending.
    d2b = munim.approve(p2.campaign_id)
    rec_a = munim.campaigns[p2.campaign_id]
    step("approval", "Owner taps 'Haan'. Munim re-checks, reserves budget, issues a passport", "merchant",
         decision=d2b.to_dict(), status=rec_a["status"], passport=rec_a["passport"].public(),
         offer=rec_a.get("offer"),
         soundbox={"hi": f"Offer chalu. {d2b.numbers['treated']} grahakon ko WhatsApp par bheja gaya. "
                         f"{d2b.numbers['holdout']} grahak tulna ke liye bina offer ke.",
                   "en": f"Offer live. Sent to {d2b.numbers['treated']} customers. "
                         f"{d2b.numbers['holdout']} kept without the offer for comparison."})

    # 6. A week later: a second idea that would mostly pay people who come anyway.
    munim.advance_to_day(start + 7)
    p3 = agent.proposal(occasional, policy.merchant_id, "nudge-a1", name="Nudge occasional shoppers",
                        reward_paise=1_200, min_bill_paise=20_000, holdout_pct=20,
                        customer_ids=occasional.customer_ids[:30],
                        message=f"{sim.display_name}: ₹200+ ki khareed par ₹12 cashback, 14 din tak.",
                        rationale="Occasional shoppers could visit more often with a small reward.")
    d3 = munim.propose(p3)
    step("decision", "A second idea: cashback for shoppers who come anyway", "agent",
         proposal=p3.to_dict(), decision=d3.to_dict(), soundbox=decision_line(p3, d3))

    p4 = agent.replan(p3, d3, occasional)
    d4 = munim.propose(p4)
    step("decision", "Smaller reward: inside the rules, so Munim lets it run, and measures it", "agent",
         proposal=p4.to_dict(), decision=d4.to_dict(), soundbox=decision_line(p4, d4))

    # 7. Day 14: win-back results against the holdout.
    munim.advance_to_day(start + 14)
    out_a, truth_a = sim.simulate_campaign(
        treated=rec_a["decision"].treated_ids, holdout=rec_a["decision"].holdout_ids, start_day=rec_a["live_day"],
        window_days=p2.validity_days, true_lift=TRUE_LIFT_WINBACK, min_bill_paise=p2.min_bill_paise,
        reward_paise=p2.reward_paise, seed=stable_seed("sim:" + p2.campaign_id))
    res_a = munim.record_outcome(p2.campaign_id, out_a)
    solo_a = evaluate(out_a, policy.gross_margin_bps, prior=None, seed=stable_seed(p2.campaign_id))
    step("outcome", "Day 14: did the win-back offer make money?", "munim",
         campaign_id=p2.campaign_id, name=p2.name, outcome=out_a.__dict__, result=res_a.to_dict(),
         solo=solo_a.to_dict(), truth=truth_a, status=rec_a["status"], released_paise=rec_a["released_paise"],
         soundbox=outcome_line(p2, res_a, rec_a["released_paise"]))

    # 8. Day 21: the nudge results.
    munim.advance_to_day(start + 21)
    rec_b = munim.campaigns[p4.campaign_id]
    out_b, truth_b = sim.simulate_campaign(
        treated=rec_b["decision"].treated_ids, holdout=rec_b["decision"].holdout_ids, start_day=rec_b["live_day"],
        window_days=p4.validity_days, true_lift=TRUE_LIFT_NUDGE, min_bill_paise=p4.min_bill_paise,
        reward_paise=p4.reward_paise, seed=stable_seed("sim:" + p4.campaign_id))
    res_b = munim.record_outcome(p4.campaign_id, out_b)
    solo_b = evaluate(out_b, policy.gross_margin_bps, prior=None, seed=stable_seed(p4.campaign_id))
    step("outcome", "Day 21: did the nudge make money?", "munim",
         campaign_id=p4.campaign_id, name=p4.name, outcome=out_b.__dict__, result=res_b.to_dict(),
         solo=solo_b.to_dict(), truth=truth_b, status=rec_b["status"], released_paise=rec_b["released_paise"],
         soundbox=outcome_line(p4, res_b, rec_b["released_paise"]))

    # 9. Kill switch.
    kill = munim.set_kill_switch(True)
    n_cancelled = len(kill["cancelled"])
    running_hi = f"{n_cancelled} chalu offer band kar diye. " if n_cancelled else "Abhi koi offer chalu nahi hai. "
    running_en = f"{n_cancelled} running offer(s) cancelled. " if n_cancelled else "Nothing is running right now. "
    step("kill", "Owner: 'Munim, sab band karo'", "merchant", cancelled=kill["cancelled"],
         soundbox={"hi": f"Theek hai. {running_hi}Ab koi bhi naya offer aapki manzoori ke bina nahi chalega.",
                   "en": f"Done. {running_en}No new offer runs without your approval."})
    first_timers = munim.segment("one_time_recent")
    p5 = agent.proposal(first_timers, policy.merchant_id, "firsttime-a1", name="Bring first-timers back",
                        reward_paise=1_000, min_bill_paise=20_000, holdout_pct=20,
                        message=f"{sim.display_name} mein dobara aaiye! ₹200+ ki khareed par ₹10 cashback.",
                        rationale="First-time customers rarely return on their own; a small reward may start a habit.")
    d5 = munim.propose(p5)
    step("decision", "The agent's next idea would be allowed, but spending is paused", "agent",
         proposal=p5.to_dict(), decision=d5.to_dict(), soundbox=decision_line(p5, d5))

    # 10. Audit: the chain verifies, and a quiet edit is caught.
    verify = munim.verify_ledger()
    tampered = munim.ledger.export()
    target = next(e for e in tampered if e["kind"] == "OUTCOME" and e["payload"]["campaign_id"] == p4.campaign_id)
    target["payload"]["result"]["verdict"] = "WORKED"
    tamper = verify_entries(tampered)
    # A determined attacker edits the same entry and recomputes every later hash: the public chain then
    # checks out, but the seals (HMAC under Munim's key) do not.
    rewritten = munim.ledger.export()
    seq = target["seq"]
    rewritten[seq - 1]["payload"]["result"]["verdict"] = "WORKED"
    prev = rewritten[seq - 2]["hash"]
    for e in rewritten[seq - 1:]:
        e["prev_hash"] = prev
        e["hash"] = entry_hash(prev, {k: v for k, v in e.items() if k not in ("hash", "seal")})
        prev = e["hash"]
    rewrite = {"public": verify_entries(rewritten), "sealed": munim.verify_export(rewritten)}
    step("audit", "Anyone can check the record. Quiet edits break the chain.", "auditor",
         verify=verify, tamper={"edited_seq": target["seq"], "edit": "nudge verdict STOP -> WORKED", **tamper},
         rewrite=rewrite, kinds=[e["kind"] for e in munim.ledger.entries])

    say(f"\nLedger: {verify}  |  tamper test: {tamper}")
    return {
        "generated_by": "scripts/demo.py",
        "engine_version": __version__,
        "seed": seed,
        "synthetic": True,
        "ground_truth": {"winback_true_lift_bps": round(TRUE_LIFT_WINBACK * 10_000),
                         "nudge_true_lift_bps": round(TRUE_LIFT_NUDGE * 10_000)},
        "priors": {k: v.__dict__ for k, v in priors.items()},
        "policy": policy.to_dict(),
        "steps": steps,
        "ledger": {"entries": len(munim.ledger.entries), "head": munim.ledger.head(), "verify": verify},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", default=str(ROOT / "docs" / "data" / "scenario.json"))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    scenario = run(args.seed, args.quiet)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(scenario, ensure_ascii=False, indent=1))
    # Same data as a script, so docs/index.html also works when opened straight from disk.
    out.with_suffix(".js").write_text("window.MUNIM_SCENARIO = " + json.dumps(scenario, ensure_ascii=False) + ";\n")
    if not args.quiet:
        print(f"\nWrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")


if __name__ == "__main__":
    main()
