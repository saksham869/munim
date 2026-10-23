"""Budget, passport and ledger: the controls between a decision and money moving."""

from __future__ import annotations

import threading
from dataclasses import replace

import pytest

from munim.budget import BudgetError, WeeklyBudget
from munim.ledger import Ledger, verify_entries
from munim.passport import PassportError, PassportIssuer

# ------------------------------------------------------------------ budget


def test_budget_reserve_settle_release():
    b = WeeklyBudget(50_000)
    assert b.commit("a", 30_000, week=0) == 20_000
    assert b.remaining(0) == 20_000
    assert b.settle("a", 12_000) == 18_000
    assert b.remaining(0) == 38_000
    b.commit("b", 10_000, week=0)
    assert b.release("b") == 10_000
    assert b.remaining(0) == 38_000


def test_budget_refuses_overspend_and_double_booking():
    b = WeeklyBudget(50_000)
    b.commit("a", 40_000, week=0)
    with pytest.raises(BudgetError):
        b.commit("b", 10_001, week=0)
    with pytest.raises(BudgetError):
        b.commit("a", 1, week=0)
    with pytest.raises(BudgetError):
        b.settle("a", 40_001)  # spending above the reservation is a breach
    b.settle("a", 1)
    with pytest.raises(BudgetError):
        b.settle("a", 1)


def test_weeks_are_separate():
    b = WeeklyBudget(50_000)
    b.commit("a", 50_000, week=0)
    assert b.remaining(0) == 0
    assert b.remaining(1) == 50_000


def test_two_approvals_racing_for_the_last_rupees():
    b = WeeklyBudget(50_000)
    results = []

    def grab(cid):
        try:
            b.commit(cid, 30_000, week=0)
            results.append(cid)
        except BudgetError:
            pass

    threads = [threading.Thread(target=grab, args=(f"c{i}",)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 1
    assert b.remaining(0) == 20_000


# ------------------------------------------------------------------ passport


class FakeClock:
    def __init__(self):
        self.t = 1_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def issuer():
    clock = FakeClock()
    return PassportIssuer(b"k" * 32, ttl_seconds=60, clock=clock), clock


def issue(issuer, ids=("c1", "c2")):
    return issuer.issue(campaign_id="camp", merchant_id="m", reward_paise=1_500, min_bill_paise=25_000,
                        max_spend_paise=3_000, treated_ids=ids, policy_fingerprint="fp1")


def test_valid_passport_is_accepted_once(issuer):
    iss, _ = issuer
    p = issue(iss)
    iss.consume(p, policy_fingerprint="fp1", treated_ids=("c2", "c1"))
    with pytest.raises(PassportError) as e:
        iss.consume(p, policy_fingerprint="fp1", treated_ids=("c1", "c2"))
    assert e.value.code == "replayed"


@pytest.mark.parametrize("field,value", [("max_spend_paise", 999_999), ("reward_paise", 5_000), ("campaign_id", "other")])
def test_edited_passport_is_rejected(issuer, field, value):
    iss, _ = issuer
    forged = replace(issue(iss), **{field: value})
    with pytest.raises(PassportError) as e:
        iss.verify(forged, policy_fingerprint="fp1", treated_ids=("c1", "c2"))
    assert e.value.code == "bad_signature"


def test_passport_signed_with_another_key_is_rejected(issuer):
    iss, clock = issuer
    other = PassportIssuer(b"x" * 32, ttl_seconds=60, clock=clock)
    with pytest.raises(PassportError) as e:
        iss.verify(issue(other), policy_fingerprint="fp1", treated_ids=("c1", "c2"))
    assert e.value.code == "bad_signature"


def test_expired_passport_is_rejected(issuer):
    iss, clock = issuer
    p = issue(iss)
    clock.t += 61
    with pytest.raises(PassportError) as e:
        iss.verify(p, policy_fingerprint="fp1", treated_ids=("c1", "c2"))
    assert e.value.code == "expired"


def test_passport_from_an_old_policy_is_rejected(issuer):
    iss, _ = issuer
    with pytest.raises(PassportError) as e:
        iss.verify(issue(iss), policy_fingerprint="fp2", treated_ids=("c1", "c2"))
    assert e.value.code == "stale_policy"


def test_passport_cannot_be_stretched_to_more_customers(issuer):
    iss, _ = issuer
    with pytest.raises(PassportError) as e:
        iss.verify(issue(iss), policy_fingerprint="fp1", treated_ids=("c1", "c2", "c3"))
    assert e.value.code == "scope_mismatch"


# ------------------------------------------------------------------ ledger


@pytest.fixture
def ledger():
    led = Ledger(clock=lambda: "2026-10-23T09:00+05:30")
    for i in range(5):
        led.append("DECISION", {"campaign_id": f"c{i}", "decision": "DENY" if i % 2 else "ALLOW", "spend": i * 100})
    return led


def test_untouched_ledger_verifies(ledger):
    assert ledger.verify() == {"intact": True, "checked": 5, "broken_at": None}


def test_edited_entry_is_detected(ledger):
    entries = ledger.export()
    assert entries[2]["payload"]["decision"] == "ALLOW"
    entries[2]["payload"]["decision"] = "DENY"
    assert verify_entries(entries)["broken_at"] == 3


def test_recomputed_hash_still_breaks_the_next_link(ledger):
    from munim.ledger import entry_hash

    entries = ledger.export()
    entries[1]["payload"]["spend"] = 0
    body = {k: v for k, v in entries[1].items() if k != "hash"}
    entries[1]["hash"] = entry_hash(entries[1]["prev_hash"], body)
    assert verify_entries(entries)["broken_at"] == 3


def test_deleted_or_reordered_entries_are_detected(ledger):
    entries = ledger.export()
    assert verify_entries(entries[:2] + entries[3:])["intact"] is False
    entries[1], entries[2] = entries[2], entries[1]
    assert verify_entries(entries)["intact"] is False


def test_export_is_a_copy(ledger):
    entries = ledger.export()
    entries[0]["payload"]["decision"] = "HACKED"
    assert ledger.verify()["intact"] is True
