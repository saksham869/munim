"""The browser demo (docs/rules.js) must decide exactly what the Python engine decides.

Runs both on the same cases, including random policies and proposals, and
compares the decision, every reason (code, effect, English and Hinglish text),
every constraint and every number. Skipped when Node.js is not installed.
"""

from __future__ import annotations

import json
import pathlib
import random
import shutil
import subprocess

import pytest

from munim.agent import ReferenceAgent
from munim.models import CampaignProposal, MerchantPolicy, Segment
from munim.money import fmt_inr, fmt_pct, fmt_pp
from munim.policy import EvalContext, PolicyEngine

ROOT = pathlib.Path(__file__).resolve().parents[1]
RULES_JS = ROOT / "docs" / "rules.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js not installed")

RUNNER = r"""
const rules = require(process.argv[1]);
let input = "";
process.stdin.on("data", (d) => (input += d));
process.stdin.on("end", () => {
  const job = JSON.parse(input);
  const decisions = job.cases.map((c) => rules.evaluate(c.policy, c.proposal, c.ctx));
  const replans = job.cases.map((c, i) => rules.replan(c.previous, decisions[i]));
  const formats = job.formats.map(([kind, value, opts]) =>
    kind === "inr" ? rules.fmtInr(value, opts) : kind === "pct" ? rules.fmtPct(value) : rules.fmtPp(value));
  process.stdout.write(JSON.stringify({ decisions, replans, formats }));
});
"""


def run_js(cases: list, formats: list) -> dict:
    job = json.dumps({"cases": cases, "formats": formats})
    out = subprocess.run([NODE, "-e", RUNNER, str(RULES_JS)], input=job, capture_output=True, text=True,
                         check=True, timeout=60)
    return json.loads(out.stdout)


KINDS = ("lapsed_regulars", "one_time_recent", "occasional_active")


def build_case(*, policy: MerchantPolicy, n: int, baseline: int, basket: int, window: int, consented: list,
               offers: list, targeted: list, reward: int, min_bill: int, holdout: int, validity: int,
               remaining: int, kill: bool, cid: str, kind: str = "lapsed_regulars", auto: int = 0,
               stops: tuple = (), held: list | None = None) -> tuple:
    held = held or [False] * n
    ids = tuple(f"c{i:03d}" for i in range(n))
    seg = Segment(segment_id="seg@parity", kind=kind, name="parity", description="parity",
                  customer_ids=ids, baseline_return_bps=baseline, avg_basket_paise=basket, window_days=window)
    chosen = tuple(ids[i] for i in targeted)
    proposal = CampaignProposal(campaign_id=cid, merchant_id=policy.merchant_id, segment_id=seg.segment_id,
                                name="parity", customer_ids=chosen, reward_paise=reward, min_bill_paise=min_bill,
                                holdout_pct=holdout, validity_days=validity)
    ctx = EvalContext(segment=seg, consented=frozenset(ids[i] for i in range(n) if consented[i]),
                      offers_last_30d={ids[i]: offers[i] for i in range(n) if offers[i]},
                      remaining_budget_paise=remaining, kill_switch=kill, holdout_salt=b"parity",
                      auto_approved_paise=auto, recent_stops=tuple(stops),
                      in_active_holdout=frozenset(ids[i] for i in range(n) if held[i]))
    js_case = {
        "policy": {k: v for k, v in policy.to_dict().items() if k != "fingerprint"},
        "proposal": {"campaign_id": cid, "reward_paise": reward, "min_bill_paise": min_bill, "holdout_pct": holdout,
                     "validity_days": validity,
                     "customers": [{"consented": consented[i], "offers_30d": offers[i], "in_holdout": held[i]}
                                   for i in targeted]},
        "ctx": {"segment": {"kind": kind, "window_days": window, "baseline_return_bps": baseline,
                            "avg_basket_paise": basket},
                "remaining_budget_paise": remaining, "kill_switch": kill, "auto_approved_paise": auto,
                "recent_stops": list(stops)},
        "previous": {"reward_paise": reward, "min_bill_paise": min_bill, "holdout_pct": holdout,
                     "customer_count": len(targeted)},
    }
    return proposal, seg, ctx, js_case


