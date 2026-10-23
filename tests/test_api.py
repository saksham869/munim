from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from munim.api import build_demo, create_app
from munim.measurement import CohortPrior


@pytest.fixture
def client():
    priors = {"lapsed_regulars": CohortPrior(2_242, 60), "one_time_recent": CohortPrior(1_094, 60),
              "occasional_active": CohortPrior(5_072, 60)}
    munim, sim = build_demo(secret=b"api-test", priors=priors)
    return TestClient(create_app(munim, sim))


def seg_id(client, kind):
    return next(s["segment_id"] for s in client.get("/segments").json() if s["kind"] == kind)


def test_health_and_segments(client):
    assert client.get("/health").json()["ok"] is True
    assert {s["kind"] for s in client.get("/segments").json()} == {"lapsed_regulars", "one_time_recent", "occasional_active"}


def test_full_flow_over_http(client):
    sid = seg_id(client, "lapsed_regulars")
    greedy = client.post("/proposals", json={"campaign_id": "wb-a1", "segment_id": sid, "reward_rupees": 40,
                                             "min_bill_rupees": 100, "holdout_pct": 0}).json()
    assert greedy["decision"]["decision"] == "DENY"

    ok = client.post("/proposals", json={"campaign_id": "wb-a2", "segment_id": sid, "reward_rupees": 15,
                                         "min_bill_rupees": 250, "holdout_pct": 20, "customer_count": 44}).json()
    assert ok["decision"]["decision"] == "GATE" and ok["status"] == "PENDING_APPROVAL"

    approved = client.post("/campaigns/wb-a2/approve").json()
    assert approved["status"] == "LIVE"
    assert client.post("/campaigns/wb-a2/approve").status_code == 409

    res = client.post("/demo/campaigns/wb-a2/simulate-outcome", json={"true_lift_pct": 20}).json()
    assert res["result"]["verdict"] in {"WORKED", "UNCERTAIN", "STOP"}
    assert client.get("/ledger/verify").json()["intact"] is True
    assert client.get("/campaigns/wb-a2").json()["result"] is not None


def test_kill_switch_over_http(client):
    client.post("/kill-switch", json={"on": True})
    sid = seg_id(client, "one_time_recent")
    r = client.post("/proposals", json={"campaign_id": "ft-a1", "segment_id": sid, "reward_rupees": 10,
                                        "min_bill_rupees": 200, "holdout_pct": 20}).json()
    assert r["decision"]["decision"] == "GATE"
    assert [x["code"] for x in r["decision"]["reasons"] if x["effect"] == "GATE"] == ["kill_switch"]


@pytest.mark.parametrize("bad", [
    {"reward_rupees": -5}, {"reward_rupees": 0}, {"holdout_pct": 101}, {"campaign_id": ""}, {"reward_rupees": "lots"},
])
def test_malformed_requests_never_reach_the_engine(client, bad):
    body = {"campaign_id": "x", "segment_id": seg_id(client, "one_time_recent"), "reward_rupees": 10,
            "min_bill_rupees": 200, "holdout_pct": 20, **bad}
    assert client.post("/proposals", json=body).status_code == 422


def test_unknown_campaign_is_404(client):
    assert client.post("/campaigns/nope/approve").status_code == 404
