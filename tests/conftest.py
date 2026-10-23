from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from munim.models import CampaignProposal, MerchantPolicy, Segment  # noqa: E402
from munim.policy import EvalContext  # noqa: E402

MERCHANT = "test-kirana"


@pytest.fixture
def policy() -> MerchantPolicy:
    return MerchantPolicy(
        merchant_id=MERCHANT,
        weekly_budget_paise=50_000,
        gross_margin_bps=1_200,
        keep_margin_bps=600,
        approval_threshold_paise=30_000,
    )


def make_segment(n: int = 40, baseline_bps: int = 1_500, avg_basket_paise: int = 30_000, kind: str = "lapsed_regulars",
                 window_days: int = 14) -> Segment:
    return Segment(
        segment_id=f"{kind}@test",
        kind=kind,
        name="Test segment",
        description="for tests",
        customer_ids=tuple(f"c{i:03d}" for i in range(n)),
        baseline_return_bps=baseline_bps,
        avg_basket_paise=avg_basket_paise,
        window_days=window_days,
    )


def make_ctx(segment: Segment, *, remaining: int = 50_000, consented=None, offers=None, kill: bool = False,
             salt: bytes = b"salt") -> EvalContext:
    return EvalContext(
        segment=segment,
        consented=frozenset(segment.customer_ids if consented is None else consented),
        offers_last_30d=offers or {},
        remaining_budget_paise=remaining,
        kill_switch=kill,
        holdout_salt=salt,
    )


def make_proposal(segment: Segment, *, reward: int = 1_500, min_bill: int = 25_000, holdout: int = 20,
                  customers=None, validity=None, cid: str = "camp-1", merchant: str = MERCHANT) -> CampaignProposal:
    return CampaignProposal(
        campaign_id=cid,
        merchant_id=merchant,
        segment_id=segment.segment_id,
        name="Test offer",
        customer_ids=tuple(segment.customer_ids if customers is None else customers),
        reward_paise=reward,
        min_bill_paise=min_bill,
        holdout_pct=holdout,
        validity_days=segment.window_days if validity is None else validity,
    )


@pytest.fixture
def segment() -> Segment:
    return make_segment()
