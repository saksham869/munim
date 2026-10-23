"""Typed records passed between the agent, the policy engine and the ledger."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

ALLOW, GATE, DENY, NOTE = "ALLOW", "GATE", "DENY", "NOTE"


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


@dataclass(frozen=True)
class MerchantPolicy:
    """Rules the merchant sets once. The agent can read them; only the merchant can change them."""

    merchant_id: str
    weekly_budget_paise: int
    gross_margin_bps: int
    keep_margin_bps: int
    approval_threshold_paise: int
    min_holdout_pct: int = 20
    max_holdout_pct: int = 50
    max_offers_per_customer_30d: int = 2
    max_plausible_lift_bps: int = 2500
    max_validity_days: int = 14
    min_eligible_customers: int = 10
    version: int = 1

    def fingerprint(self) -> str:
        return hashlib.sha256(canonical_json(asdict(self)).encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["fingerprint"] = self.fingerprint()
        return d


@dataclass(frozen=True)
class Segment:
    """A group of customers Munim computed from the merchant's own payment history.

    Baseline return rate and average basket are measured by Munim, never
    supplied by the agent, so the agent cannot talk its way past the payback check.
    """

    segment_id: str
    kind: str
    name: str
    description: str
    customer_ids: tuple
    baseline_return_bps: int
    avg_basket_paise: int
    window_days: int
    backtest_members: int = 0
    backtest_returned: int = 0

    def summary(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "kind": self.kind,
            "name": self.name,
            "description": self.description,
            "size": len(self.customer_ids),
            "baseline_return_bps": self.baseline_return_bps,
            "avg_basket_paise": self.avg_basket_paise,
            "window_days": self.window_days,
            "backtest_members": self.backtest_members,
            "backtest_returned": self.backtest_returned,
        }


@dataclass(frozen=True)
class CampaignProposal:
    """What the growth agent wants to do. Everything in here is untrusted."""

    campaign_id: str
    merchant_id: str
    segment_id: str
    name: str
    customer_ids: tuple
    reward_paise: int
    min_bill_paise: int
    holdout_pct: int
    validity_days: int
    message: str = ""
    rationale: str = ""
    attempt: int = 1
    proposed_by: str = "agent"

    def to_dict(self, include_ids: bool = False) -> dict:
        d = asdict(self)
        d["customer_count"] = len(self.customer_ids)
        if include_ids:
            d["customer_ids"] = list(self.customer_ids)
        else:
            d.pop("customer_ids")
        return d


@dataclass(frozen=True)
class Reason:
    code: str
    effect: str
    en: str
    hi: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Decision:
    campaign_id: str
    decision: str
    reasons: list
    constraints: dict
    numbers: dict
    treated_ids: tuple = ()
    holdout_ids: tuple = ()
    policy_fingerprint: str = ""
    extra: dict = field(default_factory=dict)

    def codes(self, effect: str | None = None) -> list:
        return [r.code for r in self.reasons if effect is None or r.effect == effect]

    def to_dict(self, include_ids: bool = False) -> dict:
        d = {
            "campaign_id": self.campaign_id,
            "decision": self.decision,
            "reasons": [r.to_dict() for r in self.reasons],
            "constraints": self.constraints,
            "numbers": self.numbers,
            "policy_fingerprint": self.policy_fingerprint,
        }
        if include_ids:
            d["treated_ids"] = list(self.treated_ids)
            d["holdout_ids"] = list(self.holdout_ids)
        return d
