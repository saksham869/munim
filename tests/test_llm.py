"""The LLM proposer: whatever the model says becomes a typed proposal or an error, never an action."""

from __future__ import annotations

import json

import pytest

from munim.llm import LLMError, OpenAICompatibleProposer, build_messages, parse_reply
from munim.policy import PolicyEngine

from .conftest import make_ctx, make_segment

GOOD = {"name": "Win back", "reward_rupees": 15, "min_bill_rupees": 250, "holdout_pct": 20, "customer_count": 30,
        "message_hi": "Aapki yaad aayi! ₹250+ par ₹15 cashback.", "rationale": "Lapsed regulars respond to small rewards."}


def parse(text, seg=None):
    seg = seg or make_segment()
    return parse_reply(text, segment=seg, merchant_id="test-kirana", campaign_id="llm-1")


def test_plain_json_parses():
    p = parse(json.dumps(GOOD))
    assert p.reward_paise == 1_500 and p.min_bill_paise == 25_000 and len(p.customer_ids) == 30


def test_code_fenced_reply_parses():
    assert parse("```json\n" + json.dumps(GOOD) + "\n```").holdout_pct == 20


def test_customer_count_is_clipped_to_the_segment():
    assert len(parse(json.dumps({**GOOD, "customer_count": 9_999})).customer_ids) == 40


@pytest.mark.parametrize("text", ["sure! here's an idea", "{not json}", "[1, 2, 3]",
                                  json.dumps({**GOOD, "reward_rupees": "fifteen"}),
                                  json.dumps({**GOOD, "holdout_pct": 20.5}),
                                  json.dumps({**GOOD, "customer_count": True})])
def test_bad_replies_are_refused_not_repaired(text):
    with pytest.raises(LLMError):
        parse(text)


def test_a_greedy_model_still_has_to_get_past_the_policy(policy):
    seg = make_segment()
    p = parse(json.dumps({**GOOD, "reward_rupees": 200, "holdout_pct": 0}), seg)
    d = PolicyEngine(policy).evaluate(p, make_ctx(seg))
    assert d.decision == "DENY"


def test_feedback_reaches_the_prompt(policy):
    msgs = build_messages(make_segment(), policy, feedback=["Max reward ₹15"])
    assert "Max reward ₹15" in msgs[-1]["content"] and msgs[0]["role"] == "system"


def test_proposer_with_stub_transport(policy):
    seen = {}

    def transport(url, headers, body, timeout):
        seen.update(url=url, auth=headers["Authorization"], model=body["model"])
        return {"choices": [{"message": {"content": json.dumps(GOOD)}}]}

    prop = OpenAICompatibleProposer("https://example.invalid/v1/", "key", "some-model", transport=transport)
    p = prop.propose(make_segment(), policy, "test-kirana", "llm-1")
    assert seen == {"url": "https://example.invalid/v1/chat/completions", "auth": "Bearer key", "model": "some-model"}
    assert p.proposed_by == "llm:some-model"


def test_odd_endpoint_response_is_an_error(policy):
    prop = OpenAICompatibleProposer("https://x/v1", "k", "m", transport=lambda *a: {"error": "rate limited"})
    with pytest.raises(LLMError):
        prop.propose(make_segment(), policy, "test-kirana", "llm-1")


def test_from_env_is_off_by_default(monkeypatch):
    for k in ("MUNIM_LLM_BASE_URL", "MUNIM_LLM_API_KEY", "MUNIM_LLM_MODEL"):
        monkeypatch.delenv(k, raising=False)
    assert OpenAICompatibleProposer.from_env() is None
