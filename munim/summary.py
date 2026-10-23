"""What the merchant hears on the Soundbox, in Hinglish and English.

Every number is read from the decision or the measured result, and nothing the
agent wrote is ever spoken. The Soundbox sits on the counter, so spoken lines
never mention margins or why an offer was refused; the full reasons go to the
owner's app (they are in the decision record).
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
            "hi": f"{treated} grahakon ko {bill}+ ke bill par {reward} cashback bhejein? Kharcha {spend} tak. "
                  f"Manzoori ke liye screen par 'Haan' dabayein.",
            "en": f"Send {reward} cashback on {bill}+ bills to {treated} customers? It costs up to {spend}. "
                  f"Tap 'Haan' on the screen to approve.",
        }
    n = len([r for r in decision.reasons if r.effect == DENY])
    return {
        "hi": f"Agent ka {reward} cashback wala offer roka, {n} kaaran. Poori jaankari app mein.",
        "en": f"The agent's {reward} cashback offer was refused for {n} reason(s). Details are in the app.",
    }


def offer_label(proposal) -> dict:
    """How the owner hears an offer named: by its terms, never by the agent's free-text name."""
    reward, bill = inr(proposal.reward_paise), inr(proposal.min_bill_paise)
    return {"hi": f"{bill}+ ke bill par {reward} cashback wala offer", "en": f"The {reward} cashback offer on {bill}+ bills"}


def outcome_line(proposal, result, released_paise: int) -> dict:
    label = offer_label(proposal)
    visits = max(0, round(result.incremental_visits))
    chance = round(result.prob_profitable * 100)
    if result.verdict == WORKED:
        return {
            "hi": f"{label['hi']} kaam kar gaya. {inr(result.spend_paise)} cashback diya; lagbhag {visits} extra visit "
                  f"aur {inr(result.incremental_revenue_paise)} ki extra bikri. Shuddh fayda {inr(result.net_paise)} "
                  f"({chance}% sambhavna ki sach mein fayda hua).",
            "en": f"{label['en']} worked. {inr(result.spend_paise)} paid in cashback; about {visits} extra visits and "
                  f"{inr(result.incremental_revenue_paise)} in extra sales. Net {inr(result.net_paise)} "
                  f"({chance}% chance it truly made money).",
        }
    if result.verdict == STOP:
        return {
            "hi": f"{label['hi']} kaam nahi kiya. {inr(result.spend_paise)} kharch hue par pakka fayda nahi dikha "
                  f"({chance}% sambhavna). Munim ne ise band kiya, 30 din tak dobara nahi chalega; "
                  f"{inr(released_paise)} budget wapas.",
            "en": f"{label['en']} did not work. {inr(result.spend_paise)} spent with no clear gain ({chance}% chance "
                  f"it made money). Munim stopped it and won't let it run again for 30 days; "
                  f"{inr(released_paise)} back in the budget.",
        }
    back = round(result.prob_lift_positive * 100)
    return {
        "hi": f"{label['hi']} khatam. {back}% sambhavna ki grahak offer ki wajah se laute, {chance}% ki kharch nikal "
              f"aaya. Abhi pakka nahi; agli baar aisa offer chala to Munim phir naapega.",
        "en": f"{label['en']} has ended. {back}% chance it brought customers back, {chance}% that it paid for itself. "
              f"Not proven yet; if the agent runs it again, Munim measures it again.",
    }
