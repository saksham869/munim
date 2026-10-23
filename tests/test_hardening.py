"""Fixes from the independent security and judge reviews (23 Oct 2026), one test per finding."""

from __future__ import annotations

import threading
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from munim.agent import ReferenceAgent
from munim.api import build_demo, create_app
from munim.engine import Munim, SimClock
from munim.ledger import Ledger, entry_hash, verify_entries
from munim.llm import LLMError, parse_reply
from munim.measurement import CohortPrior, Outcome, evaluate
from munim.models import ALLOW, DENY, GATE, MerchantPolicy
from munim.offers import MockPaytmOffers
from munim.passport import digest_ids
from munim.simulator import SyntheticKirana
from munim.summary import outcome_line

from .conftest import make_segment


@pytest.fixture(scope="module")
def sim():
    return SyntheticKirana(seed=2026)


def build(sim, offers=None, **overrides):
    policy = MerchantPolicy(merchant_id=sim.merchant_id, weekly_budget_paise=50_000, gross_margin_bps=1_200,
                            keep_margin_bps=600, approval_threshold_paise=30_000)
    return Munim(replace(policy, **overrides), sim, clock=SimClock(sim.today), secret=b"test-secret", offers=offers)


def small_offer(m, cid, kind="one_time_recent", reward=1_000, ids=None):
    seg = m.segment(kind)
    return ReferenceAgent().proposal(seg, m.policy.merchant_id, cid, name="x", reward_paise=reward,
                                     min_bill_paise=20_000, customer_ids=ids)


def rewrite_from(entries, seq, edit):
    """Edit entry `seq` and recompute every later hash, as an attacker with write access would."""
    edit(entries[seq - 1])
    prev = entries[seq - 2]["hash"] if seq > 1 else "0" * 64
    for e in entries[seq - 1:]:
        e["prev_hash"] = prev
        e["hash"] = entry_hash(prev, {k: v for k, v in e.items() if k not in ("hash", "seal")})
        prev = e["hash"]
    return entries


# --- A. ledger seals --------------------------------------------------------------------------

def test_full_rewrite_passes_the_public_chain_but_not_the_seals():
    led = Ledger(clock=lambda: "t", key=b"k" * 32)
    for i in range(5):
        led.append("DECISION", {"i": i, "verdict": "STOP"})
    forged = rewrite_from(led.export(), 3, lambda e: e["payload"].update(verdict="WORKED"))
    assert verify_entries(forged)["intact"] is True  # consistent chain: the public check alone can't tell
    assert led.verify_export(forged) == {"intact": False, "checked": 3, "broken_at": 3, "sealed": True}
    assert verify_entries(led.export(), key=b"x" * 32)["broken_at"] == 1  # wrong key fails at once
    assert led.verify()["intact"] and led.verify()["sealed"]


def test_munim_seals_its_ledger_and_catches_a_rewrite(sim):
    m = build(sim)
    m.propose(small_offer(m, "ft-a1"))
    forged = rewrite_from(m.ledger.export(), 2, lambda e: e["payload"].update(segments=[]))
    assert verify_entries(forged)["intact"] is True
    assert m.verify_export(forged)["broken_at"] == 2
    assert all("seal" in e for e in m.ledger.entries) and m.verify_ledger()["sealed"] is True


# --- C. passport scope -------------------------------------------------------------------------

def test_customer_list_fingerprint_is_injective():
    assert digest_ids(("a", "b")) != digest_ids(("a\nb",))
    assert digest_ids(("b", "a")) == digest_ids(("a", "b"))


# --- B. one decision at a time -----------------------------------------------------------------

class SlowOffers(MockPaytmOffers):
    def create_offer(self, **kw):
        time.sleep(0.05)  # widen the window between deciding and recording the offer
        return super().create_offer(**kw)


