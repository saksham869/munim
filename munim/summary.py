"""What the merchant hears on the Soundbox, in Hinglish and English.

Every number is read from the decision or the measured result. The language
layer (template here, optionally an LLM in production) only phrases numbers
it is given; it never computes or invents one.
"""

from __future__ import annotations

from .measurement import STOP, WORKED
from .models import ALLOW, DENY, GATE
from .money import fmt_inr as inr
from .money import fmt_pct as pct


def policy_line(policy) -> dict:
    return {
        "hi": (
            f"Theek hai. Har hafte {inr(policy.weekly_budget_paise)} tak growth par kharch karunga, "
            f"har bill par kam se kam {pct(policy.keep_margin_bps)} munafa bachaunga, aur "
            f"{inr(policy.approval_threshold_paise)} se upar ke offer par pehle aapse poochunga."
        ),
        "en": (
            f"Got it. Up to {inr(policy.weekly_budget_paise)} a week on growth, at least "
            f"{pct(policy.keep_margin_bps)} margin kept on every bill, and I'll ask before any offer "
            f"that could cost more than {inr(policy.approval_threshold_paise)}."
        ),
    }


def decision_line(proposal, decision) -> dict:
    n = decision.numbers
    treated, holdout = n.get("treated", 0), n.get("holdout", 0)
    reward, bill, spend = inr(proposal.reward_paise), inr(proposal.min_bill_paise), inr(n.get("max_spend_paise", 0))
    if decision.decision == ALLOW:
        return {
            "hi": f"Naya offer chalu: {treated} grahakon ko {bill}+ ke bill par {reward} cashback. "
                  f"Zyada se zyada kharch {spend}. {holdout} grahak tulna ke liye alag rakhe.",
            "en": f"New offer live: {reward} cashback on bills of {bill}+ for {treated} customers. "
                  f"Most it can cost: {spend}. {holdout} customers held back for comparison.",
        }
    if decision.decision == GATE:
        if "kill_switch" in decision.codes(GATE):
            return {
                "hi": f"Apne aap kharch band hai. Agent ka naya offer ({reward} cashback, {treated} grahak, "
                      f"zyada se zyada {spend}) aapki manzoori ka intezaar kar raha hai.",
                "en": f"Autonomous spending is paused. The agent's new offer ({reward} cashback, {treated} customers, "
                      f"up to {spend}) is waiting for you.",
            }
        return {
            "hi": f"Manzoori chahiye: {treated} grahakon ko {bill}+ par {reward} cashback, zyada se zyada {spend}. "
                  f"'Haan' bolein ya button dabayein.",
            "en": f"Needs your OK: {reward} cashback on {bill}+ for {treated} customers, up to {spend}. "
                  f"Say 'haan' or press the button.",
        }
    denies = [r for r in decision.reasons if r.effect == DENY]
    first = denies[0] if denies else None
    return {
        "hi": f"Agent ka offer roka, {len(denies)} kaaran. " + (first.hi if first else ""),
        "en": f"Agent's offer refused, {len(denies)} reason(s). " + (first.en if first else ""),
    }


def outcome_line(proposal, result, released_paise: int) -> dict:
    name = proposal.name
    visits = max(0, round(result.incremental_visits))
    chance = round(result.prob_profitable * 100)
    if result.verdict == WORKED:
        return {
            "hi": f"'{name}' kaam kar gaya. {inr(result.spend_paise)} cashback diya; lagbhag {visits} extra visit "
                  f"aur {inr(result.incremental_revenue_paise)} ki extra bikri. Shuddh fayda {inr(result.net_paise)} "
                  f"({chance}% sambhavna ki sach mein fayda hua).",
            "en": f"'{name}' worked. {inr(result.spend_paise)} paid in cashback; about {visits} extra visits and "
                  f"{inr(result.incremental_revenue_paise)} in extra sales. Net {inr(result.net_paise)} "
                  f"({chance}% chance it truly made money).",
        }
    if result.verdict == STOP:
        return {
            "hi": f"'{name}' kaam nahi kiya. {inr(result.spend_paise)} kharch hue par pakka fayda nahi dikha "
                  f"({chance}% sambhavna). Munim ne ise band kar diya; {inr(released_paise)} budget wapas.",
            "en": f"'{name}' did not work. {inr(result.spend_paise)} spent with no clear gain ({chance}% chance "
                  f"it made money). Munim stopped it; {inr(released_paise)} back in the budget.",
        }
    back = round(result.prob_lift_positive * 100)
    return {
        "hi": f"'{name}' shayad kaam kar raha hai: {back}% sambhavna ki grahak offer ki wajah se laute, "
              f"{chance}% ki kharch nikal aaya. Abhi pakka nahi, isliye Munim ise chalne dega aur dekhta rahega.",
        "en": f"'{name}' is probably working: {back}% chance it brought customers back, {chance}% that it has "
              f"already paid for itself. Not proven yet, so Munim keeps it running and keeps measuring.",
    }
