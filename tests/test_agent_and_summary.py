from __future__ import annotations

from munim.agent import ReferenceAgent
from munim.measurement import Outcome, evaluate
from munim.models import DENY, GATE
from munim.policy import PolicyEngine
from munim.summary import decision_line, outcome_line, policy_line

from .conftest import make_ctx, make_segment


def test_replan_uses_munims_constraints_and_lands_inside_the_rules(policy):
    seg = make_segment(n=48, baseline_bps=2_189, avg_basket_paise=34_051)
    agent = ReferenceAgent()
    engine = PolicyEngine(policy)
    p1 = agent.win_back_greedy(seg, policy.merchant_id, "wb-a1")
    d1 = engine.evaluate(p1, make_ctx(seg))
    assert d1.decision == DENY
    p2 = agent.replan(p1, d1, seg)
    assert (p2.reward_paise, p2.min_bill_paise, p2.holdout_pct) == (1_500, 25_000, 20)
    assert p2.campaign_id == "wb-a2" and p2.attempt == 2
    d2 = engine.evaluate(p2, make_ctx(seg))
    assert d2.decision == GATE and d2.codes(DENY) == []


def test_replan_gives_up_when_nothing_worthwhile_fits(policy):
    seg = make_segment(baseline_bps=9_000)
    agent = ReferenceAgent()
    p1 = agent.proposal(seg, policy.merchant_id, "x-a1", name="x", reward_paise=1_500, min_bill_paise=25_000)
    d1 = PolicyEngine(policy).evaluate(p1, make_ctx(seg))
    assert d1.decision == DENY
    assert agent.replan(p1, d1, seg) is None


def test_lines_quote_engine_numbers(policy):
    seg = make_segment()
    agent = ReferenceAgent()
    p = agent.proposal(seg, policy.merchant_id, "x-a1", name="Test offer", reward_paise=1_500, min_bill_paise=25_000)
    d = PolicyEngine(policy).evaluate(p, make_ctx(seg))
    line = decision_line(p, d)
    assert "₹480" in line["en"] and "₹480" in line["hi"]
    assert "₹500" in policy_line(policy)["hi"]
    r = evaluate(Outcome(32, 4, 8, 3, 6_000, 30_000), policy.gross_margin_bps, samples=2_000, seed=1)
    out = outcome_line(p, r, released_paise=42_000)
    assert r.verdict == "STOP" and "₹420" in out["en"] and "band" in out["hi"]
