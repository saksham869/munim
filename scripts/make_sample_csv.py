#!/usr/bin/env python3
"""Write examples/sample_payments.csv: the synthetic shop's six months of payments in the import format.

A few deliberately bad rows are appended (a refund, a missing customer id, a
date in the wrong format, a re-exported duplicate, and a payer identified by a
phone number) so that `scripts/import_payments.py` shows its validation.

    python3 scripts/make_sample_csv.py
"""

from __future__ import annotations

import pathlib
import sys
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from munim.ingest import export_payments_csv  # noqa: E402
from munim.simulator import SyntheticKirana  # noqa: E402

TODAY = date(2026, 10, 23)


def main() -> None:
    sim = SyntheticKirana(seed=2026)
    start = TODAY - timedelta(days=sim.today)
    text = export_payments_csv(sim.txns, start, sim.consented, sim.offers_last_30d)
    last = TODAY - timedelta(days=1)
    bad = [
        f"BAD1,{last.isoformat()}T10:00:00,c0007,-120,yes,0",              # refund
        f"BAD2,{last.isoformat()}T11:00:00,,250,yes,0",                    # no customer id
        "BAD3,23/10/2026,c0011,180,yes,0",                                # wrong date format
        f"T000001,{start.isoformat()}T09:00:00,c9999,999,yes,0",           # re-exported duplicate txn_id
        f"BAD5,{last.isoformat()}T18:00:00,9876543210,410,yes,0",          # payer identified by a phone number
    ]
    out = ROOT / "examples" / "sample_payments.csv"
    out.parent.mkdir(exist_ok=True)
    out.write_text(text + "\n".join(bad) + "\n")
    print(f"Wrote {out.relative_to(ROOT)}: {len(sim.txns)} payments from {start} to {last}, plus {len(bad)} bad rows")


if __name__ == "__main__":
    main()