def random_case(rng: random.Random, i: int) -> tuple:
    gross = rng.choice([300, 800, 1_200, 1_500, 2_500, rng.randint(100, 4_000)])
    keep = rng.choice([0, 300, 600, gross // 2, gross, gross + 100, rng.randint(0, gross)])
    window = rng.choice([7, 14, 14, 21, 30])
    policy = MerchantPolicy(
        merchant_id="parity-shop",
        weekly_budget_paise=rng.choice([0, 20_000, 50_000, 500_000]),
        gross_margin_bps=gross,
        keep_margin_bps=keep,
        approval_threshold_paise=rng.choice([0, 10_000, 30_000, 10**7]),
        min_holdout_pct=rng.choice([0, 10, 20, 30]),
        max_holdout_pct=rng.choice([30, 50, 100]),
        max_offers_per_customer_30d=rng.choice([1, 2, 3]),
        max_plausible_lift_bps=rng.choice([500, 1_500, 2_500, 5_000]),
        max_validity_days=rng.choice([7, 14, 30]),
        min_eligible_customers=rng.choice([1, 10, 25]),
    )
    n = rng.randint(1, 120)
    consented = [rng.random() < 0.9 for _ in range(n)]
    offers = [rng.choice([0, 0, 0, 1, 2, 3]) for _ in range(n)]
    k = rng.choice([0, n, n, rng.randint(1, n)])
    targeted = sorted(rng.sample(range(n), k))
    min_bill = rng.choice([0, 10_000, 20_000, 25_000, rng.randint(-1_000, 150_000)])
    reward = rng.choice([0, 1_000, 1_500, 4_000, rng.randint(-500, 25_000), max(1, min_bill // 20)])
    return build_case(
        policy=policy, n=n, baseline=rng.choice([0, 952, 2_189, 5_132, rng.randint(0, 9_999)]),
        basket=rng.randint(2_000, 200_000), window=window, consented=consented, offers=offers, targeted=targeted,
        reward=reward, min_bill=min_bill, holdout=rng.choice([0, 20, 25, rng.randint(-5, 110)]),
        validity=rng.choice([window, window, policy.max_validity_days, rng.randint(-1, 40)]),
        remaining=rng.choice([0, 50_000, rng.randint(0, 300_000)]), kill=rng.random() < 0.2, cid=f"r{i}",
        kind=rng.choice(KINDS), auto=rng.choice([0, 0, 0, rng.randint(1, 60_000)]),
        stops=tuple({"segment_kind": rng.choice(KINDS), "reward_paise": rng.choice([500, 1_000, 1_500, rng.randint(1, 20_000)])}
                    for _ in range(rng.choice([0, 0, 1, 2]))),
        held=[rng.random() < 0.08 for _ in range(n)],
    )


def scenario_cases() -> list:
    """The proposals from the demo run, against the segments the demo computed."""
    data = json.loads((ROOT / "docs" / "data" / "scenario.json").read_text())
    pol = data["policy"]
    policy = MerchantPolicy(**{k: v for k, v in pol.items() if k != "fingerprint"})
    segments = {s["segment_id"]: s for s in next(st for st in data["steps"] if st["kind"] == "insight")["segments"]}
    cases = []
    for st in data["steps"]:
        if st["kind"] != "decision":
            continue
        prop, seg = st["proposal"], segments[st["proposal"]["segment_id"]]
        members = seg["members"][: prop["customer_count"]]
        cap = policy.max_offers_per_customer_30d
        cases.append((build_case(
            policy=policy, n=len(members), baseline=seg["baseline_return_bps"], basket=seg["avg_basket_paise"],
            window=seg["window_days"], consented=[m["consented"] for m in members],
            offers=[cap if m["capped"] else 0 for m in members], targeted=list(range(len(members))),
            reward=prop["reward_paise"], min_bill=prop["min_bill_paise"], holdout=prop["holdout_pct"],
            validity=prop["validity_days"], remaining=st["decision"]["numbers"].get("remaining_budget_paise", 50_000),
            kill=any(r["code"] == "kill_switch" for r in st["decision"]["reasons"]), cid=prop["campaign_id"],
            kind=seg["kind"], auto=st["decision"]["numbers"].get("auto_approved_this_week_paise", 0),
        ), st["decision"]))
    return cases


def python_view(proposal, seg, ctx, policy) -> dict:
    d = PolicyEngine(policy).evaluate(proposal, ctx).to_dict()
    return {k: d[k] for k in ("campaign_id", "decision", "reasons", "constraints", "numbers")}


def python_replan(proposal, seg, ctx, policy) -> dict | None:
    d = PolicyEngine(policy).evaluate(proposal, ctx)
    p2 = ReferenceAgent().replan(proposal, d, seg)
    if p2 is None:
        return None
    return {"reward_paise": p2.reward_paise, "min_bill_paise": p2.min_bill_paise, "holdout_pct": p2.holdout_pct,
            "customer_count": len(p2.customer_ids)}


FORMATS = (
    [["inr", v, None] for v in (0, 1, 49, 50, 99, 150, 1_500, 99_950, 1_00_000_00, 12_34_56_789, -25_050, -49, -50)]
    + [["inr", v, {"floor": True}] for v in (0, 1_090, 1_099, 99_999, 12_34_56_789, -1_090)]
    + [["inr", v, {"decimals": True}] for v in (0, 5, 1_090, -25_050, 12_34_56_789)]
    + [["pct", v, None] for v in (0, 5, 600, 952, 1_200, 1_210, 1_215, 2_189, -1_200, -1_250, -3, 10_000)]
    + [["pp", v, None] for v in (0, 4, 5, 1_270, 2_500, 2_895, -158, -5, 9_999)]
)


def py_format(kind, value, opts):
    if kind == "inr":
        return fmt_inr(value, **(opts or {}))
    return fmt_pct(value) if kind == "pct" else fmt_pp(value)


def test_formatters_match():
    js = run_js([], FORMATS)["formats"]
    assert js == [py_format(*f) for f in FORMATS]


def test_demo_proposals_match_the_recorded_run():
    cases = scenario_cases()
    assert len(cases) == 5
    js = run_js([c[0][3] for c in cases], [])["decisions"]
    for (case, recorded), got in zip(cases, js):
        proposal, seg, ctx, _ = case
        policy = MerchantPolicy(**{k: v for k, v in json.loads(
            (ROOT / "docs" / "data" / "scenario.json").read_text())["policy"].items() if k != "fingerprint"})
        assert got == python_view(proposal, seg, ctx, policy)
        assert got["decision"] == recorded["decision"]
        assert got["reasons"] == recorded["reasons"]
        assert got["numbers"] == recorded["numbers"]


def test_random_cases_match():
    rng = random.Random(20261023)
    built = []
    for i in range(1_500):
        proposal, seg, ctx, js_case = random_case(rng, i)
        policy = MerchantPolicy(**js_case["policy"])
        built.append((proposal, seg, ctx, js_case, policy))
    out = run_js([b[3] for b in built], [])
    decisions_seen = set()
    for (proposal, seg, ctx, js_case, policy), got, got_replan in zip(built, out["decisions"], out["replans"]):
        want = python_view(proposal, seg, ctx, policy)
        assert got == want, proposal.campaign_id
        assert got_replan == python_replan(proposal, seg, ctx, policy), proposal.campaign_id
        decisions_seen.add(got["decision"])
        decisions_seen.update(r["code"] for r in got["reasons"])
    # The random cases must actually exercise every rule, or the comparison proves little.
    for code in ("ALLOW", "GATE", "DENY", "invalid_proposal", "margin_floor", "no_measurement", "excluded_no_consent",
                 "excluded_frequency_cap", "excluded_in_holdout", "recently_stopped", "too_small_to_measure",
                 "over_budget", "cannot_pay_back", "unrealistic_payback", "approval_required", "kill_switch",
                 "within_rules"):
        assert code in decisions_seen, code


def test_js_fails_closed():
    """A well-formed proposal with a missing policy throws inside the rules; the answer is still DENY."""
    script = ("const r=require(process.argv[1]);"
              "const p={campaign_id:'x',reward_paise:1500,min_bill_paise:25000,holdout_pct:20,validity_days:14,"
              "customers:[{consented:true}]};"
              "process.stdout.write(JSON.stringify(r.evaluate(null,p,{segment:{window_days:14}})))")
    out = subprocess.run([NODE, "-e", script, str(RULES_JS)], capture_output=True, text=True, check=True, timeout=30)
    d = json.loads(out.stdout)
    assert d["decision"] == "DENY" and [r["code"] for r in d["reasons"]] == ["engine_error"]
    assert "TypeError" in d["reasons"][0]["en"]
