"""A stand-in growth agent.

In production the proposer is Paytm's own growth agent (for example Pi's Sales
& Marketing agent) or an LLM through munim.llm. Either way it sees segment
summaries and Munim's decisions, and it has no way to pay anyone.

This reference agent is deliberately greedy on its first try so the demo
shows Munim refusing, explaining, and the agent replanning within limits.
"""

from __future__ import annotations

import re

from .models import DENY, CampaignProposal, Decision, Segment
from .money import fmt_inr as inr

STEP_PAISE = 500  # offers in clean ₹5 steps


def _lead(message: str, store_name: str) -> str:
    """The greeting of the previous message ("... kami khal rahi hai!"), kept when the offer terms change."""
    lead = re.split(r"(?<=[!:.])\s", message.strip(), maxsplit=1)[0] if message.strip() else ""
    return lead if lead and lead != message.strip() else f"{store_name}:"


class ReferenceAgent:
    name = "reference-growth-agent"

    def __init__(self, store_name: str = "Sharma General Store"):
        self.store_name = store_name

    def proposal(self, segment: Segment, merchant_id: str, campaign_id: str, *, name: str, reward_paise: int,
                 min_bill_paise: int, holdout_pct: int = 20, customer_ids=None, message: str = "",
                 rationale: str = "", attempt: int = 1) -> CampaignProposal:
        ids = tuple(customer_ids) if customer_ids is not None else segment.customer_ids
        return CampaignProposal(
            campaign_id=campaign_id,
            merchant_id=merchant_id,
            segment_id=segment.segment_id,
            name=name,
            customer_ids=ids,
            reward_paise=reward_paise,
            min_bill_paise=min_bill_paise,
            holdout_pct=holdout_pct,
            validity_days=segment.window_days,
            message=message,
            rationale=rationale,
            attempt=attempt,
            proposed_by=self.name,
        )

    def win_back_greedy(self, segment: Segment, merchant_id: str, campaign_id: str) -> CampaignProposal:
        return self.proposal(
            segment, merchant_id, campaign_id,
            name="Win back lapsed regulars",
            reward_paise=4_000,
            min_bill_paise=10_000,
            holdout_pct=0,
            message=f"{self.store_name} mein aapki kami khal rahi hai! Agli khareed par ₹40 cashback.",
            rationale="Bring back as many lapsed regulars as possible: big reward, low minimum bill, everyone, no comparison group.",
        )

    def replan(self, previous: CampaignProposal, decision: Decision, segment: Segment) -> CampaignProposal | None:
        """Use the constraints Munim returned to build a proposal it can accept. None means give up."""
        if decision.decision != DENY:
            return None
        codes = set(decision.codes(DENY))
        if codes & {"invalid_proposal", "too_small_to_measure", "engine_error", "duplicate_campaign"}:
            return None
        c, n = decision.constraints, decision.numbers
        reward, min_bill, holdout = previous.reward_paise, previous.min_bill_paise, previous.holdout_pct
        customers = list(previous.customer_ids)

        if "suggested" in c:
            min_bill = c["suggested"]["min_bill_paise"]
            reward = min(reward, c["suggested"]["reward_paise"])
        elif "max_reward_paise" in c:
            reward = min(reward, c["max_reward_paise"])
        if "max_reward_for_payback_paise" in c:
            reward = min(reward, c["max_reward_for_payback_paise"])
        reward = (reward // STEP_PAISE) * STEP_PAISE
        if reward < 1_000:
            return None  # below ₹10 an offer is not worth sending
        if "min_holdout_pct" in c:
            holdout = max(holdout, c["min_holdout_pct"])

        remaining, treated = n.get("remaining_budget_paise"), n.get("treated")
        if remaining is not None and treated and reward * treated > remaining:
            keep_treated = remaining // reward
            customers = customers[: max(1, len(customers) * keep_treated // treated)]

        attempt = previous.attempt + 1
        base_id = previous.campaign_id.rsplit("-a", 1)[0]
        return CampaignProposal(
            campaign_id=f"{base_id}-a{attempt}",
            merchant_id=previous.merchant_id,
            segment_id=previous.segment_id,
            name=previous.name,
            customer_ids=tuple(customers),
            reward_paise=reward,
            min_bill_paise=min_bill,
            holdout_pct=holdout,
            validity_days=previous.validity_days,
            message=(
                f"{_lead(previous.message, self.store_name)} {inr(min_bill)}+ ki khareed par "
                f"{inr(reward)} cashback, {previous.validity_days} din tak."
            ),
            rationale=f"Replanned inside Munim's limits after: {', '.join(sorted(codes))}.",
            attempt=attempt,
            proposed_by=self.name,
        )