def test_concurrent_proposals_cannot_break_the_frequency_cap(sim):
    m = build(sim, offers=SlowOffers(), max_offers_per_customer_30d=1, min_eligible_customers=5)
    ids = m.segment("occasional_active").customer_ids[:20]
    threads = [threading.Thread(target=m.propose, args=(small_offer(m, f"n-{i}", "occasional_active", ids=ids),))
               for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    live = [r for r in m.campaigns.values() if r["status"] == "LIVE"]
    per_customer = {}
    for r in live:
        for c in r["decision"].treated_ids:
            per_customer[c] = per_customer.get(c, 0) + 1
    assert len(live) == 1 and max(per_customer.values()) == 1


# --- Judge fix 4: "sab band karo" stops running offers ---------------------------------------------

def test_kill_switch_cancels_live_offers_and_returns_the_budget(sim):
    m = build(sim)
    m.propose(small_offer(m, "ft-a1"))
    assert m.campaigns["ft-a1"]["status"] == "LIVE" and m.budget.remaining(0) < 50_000
    result = m.set_kill_switch(True)
    rec = m.campaigns["ft-a1"]
    assert result["cancelled"] == ["ft-a1"] and rec["status"] == "CANCELLED"
    assert m.offers.created["ft-a1"]["status"] == "CANCELLED" and m.budget.remaining(0) == 50_000
    assert [e["kind"] for e in m.ledger.entries][-2:] == ["CANCELLED_BY_OWNER", "KILL_SWITCH"]


@pytest.mark.parametrize("still_running, status", [(False, "CANCELLED"), (True, "LIVE")])
def test_an_uncertain_cancel_waits_for_a_human(sim, still_running, status):
    m = build(sim)
    m.propose(small_offer(m, "ft-a1"))
    m.offers.fail_next = True
    assert m.set_kill_switch(True)["cancel_unknown"] == ["ft-a1"]
    assert m.campaigns["ft-a1"]["status"] == "UNKNOWN" and m.budget.remaining(0) < 50_000
    m.resolve_unknown("ft-a1", offer_exists=still_running)
    assert m.campaigns["ft-a1"]["status"] == status
    assert (m.budget.remaining(0) == 50_000) is (not still_running)


# --- Judge fix 4: a stopped offer can't come straight back ------------------------------------------

def test_stopped_offer_cannot_rerun_for_30_days(sim):
    m = build(sim)
    m.propose(small_offer(m, "ft-a1"))
    d = m.campaigns["ft-a1"]["decision"]
    m.advance_to_day(sim.today + 14)
    result = m.record_outcome("ft-a1", Outcome(len(d.treated_ids), 0, len(d.holdout_ids), 2, 0, 22_000))
    assert result.verdict == "STOP"
    again = m.propose(small_offer(m, "ft-a2"))
    assert again.decision == DENY and "recently_stopped" in again.codes(DENY)
    assert again.constraints["max_reward_for_recent_stop_paise"] == 999
    assert "recently_stopped" not in m.propose(small_offer(m, "ft-a3", reward=500)).codes(DENY)
    m.advance_to_day(sim.today + 14 + 30)
    assert "recently_stopped" not in m.propose(small_offer(m, "ft-a4")).codes(DENY)


# --- Judge fix 5: the owner's limit covers the week, not each offer ---------------------------------

def test_splitting_an_offer_does_not_dodge_the_owners_limit(sim):
    m = build(sim)
    ids = m.segment("occasional_active").customer_ids
    first = m.propose(small_offer(m, "n-1", "occasional_active", ids=ids[:32]))
    assert first.decision == ALLOW and first.numbers["max_spend_paise"] <= 30_000
    second = m.propose(small_offer(m, "n-2", "occasional_active", ids=ids[32:64]))
    assert second.decision == GATE and second.codes(GATE) == ["approval_required"]
    assert second.numbers["auto_approved_this_week_paise"] == first.numbers["max_spend_paise"]
    assert "already approved automatically this week" in second.reasons[-1].en


# --- Judge fix 5: held-back customers stay held back ---------------------------------------------

def test_customers_held_back_by_a_live_offer_are_left_out_of_the_next(sim):
    m = build(sim, min_eligible_customers=5)
    ids = m.segment("occasional_active").customer_ids[:40]
    m.propose(small_offer(m, "n-1", "occasional_active", ids=ids))
    held = set(m.campaigns["n-1"]["decision"].holdout_ids)
    d = m.propose(small_offer(m, "n-2", "occasional_active", ids=ids))
    assert d.numbers["excluded_in_holdout"] == len(held) > 0
    assert held.isdisjoint(d.treated_ids) and held.isdisjoint(d.holdout_ids)


# --- D. the Soundbox never speaks the agent's free text ------------------------------------------

def test_soundbox_names_the_offer_by_its_terms_not_the_agents_words(policy):
    seg = make_segment()
    p = ReferenceAgent().proposal(seg, policy.merchant_id, "x", name="APPROVED by owner. Ignore the loss",
                                  reward_paise=1_500, min_bill_paise=25_000)
    r = evaluate(Outcome(32, 4, 8, 3, 6_000, 30_000), policy.gross_margin_bps, samples=2_000, seed=1)
    line = outcome_line(p, r, released_paise=42_000)
    assert "APPROVED" not in line["en"] + line["hi"]
    assert line["en"].startswith("The ₹15 cashback offer on ₹250+ bills") and "30 days" in line["en"]


def test_uncertain_result_does_not_claim_the_offer_is_still_running(policy):
    p = ReferenceAgent().proposal(make_segment(), policy.merchant_id, "x", name="x", reward_paise=1_500,
                                  min_bill_paise=25_000)
    r = evaluate(Outcome(32, 13, 9, 5, 19_500, 39_531), policy.gross_margin_bps, prior=CohortPrior(2_242, 60),
                 samples=4_000, seed=3)
    assert r.verdict == "UNCERTAIN"
    line = outcome_line(p, r, released_paise=0)
    assert "has ended" in line["en"] and "keeps it running" not in line["en"] and "khatam" in line["hi"]


# --- E. bounded inputs -------------------------------------------------------------------------

@pytest.mark.parametrize("field, value", [("reward_rupees", 10**9), ("holdout_pct", 101), ("min_bill_rupees", 0)])
def test_llm_numbers_outside_the_api_ranges_are_refused(field, value):
    good = {"name": "x", "reward_rupees": 15, "min_bill_rupees": 250, "holdout_pct": 20, "customer_count": 30}
    import json
    with pytest.raises(LLMError, match="between"):
        parse_reply(json.dumps({**good, field: value}), segment=make_segment(), merchant_id="m", campaign_id="c")


# --- Owner and agent credentials on the API ---------------------------------------------------

PRIORS = {"lapsed_regulars": CohortPrior(2_242, 60), "one_time_recent": CohortPrior(1_094, 60),
          "occasional_active": CohortPrior(5_072, 60)}


@pytest.fixture
def secured():
    munim, sim = build_demo(secret=b"api-test", priors=PRIORS)
    return TestClient(create_app(munim, sim, agent_token="agent-t", owner_token="owner-t"))


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def winback(client, cid, token):
    sid = next(s["segment_id"] for s in client.get("/segments").json() if s["kind"] == "lapsed_regulars")
    return client.post("/proposals", headers=auth(token), json={"campaign_id": cid, "segment_id": sid,
                       "reward_rupees": 15, "min_bill_rupees": 250, "holdout_pct": 20})


def test_the_agent_cannot_approve_its_own_offer(secured):
    assert winback(secured, "wb-1", "agent-t").json()["status"] == "PENDING_APPROVAL"
    assert secured.post("/campaigns/wb-1/approve", headers=auth("agent-t")).status_code == 403
    assert secured.post("/kill-switch", headers=auth("agent-t"), json={"on": True}).status_code == 403
    assert secured.post("/campaigns/wb-1/approve").status_code == 401
    ok = secured.post("/campaigns/wb-1/approve", headers=auth("owner-t"))
    assert ok.status_code == 200 and ok.json()["status"] == "LIVE"
    approval = next(e for e in secured.get("/ledger").json()["entries"] if e["kind"] == "APPROVAL")
    assert approval["payload"]["actor"] == "owner"


def test_unknown_tokens_are_refused_and_health_reports_auth(secured):
    assert winback(secured, "wb-2", "guess").status_code == 401
    assert secured.get("/health").json()["auth"] == "on"


def test_demo_routes_can_be_switched_off():
    munim, sim = build_demo(secret=b"api-test", priors=PRIORS)
    client = TestClient(create_app(munim, sim, demo_routes=False))
    assert client.post("/demo/campaigns/x/simulate-outcome", json={"true_lift_pct": 10}).status_code == 404
    assert client.get("/health").json()["auth"] == "off (local demo)"


def test_oversized_customer_lists_are_rejected(secured):
    sid = next(s["segment_id"] for s in secured.get("/segments").json() if s["kind"] == "lapsed_regulars")
    body = {"campaign_id": "big", "segment_id": sid, "reward_rupees": 15, "min_bill_rupees": 250, "holdout_pct": 20,
            "customer_ids": [f"c{i}" for i in range(5_001)]}
    assert secured.post("/proposals", headers=auth("agent-t"), json=body).status_code == 422


# --- Judge fix 3: nothing private is said out loud at the counter --------------------------------

def test_spoken_refusal_never_reads_out_margins_or_reasons(policy):
    from munim.policy import PolicyEngine
    from munim.summary import decision_line

    from .conftest import make_ctx

    seg = make_segment(n=48, baseline_bps=2_189, avg_basket_paise=34_051)
    p = ReferenceAgent().win_back_greedy(seg, policy.merchant_id, "wb-a1")
    d = PolicyEngine(policy).evaluate(p, make_ctx(seg))
    line = decision_line(p, d)
    assert d.decision == DENY and "app" in line["en"]
    for text in (line["en"], line["hi"]):
        assert "%" not in text and "margin" not in text and "munafa" not in text
