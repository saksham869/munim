"""Execution adapter for merchant-funded customer offers.

MockPaytmOffers is a stand-in, not a Paytm API. Paytm does not publish an
offer-creation API for this use; in production this adapter is replaced by
the real integration, which must also check Munim's passport itself (the mock
does not). It behaves the way a careful upstream should: idempotent by key,
and able to fail in the ambiguous way real payment systems do.
"""

from __future__ import annotations

import hashlib


class UpstreamUnknown(Exception):
    """The call may or may not have taken effect (timeout, 5xx). Never retried blindly."""


class MockPaytmOffers:
    is_mock = True

    def __init__(self):
        self.created: dict = {}
        self.fail_next = False
        self.calls = 0

    def create_offer(self, *, idempotency_key: str, reward_paise: int, min_bill_paise: int, customer_ids, valid_days: int) -> dict:
        self.calls += 1
        if idempotency_key in self.created:
            return self.created[idempotency_key]
        if self.fail_next:
            self.fail_next = False
            raise UpstreamUnknown("offers API returned 503; outcome unknown")
        offer = {
            "offer_id": "mock-offer-" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:10],
            "status": "CREATED",
            "customers": len(customer_ids),
            "reward_paise": reward_paise,
            "min_bill_paise": min_bill_paise,
            "valid_days": valid_days,
        }
        self.created[idempotency_key] = offer
        return offer

    def cancel_offer(self, *, offer_id: str) -> dict:
        """Stop an offer early. Idempotent; reports cashback already redeemed (none in the mock)."""
        self.calls += 1
        offer = next((o for o in self.created.values() if o["offer_id"] == offer_id), None)
        if offer is None:
            raise KeyError(offer_id)
        if offer["status"] == "CANCELLED":
            return offer
        if self.fail_next:
            self.fail_next = False
            raise UpstreamUnknown("offers API timed out while cancelling; outcome unknown")
        offer.update(status="CANCELLED", redeemed_paise=0)
        return offer
