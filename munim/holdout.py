"""Comparison-group assignment the agent cannot steer.

Customers are ranked by SHA-256 of a per-campaign salt plus their id, and the
first k become the holdout. The salt is an HMAC of the campaign id under a
secret only Munim holds, so the agent cannot predict the split or retry
campaign ids until it gets a flattering one.
"""

from __future__ import annotations

import hashlib
import hmac

from .economics import split_counts


def campaign_salt(secret: bytes, campaign_id: str) -> bytes:
    return hmac.new(secret, campaign_id.encode(), hashlib.sha256).digest()


def assign(customer_ids, holdout_pct: int, salt: bytes) -> tuple[tuple, tuple]:
    """Return (treated, holdout) as sorted tuples. Holdout size is exactly ceil(n * pct / 100)."""
    unique = sorted(set(customer_ids))
    ranked = sorted(unique, key=lambda cid: hashlib.sha256(salt + cid.encode()).digest())
    _, k = split_counts(len(ranked), holdout_pct)
    holdout = tuple(sorted(ranked[:k]))
    treated = tuple(sorted(ranked[k:]))
    return treated, holdout
