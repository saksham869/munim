"""Munim: the orchestrator between a growth agent, the merchant, and the offer rails.

    agent proposes  ->  policy decides (ALLOW / GATE / DENY)
    GATE            ->  merchant approves  ->  policy re-checks with fresh state
    authorized      ->  budget reserved  ->  passport issued  ->  offer created
    window closes   ->  holdout measurement  ->  keep or stop  ->  budget settled
    every step      ->  hash-chained ledger
"""

from __future__ import annotations

import os
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from .budget import BudgetError, WeeklyBudget
from .insights import build_segments
from .ledger import Ledger
from .measurement import STOP, Outcome, evaluate, stable_seed
from .models import ALLOW, DENY, GATE, CampaignProposal, Decision, MerchantPolicy, Reason
from .offers import MockPaytmOffers, UpstreamUnknown
from .passport import PassportError, PassportIssuer, digest_ids
from .holdout import campaign_salt
from .policy import HUMAN_CLEARABLE, EvalContext, PolicyEngine

IST = timezone(timedelta(hours=5, minutes=30))


class SimClock:
    """Deterministic clock. `day` counts days from the start of the payment history."""

    def __init__(self, today_day: int, today_date: date = date(2026, 10, 23), hour: int = 9):
        self.day = today_day
        self._base_day = today_day
        self._base_date = today_date
        self._minute = hour * 60

    def advance_to(self, day: int, hour: int = 9) -> None:
        if day < self.day:
            raise ValueError("time only moves forward")
        self.day = day
        self._minute = hour * 60

    def tick(self, minutes: int = 1) -> None:
        self._minute += minutes

    def _dt(self) -> datetime:
        d = self._base_date + timedelta(days=self.day - self._base_day)
        return datetime(d.year, d.month, d.day, tzinfo=IST) + timedelta(minutes=self._minute)

    def now(self) -> float:
        return self._dt().timestamp()

    def iso(self) -> str:
        return self._dt().isoformat(timespec="minutes")

    def label(self) -> str:
        return self._dt().strftime("%a %d %b")


class RealClock:
    def __init__(self, today_day: int):
        self.day = today_day

    def advance_to(self, day: int, hour: int = 9) -> None:
        self.day = day

    def tick(self, minutes: int = 1) -> None:
        pass

    def now(self) -> float:
        return time.time()

    def iso(self) -> str:
        return datetime.now(IST).isoformat(timespec="seconds")

    def label(self) -> str:
        return datetime.now(IST).strftime("%a %d %b")


