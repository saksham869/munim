from __future__ import annotations

from dataclasses import replace

import pytest

from munim.models import ALLOW, DENY, GATE
from munim.policy import PolicyEngine

from .conftest import make_ctx, make_proposal, make_segment


def evaluate(policy, proposal, ctx):
    return PolicyEngine(policy).evaluate(proposal, ctx)


def test_small_safe_offer_is_allowed(policy, segment):
    p = make_proposal(segment, reward=1_000, min_bill=20_000, customers=segment.customer_ids[:20])
    d = evaluate(policy, p, make_ctx(segment))
    assert d.decision == ALLOW
    assert d.codes() == ["within_rules"]
    assert d.numbers["max_spend_paise"] == 1_000 * d.numbers["treated"]


def test_big_spend_waits_for_the_merchant(policy, segment):
    d = evaluate(policy, make_proposal(segment), make_ctx(segment))  # 32 treated x ₹15 = ₹480
    assert d.decision == GATE
    assert d.codes(GATE) == ["approval_required"]


def test_margin_floor_denies_and_says_how_to_fix(policy, segment):
    d = evaluate(policy, make_proposal(segment, reward=4_000, min_bill=10_000), make_ctx(segment))
    assert d.decision == DENY
    assert "margin_floor" in d.codes(DENY)
    c = d.constraints
    assert c["max_reward_paise"] == 600
    assert c["min_bill_for_requested_reward_paise"] == 66_667
    assert c["suggested"] == {"min_bill_paise": 25_000, "reward_paise": 1_500}


def test_reward_exactly_at_ceiling_is_fine(policy, segment):
    d = evaluate(policy, make_proposal(segment, reward=1_500, min_bill=25_000), make_ctx(segment))
    assert "margin_floor" not in d.codes()


def test_no_comparison_group_is_refused(policy, segment):
    d = evaluate(policy, make_proposal(segment, holdout=10), make_ctx(segment))
    assert "no_measurement" in d.codes(DENY)
    assert d.constraints["min_holdout_pct"] == 20
    assert d.numbers["holdout_pct_used"] == 20  # numbers still sized with the minimum


def test_over_budget_returns_the_fitting_size(policy, segment):
    d = evaluate(policy, make_proposal(segment), make_ctx(segment, remaining=20_000))
    assert "over_budget" in d.codes(DENY)
    assert d.constraints["max_treated_customers"] == 13
    assert d.constraints["max_reward_for_all_paise"] == 20_000 // d.numbers["treated"]


def test_deadweight_customers_are_not_paid_to_do_what_they_do_anyway(policy):
    seg = make_segment(baseline_bps=5_500, avg_basket_paise=27_000)
    d = evaluate(policy, make_proposal(seg, reward=1_200, min_bill=20_000), make_ctx(seg))
    assert "unrealistic_payback" in d.codes(DENY)
    r_max = d.constraints["max_reward_for_payback_paise"]
    ok = evaluate(policy, make_proposal(seg, reward=r_max, min_bill=20_000, cid="camp-2"), make_ctx(seg))
    assert "unrealistic_payback" not in ok.codes()


def test_offer_that_loses_money_even_if_everyone_returns(policy, segment):
    d = evaluate(policy, make_proposal(segment, reward=4_000, min_bill=10_000), make_ctx(segment))
    assert "cannot_pay_back" in d.codes(DENY)


def test_deny_beats_gate(policy, segment):
    d = evaluate(policy, make_proposal(segment, reward=4_000, min_bill=10_000), make_ctx(segment))
    assert d.decision == DENY
    assert "approval_required" in d.codes(GATE)


def test_greedy_first_try_gets_every_reason_at_once(policy, segment):
    p = make_proposal(segment, reward=4_000, min_bill=10_000, holdout=0)
    d = evaluate(policy, p, make_ctx(segment))
    assert set(d.codes(DENY)) == {"margin_floor", "no_measurement", "over_budget", "cannot_pay_back"}


