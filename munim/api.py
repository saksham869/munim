"""HTTP API for Munim.

    uvicorn munim.api:app --port 8090

Starts with a synthetic kirana so every endpoint works with no setup.

Who may do what. Set two tokens to separate the growth agent from the owner:

    MUNIM_AGENT_TOKEN   may only create proposals
    MUNIM_OWNER_TOKEN   may also approve, reject and use the kill switch

Clients send "Authorization: Bearer <token>". With neither token set the API
runs open, as a local demo, and /health says so. The /demo routes (simulated
outcomes) exist only because the data is synthetic; MUNIM_DEMO_ROUTES=0 removes them.
"""

from __future__ import annotations

import hmac
import os
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from . import __version__
from .engine import Munim, SimClock
from .measurement import stable_seed
from .models import CampaignProposal, MerchantPolicy
from .simulator import SyntheticKirana, pooled_priors

DEMO_POLICY = dict(
    weekly_budget_paise=50_000,
    gross_margin_bps=1_200,
    keep_margin_bps=600,
    approval_threshold_paise=30_000,
)


def build_demo(seed: int = 2026, secret: Optional[bytes] = None, priors: Optional[dict] = None):
    sim = SyntheticKirana(seed=seed)
    policy = MerchantPolicy(merchant_id=sim.merchant_id, **DEMO_POLICY)
    munim = Munim(policy, sim, clock=SimClock(sim.today), secret=secret,
                  priors=pooled_priors() if priors is None else priors)
    return munim, sim


class ProposalIn(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=64)
    segment_id: str
    name: str = Field(default="Offer", max_length=80)
    customer_count: Optional[int] = Field(default=None, ge=1)
    customer_ids: Optional[List[str]] = Field(default=None, max_length=5_000)
    reward_rupees: int = Field(ge=1, le=10_000)
    min_bill_rupees: int = Field(ge=1, le=100_000)
    holdout_pct: int = Field(ge=0, le=100)
    validity_days: int = Field(default=14, ge=1, le=60)
    message: str = Field(default="", max_length=500)
    rationale: str = Field(default="", max_length=1_000)


class KillSwitchIn(BaseModel):
    on: bool


class SimOutcomeIn(BaseModel):
    true_lift_pct: float = Field(ge=0, le=60)