class Munim:
    def __init__(self, policy: MerchantPolicy, data, *, secret: bytes | None = None, offers=None, clock=None,
                 priors: dict | None = None, passport_ttl_seconds: int = 3600, nonce_source=None):
        self.data = data
        self.clock = clock or RealClock(data.today)
        self.start_day = self.clock.day
        self.policy = policy
        self._engine = PolicyEngine(policy)
        self._secret = secret or os.urandom(32)
        self.ledger = Ledger(clock=self._stamp)
        self.budget = WeeklyBudget(policy.weekly_budget_paise)
        self.passports = PassportIssuer(self._secret, passport_ttl_seconds, clock=self.clock.now,
                                        nonce_source=nonce_source)
        self.offers = offers or MockPaytmOffers()
        self.kill_switch = False
        self.priors = priors or {}
        self.campaigns: dict = {}
        self._issued: list = []  # (day, customer_id) for offers Munim itself sent
        self.segments = {s.segment_id: s for s in build_segments(data.txns, data.today)}
        self.ledger.append("POLICY_SET", {"by": "merchant", "policy": policy.to_dict()})
        self.ledger.append("INSIGHTS", {"segments": [s.summary() for s in self.segments.values()]})

    # ---------------------------------------------------------------- helpers

    def _stamp(self) -> str:
        self.clock.tick(1)
        return self.clock.iso()

    @property
    def week(self) -> int:
        return (self.clock.day - self.start_day) // 7

    def advance_to_day(self, day: int, hour: int = 9) -> None:
        self.clock.advance_to(day, hour)

    def segment(self, kind: str):
        for s in self.segments.values():
            if s.kind == kind:
                return s
        raise KeyError(kind)

    def offers_last_30d(self) -> Counter:
        counts = Counter(self.data.offers_last_30d)
        counts.update(cid for day, cid in self._issued if self.clock.day - 30 < day <= self.clock.day)
        return counts

    def context_for(self, proposal: CampaignProposal) -> EvalContext:
        return EvalContext(
            segment=self.segments.get(proposal.segment_id),
            consented=self.data.consented,
            offers_last_30d=self.offers_last_30d(),
            remaining_budget_paise=self.budget.remaining(self.week),
            kill_switch=self.kill_switch,
            holdout_salt=campaign_salt(self._secret, proposal.campaign_id),
        )

    def _get(self, campaign_id: str) -> dict:
        if campaign_id not in self.campaigns:
            raise KeyError(f"unknown campaign {campaign_id}")
        return self.campaigns[campaign_id]

    def _log_decision(self, proposal: CampaignProposal, decision: Decision, kind: str = "DECISION") -> dict:
        return self.ledger.append(
            kind,
            {
                "campaign_id": decision.campaign_id,
                "decision": decision.decision,
                "reasons": decision.codes(),
                "numbers": decision.numbers,
                "constraints": decision.constraints,
                "treated_digest": digest_ids(decision.treated_ids),
                "holdout_digest": digest_ids(decision.holdout_ids),
                "policy_fingerprint": decision.policy_fingerprint,
            },
        )

    # ---------------------------------------------------------------- flow

    def propose(self, proposal: CampaignProposal) -> Decision:
        self.ledger.append("PROPOSAL", {"campaign": proposal.to_dict()})
        if proposal.campaign_id in self.campaigns:
            decision = Decision(
                campaign_id=proposal.campaign_id,
                decision=DENY,
                reasons=[Reason("duplicate_campaign", DENY,
                                "A campaign with this id already exists; each attempt needs a new id.",
                                "Is naam ka offer pehle se hai; har koshish ka naya id chahiye.")],
                constraints={},
                numbers={},
                policy_fingerprint=self.policy.fingerprint(),
            )
            self._log_decision(proposal, decision)
            return decision

        decision = self._engine.evaluate(proposal, self.context_for(proposal))
        self._log_decision(proposal, decision)
        record = {"proposal": proposal, "decision": decision, "status": None, "proposed_day": self.clock.day}
        self.campaigns[proposal.campaign_id] = record
        if decision.decision == DENY:
            record["status"] = "DENIED"
        elif decision.decision == GATE:
            record["status"] = "PENDING_APPROVAL"
        else:
            self._authorize(record, approved_by="policy")
        return decision

    def approve(self, campaign_id: str, actor: str = "merchant") -> Decision:
        record = self._get(campaign_id)
        if record["status"] != "PENDING_APPROVAL":
            raise ValueError(f"{campaign_id} is {record['status']}, not waiting for approval")
        # Re-check with fresh state: budget, policy, consent and caps may have moved since the proposal.
        fresh = self._engine.evaluate(record["proposal"], self.context_for(record["proposal"]))
        blocking = [r.code for r in fresh.reasons
                    if r.effect == DENY or (r.effect == GATE and r.code not in HUMAN_CLEARABLE)]
        self.ledger.append("APPROVAL", {"campaign_id": campaign_id, "actor": actor,
                                        "recheck": fresh.decision, "blocking": blocking})
        record["decision"] = fresh
        if blocking:
            record["status"] = "DENIED"
            return fresh
        self._authorize(record, approved_by=actor)
        return fresh

    def reject(self, campaign_id: str, actor: str = "merchant") -> None:
        record = self._get(campaign_id)
        if record["status"] != "PENDING_APPROVAL":
            raise ValueError(f"{campaign_id} is {record['status']}, not waiting for approval")
        record["status"] = "REJECTED"
        self.ledger.append("REJECTED", {"campaign_id": campaign_id, "actor": actor})

    def _authorize(self, record: dict, approved_by: str) -> None:
        p, d = record["proposal"], record["decision"]
        max_spend = d.numbers["max_spend_paise"]
        try:
            self.budget.commit(p.campaign_id, max_spend, self.week)
        except BudgetError as exc:
            record["status"] = "DENIED"
            self.ledger.append("AUTHORIZATION_FAILED", {"campaign_id": p.campaign_id, "error": str(exc)})
            return
        passport = self.passports.issue(
            campaign_id=p.campaign_id,
            merchant_id=p.merchant_id,
            reward_paise=p.reward_paise,
            min_bill_paise=p.min_bill_paise,
            max_spend_paise=max_spend,
            treated_ids=d.treated_ids,
            policy_fingerprint=self.policy.fingerprint(),
        )
        record.update(passport=passport, approved_by=approved_by, week=self.week, status="AUTHORIZED")
        self.ledger.append("AUTHORIZED", {"campaign_id": p.campaign_id, "approved_by": approved_by,
                                          "passport": passport.public()})
        self._execute(record)

    def _execute(self, record: dict) -> None:
        p, d, passport = record["proposal"], record["decision"], record["passport"]
        try:
            self.passports.consume(passport, policy_fingerprint=self.policy.fingerprint(), treated_ids=d.treated_ids)
        except PassportError as exc:
            record["status"] = "DENIED"
            self.budget.release(p.campaign_id)
            self.ledger.append("EXECUTION_REFUSED", {"campaign_id": p.campaign_id, "passport_error": exc.code})
            return
        try:
            offer = self.offers.create_offer(
                idempotency_key=p.campaign_id,
                reward_paise=p.reward_paise,
                min_bill_paise=p.min_bill_paise,
                customer_ids=d.treated_ids,
                valid_days=p.validity_days,
            )
        except UpstreamUnknown as exc:
            record["status"] = "UNKNOWN"
            self.ledger.append("EXECUTION_UNKNOWN", {
                "campaign_id": p.campaign_id,
                "error": str(exc),
                "action": "quarantined; budget stays reserved; not retried; needs a human to confirm",
            })
            return
        record.update(status="LIVE", offer=offer, live_day=self.clock.day)
        self._issued.extend((self.clock.day, cid) for cid in d.treated_ids)
        self.ledger.append("EXECUTED", {"campaign_id": p.campaign_id, "offer_id": offer["offer_id"],
                                        "customers": len(d.treated_ids),
                                        "mock": bool(getattr(self.offers, "is_mock", False))})

    def resolve_unknown(self, campaign_id: str, offer_exists: bool, actor: str = "merchant") -> None:
        record = self._get(campaign_id)
        if record["status"] != "UNKNOWN":
            raise ValueError(f"{campaign_id} is {record['status']}, not UNKNOWN")
        if offer_exists:
            record.update(status="LIVE", live_day=self.clock.day)
            self._issued.extend((self.clock.day, cid) for cid in record["decision"].treated_ids)
        else:
            record["status"] = "FAILED"
            self.budget.release(campaign_id)
        self.ledger.append("UNKNOWN_RESOLVED", {"campaign_id": campaign_id, "actor": actor,
                                                "offer_exists": offer_exists})

    def record_outcome(self, campaign_id: str, outcome: Outcome):
        record = self._get(campaign_id)
        if record["status"] != "LIVE":
            raise ValueError(f"{campaign_id} is {record['status']}, not LIVE")
        d, passport = record["decision"], record["passport"]
        if outcome.treated_n != len(d.treated_ids) or outcome.holdout_n != len(d.holdout_ids):
            raise ValueError("outcome group sizes do not match the authorized split")
        if outcome.spend_paise > passport.max_spend_paise:
            self.ledger.append("SPEND_BREACH", {"campaign_id": campaign_id, "spend_paise": outcome.spend_paise,
                                                "cap_paise": passport.max_spend_paise})
            raise ValueError("reported spend exceeds the passport cap")
        segment = self.segments[record["proposal"].segment_id]
        result = evaluate(outcome, self.policy.gross_margin_bps, prior=self.priors.get(segment.kind),
                          seed=stable_seed(campaign_id))
        released = self.budget.settle(campaign_id, outcome.spend_paise)
        record.update(result=result, released_paise=released, closed_day=self.clock.day,
                      status="STOPPED" if result.verdict == STOP else "COMPLETED")
        self.ledger.append("OUTCOME", {"campaign_id": campaign_id, "result": result.to_dict(),
                                       "released_paise": released,
                                       "action": "stopped" if result.verdict == STOP else "kept"})
        return result

    def set_kill_switch(self, on: bool, actor: str = "merchant") -> None:
        self.kill_switch = bool(on)
        self.ledger.append("KILL_SWITCH", {"on": self.kill_switch, "actor": actor})

    def update_policy(self, policy: MerchantPolicy, actor: str = "merchant") -> None:
        if policy.merchant_id != self.policy.merchant_id:
            raise ValueError("policy belongs to a different merchant")
        self.policy = policy
        self._engine = PolicyEngine(policy)
        self.budget.weekly_paise = policy.weekly_budget_paise
        self.ledger.append("POLICY_SET", {"by": actor, "policy": policy.to_dict()})

    def verify_ledger(self) -> dict:
        return self.ledger.verify()

    def state(self) -> dict:
        return {
            "merchant_id": self.policy.merchant_id,
            "day": self.clock.day,
            "date": self.clock.label(),
            "week": self.week,
            "kill_switch": self.kill_switch,
            "budget_remaining_paise": self.budget.remaining(self.week),
            "policy": self.policy.to_dict(),
            "campaigns": {
                cid: {
                    "status": r["status"],
                    "decision": r["decision"].decision,
                    "reasons": r["decision"].codes(),
                    "verdict": r["result"].verdict if r.get("result") else None,
                }
                for cid, r in self.campaigns.items()
            },
            "ledger": {"entries": len(self.ledger.entries), "head": self.ledger.head(), **self.ledger.verify()},
        }
