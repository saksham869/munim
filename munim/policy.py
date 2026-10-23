"""Deterministic authorization for AI-proposed growth campaigns.

Same proposal + same context = same decision, every time. No model, no
network, no clock. DENY beats GATE beats ALLOW, every DENY says how to fix it,
and any exception inside the engine is itself a DENY.

docs/rules.js mirrors this file for the browser demo; tests/test_parity.py
keeps the two identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from . import economics as eco
from .holdout import assign
from .models import ALLOW, DENY, GATE, NOTE, CampaignProposal, Decision, MerchantPolicy, Reason, Segment
from .money import fmt_inr as inr
from .money import fmt_pct as pct
from .money import fmt_pp as pp


def cap(paise: int) -> str:
    """Limits are shown rounded down, so a cap is never displayed above its true value."""
    return inr(paise, floor=True)


# GATE reasons a human approval is allowed to clear. Nothing else is clearable.
HUMAN_CLEARABLE = frozenset({"approval_required", "kill_switch"})

_INT_FIELDS = ("reward_paise", "min_bill_paise", "holdout_pct", "validity_days")


@dataclass(frozen=True)
class EvalContext:
    """Everything the policy engine trusts. None of it comes from the agent."""

    segment: Segment | None
    consented: frozenset = frozenset()
    offers_last_30d: Mapping[str, int] = field(default_factory=dict)
    remaining_budget_paise: int = 0
    kill_switch: bool = False
    holdout_salt: bytes = b""


class PolicyEngine:
    def __init__(self, policy: MerchantPolicy):
        self.policy = policy

    def evaluate(self, proposal: CampaignProposal, ctx: EvalContext) -> Decision:
        try:
            return self._evaluate(proposal, ctx)
        except Exception as exc:  # fail closed: an engine we cannot trust says no
            return Decision(
                campaign_id=str(getattr(proposal, "campaign_id", "unknown")),
                decision=DENY,
                reasons=[
                    Reason(
                        "engine_error",
                        DENY,
                        f"Munim could not evaluate this proposal ({type(exc).__name__}), so it is refused.",
                        "Munim is offer ko jaanch nahi paya, isliye ise roka gaya.",
                    )
                ],
                constraints={},
                numbers={},
                policy_fingerprint=self.policy.fingerprint(),
            )

    # ------------------------------------------------------------------ rules

    def _evaluate(self, p: CampaignProposal, ctx: EvalContext) -> Decision:
        pol = self.policy
        seg = ctx.segment
        reasons: list = []
        constraints: dict = {}
        numbers: dict = {}

        def deny(code: str, en: str, hi: str) -> None:
            reasons.append(Reason(code, DENY, en, hi))

        # 1. Shape. A malformed proposal gets no further.
        problems = self._problems(p, seg)
        if problems:
            text = "; ".join(problems)
            return Decision(
                campaign_id=str(p.campaign_id),
                decision=DENY,
                reasons=[Reason("invalid_proposal", DENY, f"Refused as malformed: {text}.", f"Offer theek se nahi bana: {text}.")],
                constraints={},
                numbers={},
                policy_fingerprint=pol.fingerprint(),
            )

        keep = pol.keep_margin_bps

        # 2. Margin floor on the smallest qualifying bill.
        ceiling = eco.reward_ceiling_paise(p.min_bill_paise, pol.gross_margin_bps, keep)
        numbers["reward_ceiling_paise"] = ceiling
        if p.reward_paise > ceiling:
            typical_bill = eco.typical_min_bill_paise(seg.avg_basket_paise)
            typical_reward = eco.reward_ceiling_paise(typical_bill, pol.gross_margin_bps, keep)
            constraints["max_reward_paise"] = ceiling
            constraints["suggested"] = {"min_bill_paise": typical_bill, "reward_paise": typical_reward}
            need = eco.min_bill_for_reward_paise(p.reward_paise, pol.gross_margin_bps, keep)
            if need is not None:
                constraints["min_bill_for_requested_reward_paise"] = need
            deny(
                "margin_floor",
                f"{inr(p.reward_paise)} cashback on a {inr(p.min_bill_paise)} bill leaves less than the "
                f"{pct(keep)} margin you keep on every bill. Most it can be: {cap(ceiling)}. "
                f"Suggested: {cap(typical_reward)} on bills of {inr(typical_bill)}+.",
                f"{inr(p.min_bill_paise)} ke bill par {inr(p.reward_paise)} cashback se har bill par "
                f"{pct(keep)} munafa nahi bachega. Zyada se zyada {cap(ceiling)}. "
                f"Sujhaav: {inr(typical_bill)}+ ke bill par {cap(typical_reward)}.",
            )

        # 3. Every campaign keeps a comparison group, or nobody can tell if it worked.
        if p.holdout_pct < pol.min_holdout_pct:
            constraints["min_holdout_pct"] = pol.min_holdout_pct
            deny(
                "no_measurement",
                f"Keeps {p.holdout_pct}% of customers as a comparison group; at least {pol.min_holdout_pct}% "
                f"is required, or nobody can tell whether the offer worked.",
                f"Kam se kam {pol.min_holdout_pct}% grahak tulna ke liye rakhne zaroori hain, "
                f"warna pata hi nahi chalega offer kaam kiya ya nahi.",
            )

        # 4. Consent and frequency cap: customers are filtered out, not argued about.
        offer_cap = pol.max_offers_per_customer_30d
        consented = [c for c in p.customer_ids if c in ctx.consented]
        eligible = [c for c in consented if ctx.offers_last_30d.get(c, 0) < offer_cap]
        no_consent = len(p.customer_ids) - len(consented)
        capped = len(consented) - len(eligible)
        numbers.update(
            customers_proposed=len(p.customer_ids),
            excluded_no_consent=no_consent,
            excluded_frequency_cap=capped,
            eligible=len(eligible),
        )
        if no_consent:
            reasons.append(
                Reason(
                    "excluded_no_consent",
                    NOTE,
                    f"{no_consent} customer(s) have not opted in to offers and were left out.",
                    f"{no_consent} grahakon ne offers ke liye haan nahi kaha, unhe chhod diya.",
                )
            )
        if capped:
            reasons.append(
                Reason(
                    "excluded_frequency_cap",
                    NOTE,
                    f"{capped} customer(s) already got {offer_cap} offers in the last 30 days and were left out.",
                    f"{capped} grahakon ko 30 din mein pehle hi {offer_cap} offer mil chuke, unhe chhod diya.",
                )
            )

        # 5. Enough people to measure anything.
        if len(eligible) < pol.min_eligible_customers:
            constraints["min_eligible_customers"] = pol.min_eligible_customers
            deny(
                "too_small_to_measure",
                f"Only {len(eligible)} eligible customers; at least {pol.min_eligible_customers} are needed to measure the result.",
                f"Sirf {len(eligible)} grahak bache; nateeja naapne ke liye kam se kam {pol.min_eligible_customers} chahiye.",
            )

        # 6. Split. If the holdout asked for is too small, size the would-be campaign
        #    with the minimum so the numbers below still help the agent replan.
        holdout_used = max(p.holdout_pct, pol.min_holdout_pct)
        treated, holdout = assign(eligible, holdout_used, ctx.holdout_salt)
        numbers.update(treated=len(treated), holdout=len(holdout), holdout_pct_used=holdout_used)

        # 7. Weekly budget, worst case: every treated customer redeems.
        remaining = ctx.remaining_budget_paise
        max_spend = p.reward_paise * len(treated)
        numbers.update(max_spend_paise=max_spend, remaining_budget_paise=remaining)
        if max_spend > remaining:
            constraints["max_treated_customers"] = max(0, remaining // p.reward_paise)
            if treated:
                constraints["max_reward_for_all_paise"] = max(0, remaining // len(treated))
            deny(
                "over_budget",
                f"Worst case this spends {inr(max_spend)} ({len(treated)} customers x {inr(p.reward_paise)}); "
                f"only {cap(remaining)} is left in this week's budget.",
                f"Is offer mein {inr(max_spend)} tak kharch ho sakta hai, par is hafte sirf {cap(remaining)} bacha hai.",
            )

        # 8. Payback, counting cashback paid to people who would have come anyway.
        basket = max(p.min_bill_paise, seg.avg_basket_paise)
        baseline = seg.baseline_return_bps
        be = eco.break_even_lift_bps(baseline, basket, pol.gross_margin_bps, p.reward_paise)
        numbers.update(baseline_return_bps=baseline, basket_used_paise=basket, break_even_lift_bps=be)
        if be is None or be > eco.BPS - baseline:
            # Loses money even if every single customer comes back.
            bill_margin = eco.margin_per_bill_paise(basket, pol.gross_margin_bps)
            r_max = eco.max_reward_for_lift_paise(baseline, basket, pol.gross_margin_bps, pol.max_plausible_lift_bps)
            constraints["max_reward_for_payback_paise"] = r_max
            deny(
                "cannot_pay_back",
                f"Even if every one of these customers came back, {inr(p.reward_paise)} cashback would cost more than "
                f"the extra margin it earns ({inr(bill_margin)} on a typical {inr(basket)} bill, and {pct(baseline)} "
                f"come back anyway). Largest reward that can pay back: {cap(r_max)}.",
                f"Saare grahak laut aayein tab bhi {inr(p.reward_paise)} cashback ka kharch extra munafe se zyada hoga "
                f"({inr(basket)} ke aam bill par {inr(bill_margin)} munafa, aur {pct(baseline)} waise bhi aate hain). "
                f"Zyada se zyada {cap(r_max)} cashback.",
            )
        elif be > pol.max_plausible_lift_bps:
            r_max = eco.max_reward_for_lift_paise(baseline, basket, pol.gross_margin_bps, pol.max_plausible_lift_bps)
            constraints["max_reward_for_payback_paise"] = r_max
            deny(
                "unrealistic_payback",
                f"{pct(baseline)} of these customers come back within {seg.window_days} days anyway, so most cashback "
                f"would go to people who'd buy regardless. Breaking even needs {pp(be)} more of them to return; "
                f"plan for at most {pp(pol.max_plausible_lift_bps)}. Largest reward that can pay back: {cap(r_max)}.",
                f"Inme se {pct(baseline)} grahak {seg.window_days} din mein waise bhi aate hain; cashback zyadatar unhe "
                f"milega jo bina offer ke bhi kharidte. Fayde ke liye {pp(be)} aur grahak lautne chahiye, "
                f"ummeed {pp(pol.max_plausible_lift_bps)} tak hi. Zyada se zyada {cap(r_max)} cashback.",
            )

        # 9. Big spends wait for the merchant.
        if max_spend > pol.approval_threshold_paise:
            reasons.append(
                Reason(
                    "approval_required",
                    GATE,
                    f"Worst-case spend {inr(max_spend)} is above your {inr(pol.approval_threshold_paise)} "
                    f"auto-approve limit, so it waits for your OK.",
                    f"Is offer mein {inr(max_spend)} tak kharch ho sakta hai, aapki {inr(pol.approval_threshold_paise)} "
                    f"ki seema se zyada. Aapki manzoori chahiye.",
                )
            )

        # 10. Kill switch: nothing spends without a human.
        if ctx.kill_switch:
            reasons.append(
                Reason(
                    "kill_switch",
                    GATE,
                    "Autonomous spending is paused. Every campaign needs your approval.",
                    "Apne aap kharch band hai. Har offer ke liye aapki manzoori chahiye.",
                )
            )

        effects = {r.effect for r in reasons}
        decision = DENY if DENY in effects else GATE if GATE in effects else ALLOW
        if decision == ALLOW:
            reasons.append(
                Reason(
                    "within_rules",
                    NOTE,
                    f"Within your rules: worst case {inr(max_spend)} of the {cap(remaining)} left this week, "
                    f"and every bill keeps at least {pct(keep)} margin.",
                    f"Aapke niyamon ke andar: zyada se zyada {inr(max_spend)} kharch, har bill par kam se kam "
                    f"{pct(keep)} munafa.",
                )
            )

        return Decision(
            campaign_id=str(p.campaign_id),
            decision=decision,
            reasons=reasons,
            constraints=constraints,
            numbers=numbers,
            treated_ids=treated,
            holdout_ids=holdout,
            policy_fingerprint=pol.fingerprint(),
        )

    def _problems(self, p: CampaignProposal, seg: Segment | None) -> list:
        pol = self.policy
        problems = []
        for name in _INT_FIELDS:
            value = getattr(p, name)
            if isinstance(value, bool) or not isinstance(value, int):
                problems.append(f"{name} must be a whole number")
        if problems:
            return problems
        if p.merchant_id != pol.merchant_id:
            problems.append("it is addressed to a different merchant")
        if seg is None or seg.segment_id != p.segment_id:
            problems.append("its segment is not one Munim computed")
        if p.reward_paise <= 0:
            problems.append("the reward must be positive")
        if p.min_bill_paise <= 0:
            problems.append("the minimum bill must be positive")
        elif p.reward_paise >= p.min_bill_paise:
            problems.append("the reward must be smaller than the minimum bill")
        if not 1 <= p.validity_days <= pol.max_validity_days:
            problems.append(f"validity must be 1 to {pol.max_validity_days} days")
        elif seg is not None and p.validity_days != seg.window_days:
            problems.append(f"validity must match the {seg.window_days}-day measurement window")
        if not 0 <= p.holdout_pct <= pol.max_holdout_pct:
            problems.append(f"the comparison group must be 0 to {pol.max_holdout_pct}%")
        if not p.customer_ids:
            problems.append("it targets no customers")
        elif len(set(p.customer_ids)) != len(p.customer_ids):
            problems.append("it lists a customer twice")
        elif seg is not None and not set(p.customer_ids) <= set(seg.customer_ids):
            problems.append("it targets customers outside the segment")
        return problems