def create_app(munim: Optional[Munim] = None, sim: Optional[SyntheticKirana] = None, *,
               agent_token: Optional[str] = None, owner_token: Optional[str] = None,
               demo_routes: bool = True) -> FastAPI:
    if munim is None:
        munim, sim = build_demo()
    app = FastAPI(title="Munim", version=__version__,
                  description="Spending limits and a scorecard for AI growth agents acting on a merchant's money.")
    app.state.munim, app.state.sim = munim, sim
    auth_on = bool(agent_token or owner_token)

    def caller(authorization: Optional[str] = Header(default=None)) -> str:
        """Who is calling: 'owner', 'agent', or 'open' when the API runs without tokens."""
        if not auth_on:
            return "open"
        token = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
        if owner_token and hmac.compare_digest(token, owner_token):
            return "owner"
        if agent_token and hmac.compare_digest(token, agent_token):
            return "agent"
        raise HTTPException(401, "missing or unknown token")

    def owner_only(who: str = Depends(caller)) -> str:
        if who == "agent":
            raise HTTPException(403, "only the owner can do this; the growth agent can only propose")
        return "owner" if who == "owner" else "unauthenticated (demo mode)"

    def campaign_or_404(cid: str) -> dict:
        if cid not in munim.campaigns:
            raise HTTPException(404, f"unknown campaign {cid}")
        return munim.campaigns[cid]

    @app.get("/health")
    def health():
        return {"ok": True, "version": __version__, "auth": "on" if auth_on else "off (local demo)",
                "ledger": munim.verify_ledger()}

    @app.get("/policy")
    def policy():
        return munim.policy.to_dict()

    @app.get("/segments")
    def segments():
        return [s.summary() for s in munim.segments.values()]

    @app.post("/proposals")
    def propose(body: ProposalIn, who: str = Depends(caller)):
        seg = munim.segments.get(body.segment_id)
        if body.customer_ids is not None:
            ids = tuple(body.customer_ids)
        elif seg is not None:
            ids = tuple(seg.customer_ids[: body.customer_count or len(seg.customer_ids)])
        else:
            ids = ()
        proposal = CampaignProposal(
            campaign_id=body.campaign_id, merchant_id=munim.policy.merchant_id, segment_id=body.segment_id,
            name=body.name, customer_ids=ids, reward_paise=body.reward_rupees * 100,
            min_bill_paise=body.min_bill_rupees * 100, holdout_pct=body.holdout_pct,
            validity_days=body.validity_days, message=body.message, rationale=body.rationale,
            proposed_by="owner" if who == "owner" else "agent" if who == "agent" else "api (demo mode)",
        )
        decision = munim.propose(proposal)
        return {"decision": decision.to_dict(), "status": munim.campaigns.get(proposal.campaign_id, {}).get("status")}

    @app.post("/campaigns/{cid}/approve")
    def approve(cid: str, actor: str = Depends(owner_only)):
        record = campaign_or_404(cid)
        try:
            decision = munim.approve(cid, actor=actor)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return {"decision": decision.to_dict(), "status": record["status"]}

    @app.post("/campaigns/{cid}/reject")
    def reject(cid: str, actor: str = Depends(owner_only)):
        campaign_or_404(cid)
        try:
            munim.reject(cid, actor=actor)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return {"status": "REJECTED"}

    @app.get("/campaigns/{cid}")
    def campaign(cid: str):
        r = campaign_or_404(cid)
        return {
            "status": r["status"],
            "proposal": r["proposal"].to_dict(),
            "decision": r["decision"].to_dict(),
            "passport": r["passport"].public() if r.get("passport") else None,
            "result": r["result"].to_dict() if r.get("result") else None,
        }

    @app.post("/kill-switch")
    def kill_switch(body: KillSwitchIn, actor: str = Depends(owner_only)):
        result = munim.set_kill_switch(body.on, actor=actor)
        return {"kill_switch": munim.kill_switch, "cancelled": result["cancelled"],
                "cancel_unknown": result["cancel_unknown"]}

    @app.get("/ledger")
    def ledger(limit: int = 50):
        return {"entries": munim.ledger.entries[-max(1, min(limit, 500)):], **munim.verify_ledger()}

    @app.get("/ledger/verify")
    def ledger_verify():
        return munim.verify_ledger()

    @app.get("/state")
    def state():
        return munim.state()

    if not demo_routes:
        return app

    @app.post("/demo/campaigns/{cid}/simulate-outcome")
    def simulate_outcome(cid: str, body: SimOutcomeIn, actor: str = Depends(owner_only)):
        """Synthetic data only: play out the campaign window with a chosen true effect."""
        if sim is None:
            raise HTTPException(400, "no simulator attached")
        r = campaign_or_404(cid)
        if r["status"] != "LIVE":
            raise HTTPException(409, f"{cid} is {r['status']}, not LIVE")
        p, d = r["proposal"], r["decision"]
        outcome, truth = sim.simulate_campaign(
            treated=d.treated_ids, holdout=d.holdout_ids, start_day=r["live_day"], window_days=p.validity_days,
            true_lift=body.true_lift_pct / 100, min_bill_paise=p.min_bill_paise, reward_paise=p.reward_paise,
            seed=stable_seed("sim:" + cid),
        )
        munim.advance_to_day(max(munim.clock.day, r["live_day"] + p.validity_days))
        result = munim.record_outcome(cid, outcome)
        return {"result": result.to_dict(), "truth": truth, "status": r["status"]}

    return app


app = create_app(agent_token=os.environ.get("MUNIM_AGENT_TOKEN") or None,
                 owner_token=os.environ.get("MUNIM_OWNER_TOKEN") or None,
                 demo_routes=os.environ.get("MUNIM_DEMO_ROUTES", "1") != "0")
