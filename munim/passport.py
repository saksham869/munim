"""Action passports: what the execution layer accepts instead of trusting the agent.

A passport authorizes one campaign: a fixed reward, minimum bill, spend cap and
customer list, under one policy version, for a limited time, once. It is
signed with HMAC-SHA256 under a key the agent never sees.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import asdict, dataclass

from .models import canonical_json


class PassportError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def digest_ids(ids) -> str:
    return hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()


@dataclass(frozen=True)
class Passport:
    campaign_id: str
    merchant_id: str
    reward_paise: int
    min_bill_paise: int
    max_spend_paise: int
    treated_count: int
    treated_digest: str
    policy_fingerprint: str
    issued_at: float
    expires_at: float
    nonce: str
    signature: str = ""

    def body(self) -> dict:
        d = asdict(self)
        d.pop("signature")
        return d

    def public(self) -> dict:
        d = asdict(self)
        d["signature"] = d["signature"][:16] + "..."
        return d


class PassportIssuer:
    def __init__(self, secret: bytes, ttl_seconds: int = 900, clock=time.time, nonce_source=None):
        self._secret = secret
        self._ttl = ttl_seconds
        self._clock = clock
        # Random by default. The demo passes a seeded source so its output is identical on every run.
        self._nonce = nonce_source or (lambda: secrets.token_hex(12))
        self._used: set = set()
        self._lock = threading.Lock()

    def _sign(self, body: dict) -> str:
        return hmac.new(self._secret, canonical_json(body).encode(), hashlib.sha256).hexdigest()

    def issue(self, *, campaign_id, merchant_id, reward_paise, min_bill_paise, max_spend_paise, treated_ids, policy_fingerprint) -> Passport:
        now = self._clock()
        unsigned = Passport(
            campaign_id=campaign_id,
            merchant_id=merchant_id,
            reward_paise=reward_paise,
            min_bill_paise=min_bill_paise,
            max_spend_paise=max_spend_paise,
            treated_count=len(treated_ids),
            treated_digest=digest_ids(treated_ids),
            policy_fingerprint=policy_fingerprint,
            issued_at=now,
            expires_at=now + self._ttl,
            nonce=self._nonce(),
        )
        return Passport(**{**asdict(unsigned), "signature": self._sign(unsigned.body())})

    def verify(self, passport: Passport, *, policy_fingerprint: str, treated_ids) -> None:
        if not hmac.compare_digest(self._sign(passport.body()), passport.signature):
            raise PassportError("bad_signature")
        if passport.nonce in self._used:
            raise PassportError("replayed")
        if self._clock() > passport.expires_at:
            raise PassportError("expired")
        if passport.policy_fingerprint != policy_fingerprint:
            raise PassportError("stale_policy")
        if digest_ids(treated_ids) != passport.treated_digest:
            raise PassportError("scope_mismatch")

    def consume(self, passport: Passport, *, policy_fingerprint: str, treated_ids) -> None:
        with self._lock:
            self.verify(passport, policy_fingerprint=policy_fingerprint, treated_ids=treated_ids)
            self._used.add(passport.nonce)
