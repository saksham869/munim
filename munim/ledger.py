"""Append-only, hash-chained record of every proposal, decision, approval, payout and result.

Each entry's hash covers the previous entry's hash, so changing, deleting or
reordering any past entry breaks every hash after it. Denials are recorded as
prominently as approvals.
"""

from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timezone

from .models import canonical_json

GENESIS = "0" * 64


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def entry_hash(prev_hash: str, body: dict) -> str:
    return hashlib.sha256((prev_hash + canonical_json(body)).encode()).hexdigest()


class Ledger:
    def __init__(self, clock=_utc_now):
        self._clock = clock
        self.entries: list = []

    def append(self, kind: str, payload: dict) -> dict:
        prev = self.entries[-1]["hash"] if self.entries else GENESIS
        body = {"seq": len(self.entries) + 1, "ts": self._clock(), "kind": kind, "payload": payload, "prev_hash": prev}
        entry = {**body, "hash": entry_hash(prev, body)}
        self.entries.append(entry)
        return entry

    def head(self) -> str:
        return self.entries[-1]["hash"] if self.entries else GENESIS

    def verify(self) -> dict:
        return verify_entries(self.entries)

    def export(self) -> list:
        return copy.deepcopy(self.entries)


def verify_entries(entries: list) -> dict:
    prev = GENESIS
    for i, entry in enumerate(entries, start=1):
        body = {k: v for k, v in entry.items() if k != "hash"}
        if entry.get("seq") != i or entry.get("prev_hash") != prev or entry_hash(prev, body) != entry.get("hash"):
            return {"intact": False, "checked": i, "broken_at": i}
        prev = entry["hash"]
    return {"intact": True, "checked": len(entries), "broken_at": None}