def test_consent_and_frequency_cap_filter_customers(policy, segment):
    ids = segment.customer_ids
    ctx = make_ctx(segment, consented=ids[2:], offers={ids[5]: 2, ids[6]: 1})
    d = evaluate(policy, make_proposal(segment), ctx)
    assert d.numbers["excluded_no_consent"] == 2
    assert d.numbers["excluded_frequency_cap"] == 1
    assert d.numbers["eligible"] == 37
    targeted = set(d.treated_ids) | set(d.holdout_ids)
    assert ids[0] not in targeted and ids[5] not in targeted and ids[6] in targeted
    assert {"excluded_no_consent", "excluded_frequency_cap"} <= set(d.codes("NOTE"))


def test_too_few_customers_to_measure(policy, segment):
    d = evaluate(policy, make_proposal(segment, customers=segment.customer_ids[:9]), make_ctx(segment))
    assert "too_small_to_measure" in d.codes(DENY)


@pytest.mark.parametrize("change,needle", [
    (dict(merchant_id="someone-else"), "different merchant"),
    (dict(segment_id="made-up"), "segment is not one Munim computed"),
    (dict(customer_ids=("c000", "zzz")), "outside the segment"),
    (dict(customer_ids=("c000", "c000")), "twice"),
    (dict(customer_ids=()), "no customers"),
    (dict(reward_paise=30_000, min_bill_paise=25_000), "smaller than the minimum bill"),
    (dict(reward_paise=0), "reward must be positive"),
    (dict(validity_days=7), "14-day measurement window"),
    (dict(validity_days=30), "1 to 14 days"),
    (dict(holdout_pct=80), "0 to 50%"),
    (dict(reward_paise=15.0), "whole number"),
    (dict(reward_paise=True), "whole number"),
])
def test_malformed_proposals_are_refused(policy, segment, change, needle):
    p = replace(make_proposal(segment), **change)
    d = evaluate(policy, p, make_ctx(segment))
    assert d.decision == DENY
    assert d.codes() == ["invalid_proposal"]
    assert needle in d.reasons[0].en


def test_kill_switch_turns_allow_into_gate(policy, segment):
    p = make_proposal(segment, reward=1_000, min_bill=20_000, customers=segment.customer_ids[:20])
    d = evaluate(policy, p, make_ctx(segment, kill=True))
    assert d.decision == GATE
    assert d.codes(GATE) == ["kill_switch"]


def test_kill_switch_never_weakens_a_deny(policy, segment):
    d = evaluate(policy, make_proposal(segment, holdout=0), make_ctx(segment, kill=True))
    assert d.decision == DENY


def test_engine_fails_closed(policy, segment):
    broken = replace(segment, avg_basket_paise=None)
    d = evaluate(policy, make_proposal(broken), make_ctx(broken))
    assert d.decision == DENY
    assert d.codes() == ["engine_error"]


def test_same_inputs_same_decision(policy, segment):
    a = evaluate(policy, make_proposal(segment), make_ctx(segment)).to_dict(include_ids=True)
    b = evaluate(policy, make_proposal(segment), make_ctx(segment)).to_dict(include_ids=True)
    assert a == b


def test_agent_cannot_choose_the_comparison_group(policy, segment):
    p = make_proposal(segment)
    a = evaluate(policy, p, make_ctx(segment, salt=b"secret-one"))
    b = evaluate(policy, p, make_ctx(segment, salt=b"secret-two"))
    assert len(a.holdout_ids) == len(b.holdout_ids) == 8
    assert a.holdout_ids != b.holdout_ids
    assert set(a.treated_ids).isdisjoint(a.holdout_ids)


def test_every_reason_speaks_both_languages(policy, segment):
    p = make_proposal(segment, reward=4_000, min_bill=10_000, holdout=0)
    ctx = make_ctx(segment, consented=segment.customer_ids[1:], offers={segment.customer_ids[3]: 2}, kill=True)
    for r in evaluate(policy, p, ctx).reasons:
        assert r.en and r.hi and r.en != r.hi
