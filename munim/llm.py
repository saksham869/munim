"""Optional LLM proposer over any OpenAI-compatible chat endpoint.

Works with Pi Inference, Groq, OpenAI, or a local server. Off unless
MUNIM_LLM_BASE_URL, MUNIM_LLM_API_KEY and MUNIM_LLM_MODEL are set.

The model's reply is parsed into a typed CampaignProposal and then goes through
the same policy engine as every other proposal. Free text never reaches the
money path, and a reply that does not parse is refused, not repaired.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request

from .models import CampaignProposal, Segment
from .money import fmt_inr as inr
from .money import fmt_pct as pct

SYSTEM_PROMPT = (
    "You are a growth agent for a small Indian shop that takes payments on Paytm. "
    "Propose ONE customer offer. Reply with a JSON object only, with keys: "
    "name (string), reward_rupees (integer), min_bill_rupees (integer), holdout_pct (integer), "
    "customer_count (integer), message_hi (Hinglish text the customer sees, max 160 characters), "
    "rationale (one sentence). You cannot pay anyone. A separate system, Munim, will allow, "
    "hold for the shop owner, or refuse your offer and say why. If it refused a previous attempt, "
    "fix every reason it gave."
)

REQUIRED_INTS = ("reward_rupees", "min_bill_rupees", "holdout_pct", "customer_count")
# Same ranges the HTTP API accepts, so neither entry point takes absurd numbers.
LIMITS = {"reward_rupees": (1, 10_000), "min_bill_rupees": (1, 100_000), "holdout_pct": (0, 100),
          "customer_count": (1, 100_000)}


class LLMError(Exception):
    pass


def build_messages(segment: Segment, policy, feedback: list | None = None) -> list:
    rules = (
        f"Weekly budget {inr(policy.weekly_budget_paise)}. Gross margin {pct(policy.gross_margin_bps)}; "
        f"keep at least {pct(policy.keep_margin_bps)} on every bill. Offers that could cost more than "
        f"{inr(policy.approval_threshold_paise)} wait for the owner. Keep at least {policy.min_holdout_pct}% "
        f"of customers as a comparison group."
    )
    seg = (
        f"Segment '{segment.name}': {segment.description}. {len(segment.customer_ids)} customers. "
        f"{pct(segment.baseline_return_bps)} return within {segment.window_days} days on their own. "
        f"Average bill {inr(segment.avg_basket_paise)}."
    )
    user = f"Shop rules: {rules}\n{seg}"
    if feedback:
        user += "\nMunim refused your last offer because:\n- " + "\n- ".join(feedback)
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def parse_reply(text: str, *, segment: Segment, merchant_id: str, campaign_id: str, attempt: int = 1,
                proposed_by: str = "llm") -> CampaignProposal:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        raise LLMError("no JSON object in model reply")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise LLMError(f"model reply is not valid JSON: {exc.msg}") from None
    if not isinstance(data, dict):
        raise LLMError("model reply is not a JSON object")
    for key in REQUIRED_INTS:
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise LLMError(f"{key} must be an integer")
        lo, hi = LIMITS[key]
        if not lo <= value <= hi:
            raise LLMError(f"{key} must be between {lo} and {hi}")
    count = max(1, min(data["customer_count"], len(segment.customer_ids)))
    return CampaignProposal(
        campaign_id=campaign_id,
        merchant_id=merchant_id,
        segment_id=segment.segment_id,
        name=str(data.get("name", "LLM offer"))[:80],
        customer_ids=tuple(sorted(segment.customer_ids)[:count]),
        reward_paise=data["reward_rupees"] * 100,
        min_bill_paise=data["min_bill_rupees"] * 100,
        holdout_pct=data["holdout_pct"],
        validity_days=segment.window_days,
        message=str(data.get("message_hi", ""))[:160],
        rationale=str(data.get("rationale", ""))[:300],
        attempt=attempt,
        proposed_by=proposed_by,
    )


def _urllib_transport(url: str, headers: dict, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - URL comes from operator config
        return json.loads(resp.read().decode())


class OpenAICompatibleProposer:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 20.0, transport=None):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.transport = transport or _urllib_transport

    @classmethod
    def from_env(cls):
        base, key, model = (os.environ.get(k) for k in ("MUNIM_LLM_BASE_URL", "MUNIM_LLM_API_KEY", "MUNIM_LLM_MODEL"))
        return cls(base, key, model) if base and key and model else None

    def propose(self, segment: Segment, policy, merchant_id: str, campaign_id: str, *, feedback=None,
                attempt: int = 1) -> CampaignProposal:
        body = {"model": self.model, "messages": build_messages(segment, policy, feedback), "temperature": 0.2}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        reply = self.transport(self.url, headers, body, self.timeout)
        try:
            text = reply["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise LLMError("unexpected response shape from model endpoint") from None
        return parse_reply(text, segment=segment, merchant_id=merchant_id, campaign_id=campaign_id,
                           attempt=attempt, proposed_by=f"llm:{self.model}")
