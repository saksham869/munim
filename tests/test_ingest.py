"""Importing a merchant's own payments export: validation, privacy defaults, and equivalence with the engine."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from munim.agent import ReferenceAgent
from munim.engine import Munim, SimClock
from munim.ingest import IngestError, export_payments_csv, load_payments_csv
from munim.models import DENY, GATE, MerchantPolicy
from munim.simulator import SyntheticKirana

SALT = b"test-salt"
HEADER = "txn_id,date,customer_id,amount,consented,offers_30d\n"


def load(text, **kw):
    return load_payments_csv(text, salt=SALT, **kw)


def rows(*lines):
    return HEADER + "\n".join(lines) + "\n"


def test_valid_rows_load_with_days_hours_and_paise():
    data = load(rows("T1,2026-10-01T09:30:00,c1,349.50,yes,0", "T2,2026-10-03,c2,120,no,1"))
    assert [(t.day, t.hour, t.customer_id, t.amount_paise) for t in data.txns] == [(0, 9, "c1", 34_950), (2, 12, "c2", 12_000)]
    assert data.today == 3 and data.start_date == date(2026, 10, 1)
    assert data.consented == frozenset({"c1"}) and data.offers_last_30d == {"c2": 1}


@pytest.mark.parametrize("text, problem", [
    ("", "empty"),
    ("date,customer_id\n2026-10-01,c1\n", "missing column(s): amount"),
    ("customer_id,amount\nc1,100\n", "missing column(s): date"),
    (HEADER, "no valid payments"),
])
def test_unusable_files_are_refused(text, problem):
    with pytest.raises(IngestError, match=problem.replace("(", r"\(").replace(")", r"\)")):
        load(text)


def test_bad_rows_are_rejected_with_line_numbers_not_repaired():
    data = load(rows(
        "T1,2026-10-01,c1,100,yes,0",
        "T2,2026-10-01,c1,-50,yes,0",
        "T3,2026-10-01,,100,yes,0",
        "T4,01/10/2026,c1,100,yes,0",
        "T5,2026-10-01,c1,abc,yes,0",
        "T6,2026-10-01,c1,0,yes,0",
        "T7,2026-10-01,c1,250000,yes,0",
        "T8,2026-10-01,c1,100,maybe,0",
        "T9,2026-10-02,c2,100,yes,0", "T10,2026-10-02,c3,100,yes,0", "T11,2026-10-02,c4,100,yes,0",
        "T12,2026-10-02,c5,100,yes,0", "T13,2026-10-02,c6,100,yes,0", "T14,2026-10-02,c7,100,yes,0",
        "T15,2026-10-02,c8,100,yes,0",
    ))
    assert data.report.loaded == 8 and data.report.rejected == 7
    reasons = dict(data.report.errors)
    assert "refund" in reasons[3] and "missing customer_id" in reasons[4] and "not YYYY-MM-DD" in reasons[5]
    assert "not a rupee amount" in reasons[6] and "zero" in reasons[7] and "₹2,00,000" in reasons[8]
    assert "yes/no" in reasons[9]


def test_mostly_invalid_file_is_refused():
    with pytest.raises(IngestError, match="does not look like a payments export"):
        load(rows("T1,2026-10-01,c1,100,yes,0", "T2,bad,c1,100,yes,0", "T3,bad,c1,100,yes,0"))


def test_duplicate_txn_ids_are_dropped():
    data = load(rows("T1,2026-10-01,c1,100,yes,0", "T1,2026-10-01,c1,100,yes,0", "T2,2026-10-02,c1,100,yes,0"))
    assert data.report.duplicates_dropped == 1 and data.report.loaded == 2


def test_consent_is_never_assumed():
    data = load("date,customer_id,amount\n2026-10-01,c1,100\n")
    assert data.consented == frozenset()
    assert any("no 'consented' column" in w for w in data.report.warnings)


def test_latest_row_decides_consent():
    data = load(rows("T1,2026-10-01,c1,100,yes,0", "T2,2026-10-05,c1,100,no,0"))
    assert data.consented == frozenset()


@pytest.mark.parametrize("raw", ["9876543210", "+91 98765 43210", "ravi@okhdfc", "ravi@example.com"])
def test_personal_ids_are_pseudonymised_consistently(raw):
    data = load(rows(f'T1,2026-10-01,"{raw}",100,yes,0', f'T2,2026-10-04,"{raw}",120,yes,0'))
    ids = {t.customer_id for t in data.txns}
    assert len(ids) == 1 and ids.pop().startswith("h_")
    assert data.report.pseudonymised_ids == 1
    assert all(raw not in t.customer_id for t in data.txns)


def test_payments_dated_after_today_are_refused():
    with pytest.raises(IngestError, match="on or after 'today'"):
        load(rows("T1,2026-10-01,c1,100,yes,0", "T2,2026-10-10,c1,100,yes,0"), today=date(2026, 10, 5))


def test_short_history_is_flagged():
    data = load(rows("T1,2026-10-01,c1,100,yes,0"))
    assert any("days of history" in w for w in data.report.warnings)


def test_exported_history_reimports_to_the_same_segments_and_decisions():
    """The import path and the synthetic shop must give the engine identical inputs."""
    sim = SyntheticKirana(seed=2026)
    start = date(2026, 10, 23) - timedelta(days=sim.today)
    data = load(export_payments_csv(sim.txns, start, sim.consented, sim.offers_last_30d))
    assert data.today == sim.today and len(data.txns) == len(sim.txns)

    policy = MerchantPolicy(merchant_id="m", weekly_budget_paise=50_000, gross_margin_bps=1_200,
                            keep_margin_bps=600, approval_threshold_paise=30_000)
    a = Munim(policy, sim, clock=SimClock(sim.today), secret=b"k")
    b = Munim(policy, data, clock=SimClock(data.today), secret=b"k")
    assert [s.summary() for s in a.segments.values()] == [s.summary() for s in b.segments.values()]

    agent = ReferenceAgent()
    seg = b.segment("lapsed_regulars")
    p1 = agent.win_back_greedy(seg, "m", "wb-a1")
    d1 = b.propose(p1)
    assert d1.decision == DENY
    d2 = b.propose(agent.replan(p1, d1, seg))
    assert d2.decision == GATE and d2.codes(DENY) == []
