"""Append-only, hash-chained record of every proposal, decision, approval, payout and result.

Two layers:
- a public SHA-256 chain: each entry's hash covers the previous one, so anyone
  holding an export can see that nothing was edited, deleted or reordered
  without recomputing the hashes after it;
- a seal on every entry, an HMAC of its hash under a key only Munim holds, so
  even someone who rewrites the whole chain consistently cannot forge the
  seals. The key is never written into the ledger or its exports.
Denials are recorded as prominently as approvals.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
from datetime import datetime, timezone

from .models import canonical_json

GENESIS = "0" * 64


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def entry_hash(prev_hash: str, body: dict) -> str:
    return hashlib.sha256((prev_hash + canonical_json(body)).encode()).hexdigest()


def entry_seal(key: bytes, hash_hex: str) -> str:
    return hmac.new(key, hash_hex.encode(), hashlib.sha256).hexdigest()


class Ledger:
    def __init__(self, clock=_utc_now, key: bytes | None = None):
        self._clock = clock
        self._key = key
        self.entries: list = []

    def append(self, kind: str, payload: dict) -> dict:
        prev = self.entries[-1]["hash"] if self.entries else GENESIS
        body = {"seq": len(self.entries) + 1, "ts": self._clock(), "kind": kind, "payload": payload, "prev_hash": prev}
        entry = {**body, "hash": entry_hash(prev, body)}
        if self._key is not None:
            entry["seal"] = entry_seal(self._key, entry["hash"])
        self.entries.append(entry)
        return entry

    def head(self) -> str:
        return self.entries[-1]["hash"] if self.entries else GENESIS

    def verify(self) -> dict:
        return verify_entries(self.entries, key=self._key)

    def verify_export(self, entries: list) -> dict:
        """Check an exported copy, seals included, with this ledger's key."""
        return verify_entries(entries, key=self._key)

    def export(self) -> list:
        return copy.deepcopy(self.entries)


def verify_entries(entries: list, key: bytes | None = None) -> dict:
    """Public chain check; with `key`, also check every entry's seal."""
    sealed = key is not None
    prev = GENESIS
    for i, entry in enumerate(entries, start=1):
        body = {k: v for k, v in entry.items() if k not in ("hash", "seal")}
        if entry.get("seq") != i or entry.get("prev_hash") != prev or entry_hash(prev, body) != entry.get("hash"):
            return {"intact": False, "checked": i, "broken_at": i, "sealed": sealed}
        if sealed and not hmac.compare_digest(entry_seal(key, entry["hash"]), str(entry.get("seal", ""))):
            return {"intact": False, "checked": i, "broken_at": i, "sealed": sealed}
        prev = entry["hash"]
    return {"intact": True, "checked": len(entries), "broken_at": None, "sealed": sealed}
