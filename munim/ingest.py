"""Load a merchant's own payments export (CSV) into Munim.

This is how a pilot starts: the merchant (or Paytm, with the merchant's
consent) exports payments, and Munim computes segments and return rates from
them. Every row is validated; bad rows are rejected with a reason and a line
number, never silently repaired.

Required columns (header row, any case):
    date         YYYY-MM-DD, or a full ISO timestamp (YYYY-MM-DDTHH:MM[:SS])
    customer_id  a stable id per payer; phone numbers, emails and UPI ids are
                 replaced by salted hashes on load, so they never reach the
                 ledger or the growth agent
    amount       rupees, e.g. 349 or 349.50 (or amount_paise as an integer)

Optional columns:
    txn_id       duplicate ids are dropped (re-exports often repeat rows)
    consented    yes/no, true/false, 1/0; the customer's latest row decides.
                 Without this column nobody can receive offers: consent is
                 never assumed.
    offers_30d   offers the customer already got in the last 30 days
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from .insights import Txn

MAX_BILL_PAISE = 2_00_000_00  # ₹2,00,000: anything above is not a single kirana bill
MIN_HISTORY_DAYS = 120  # lapsed regulars need 90 days before a 3-week gap, plus backtests
REQUIRED = ("date", "customer_id")
TRUE = {"1", "y", "yes", "true", "haan", "ha"}
FALSE = {"0", "n", "no", "false", "nahi", "na"}

_PHONE = re.compile(r"^(\+?91[\s-]?)?[6-9]\d{9}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_VPA = re.compile(r"^[\w.\-]{2,}@[a-zA-Z]{2,}$")


class IngestError(ValueError):
    """The file as a whole can't be used (missing columns, no valid rows, mostly invalid)."""


@dataclass
class IngestReport:
    rows: int = 0
    loaded: int = 0
    rejected: int = 0
    duplicates_dropped: int = 0
    pseudonymised_ids: int = 0
    customers: int = 0
    first_date: str = ""
    last_date: str = ""
    history_days: int = 0
    errors: list = field(default_factory=list)  # (line, reason), first 20 only
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass
class MerchantData:
    """Same shape the engine reads from the synthetic shop: txns, today, consented, offers_last_30d."""

    txns: list
    today: int
    start_date: date
    consented: frozenset
    offers_last_30d: dict
    report: IngestReport


def _pseudonym(raw: str, salt: bytes) -> str:
    return "h_" + hmac.new(salt, raw.encode(), hashlib.sha256).hexdigest()[:16]


def _looks_personal(value: str) -> bool:
    v = value.replace(" ", "")
    return bool(_PHONE.match(v) or _EMAIL.match(v) or _VPA.match(v))


def _parse_when(value: str) -> tuple:
    value = value.strip()
    try:
        if len(value) == 10:
            return date.fromisoformat(value), 12
        dt = datetime.fromisoformat(value.replace("Z", "+00:00").replace(" ", "T", 1))
        return dt.date(), dt.hour
    except ValueError:
        raise ValueError(f"date '{value}' is not YYYY-MM-DD or an ISO timestamp")


def _parse_amount(row: dict) -> int:
    if row.get("amount_paise", "").strip():
        text = row["amount_paise"].strip()
        if not re.fullmatch(r"-?\d+", text):
            raise ValueError(f"amount_paise '{text}' is not a whole number")
        paise = int(text)
    else:
        text = row.get("amount", "").strip().replace(",", "").replace("₹", "")
        if not re.fullmatch(r"-?\d+(\.\d{1,2})?", text):
            raise ValueError(f"amount '{row.get('amount', '')}' is not a rupee amount")
        whole, _, frac = text.lstrip("-").partition(".")
        paise = int(whole) * 100 + int((frac + "00")[:2])
        paise = -paise if text.startswith("-") else paise
    if paise < 0:
        raise ValueError("negative amount (a refund or reversal), not a sale")
    if paise == 0:
        raise ValueError("zero amount")
    if paise > MAX_BILL_PAISE:
        raise ValueError("amount above ₹2,00,000, not a single shop bill")
    return paise


def _parse_flag(value: str, line: int) -> bool:
    v = value.strip().lower()
    if v in TRUE:
        return True
    if v in FALSE or v == "":
        return False
    raise ValueError(f"consented '{value}' is not yes/no")


def load_payments_csv(source, *, salt: bytes, today: date | None = None, max_invalid_share: float = 0.5) -> MerchantData:
    """Parse a payments CSV (a pathlib.Path, an open file, or CSV text) into MerchantData.

    `salt` is a per-merchant secret used to pseudonymise personal ids.
    `today` defaults to the day after the last payment.
    """
    if isinstance(source, os.PathLike):
        if not os.path.isfile(source):
            raise IngestError(f"file not found: {source}")
        handle = open(source, newline="", encoding="utf-8-sig")
    elif isinstance(source, str):
        handle = io.StringIO(source)  # CSV text; pass a pathlib.Path to read a file
    else:
        handle = source
    try:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise IngestError("the file is empty")
        reader.fieldnames = [f.strip().lower() for f in reader.fieldnames]
        missing = [c for c in REQUIRED if c not in reader.fieldnames]
        if "amount" not in reader.fieldnames and "amount_paise" not in reader.fieldnames:
            missing.append("amount")
        if missing:
            raise IngestError("missing column(s): " + ", ".join(missing))
        has_consent = "consented" in reader.fieldnames
        has_offers = "offers_30d" in reader.fieldnames
        has_txn_id = "txn_id" in reader.fieldnames

        report = IngestReport()
        parsed, seen_ids, pseudonyms = [], set(), {}
        consent, offers = {}, {}
        for line, row in enumerate(reader, start=2):
            report.rows += 1
            row = {k: (v or "") for k, v in row.items() if k is not None}
            try:
                if has_txn_id and row["txn_id"].strip():
                    tid = row["txn_id"].strip()
                    if tid in seen_ids:
                        report.duplicates_dropped += 1
                        continue
                    seen_ids.add(tid)
                raw_id = row["customer_id"].strip()
                if not raw_id:
                    raise ValueError("missing customer_id")
                when, hour = _parse_when(row["date"])
                amount = _parse_amount(row)
                consent_value = _parse_flag(row.get("consented", ""), line) if has_consent else None
                offers_value = None
                if has_offers and row["offers_30d"].strip():
                    if not row["offers_30d"].strip().isdigit():
                        raise ValueError(f"offers_30d '{row['offers_30d']}' is not a whole number")
                    offers_value = int(row["offers_30d"].strip())
            except ValueError as exc:
                report.rejected += 1
                if len(report.errors) < 20:
                    report.errors.append((line, str(exc)))
                continue
            if _looks_personal(raw_id):
                if raw_id not in pseudonyms:
                    pseudonyms[raw_id] = _pseudonym(raw_id.replace(" ", ""), salt)
                cid = pseudonyms[raw_id]
            else:
                cid = raw_id
            parsed.append((when, hour, cid, amount, consent_value, offers_value))
        report.pseudonymised_ids = len(pseudonyms)

        if not parsed:
            raise IngestError(f"no valid payments ({report.rejected} of {report.rows} rows rejected)")
        if report.rows and report.rejected / report.rows > max_invalid_share:
            raise IngestError(f"{report.rejected} of {report.rows} rows are invalid; this does not look like a "
                              "payments export. First problems: " +
                              "; ".join(f"line {ln}: {msg}" for ln, msg in report.errors[:3]))

        parsed.sort(key=lambda r: (r[0], r[1]))
        start, last = parsed[0][0], parsed[-1][0]
        today = today or date.fromordinal(last.toordinal() + 1)
        future = [p for p in parsed if p[0] >= today]
        if future:
            raise IngestError(f"{len(future)} payment(s) are dated on or after 'today' ({today.isoformat()})")

        txns = []
        for when, hour, cid, amount, consent_value, offers_value in parsed:
            txns.append(Txn((when - start).days, hour, cid, amount))
            if consent_value is not None:
                consent[cid] = consent_value  # rows are in date order: the latest row wins
            if offers_value is not None:
                offers[cid] = offers_value

        report.loaded = len(txns)
        report.customers = len({t.customer_id for t in txns})
        report.first_date, report.last_date = start.isoformat(), last.isoformat()
        report.history_days = (today - start).days
        if report.history_days < MIN_HISTORY_DAYS:
            report.warnings.append(f"only {report.history_days} days of history; return rates need about "
                                   f"{MIN_HISTORY_DAYS} and will default to a cautious 50% where history is missing")
        if not has_consent:
            report.warnings.append("no 'consented' column: no customer can receive offers until consent is recorded")
        if report.pseudonymised_ids:
            report.warnings.append(f"{report.pseudonymised_ids} customer id(s) looked like phone numbers, emails or "
                                   "UPI ids and were replaced by salted hashes")
        if report.rejected:
            report.warnings.append(f"{report.rejected} row(s) rejected; see errors")

        return MerchantData(
            txns=txns,
            today=(today - start).days,
            start_date=start,
            consented=frozenset(cid for cid, ok in consent.items() if ok),
            offers_last_30d={cid: n for cid, n in offers.items() if n},
            report=report,
        )
    finally:
        if handle is not source and not isinstance(handle, io.StringIO):
            handle.close()


def export_payments_csv(txns, start: date, consented=frozenset(), offers_last_30d=None) -> str:
    """Write transactions in the import format (used to export the synthetic shop as a sample file)."""
    offers_last_30d = offers_last_30d or {}
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["txn_id", "date", "customer_id", "amount", "consented", "offers_30d"])
    for i, t in enumerate(txns, start=1):
        when = date.fromordinal(start.toordinal() + t.day)
        stamp = f"{when.isoformat()}T{t.hour:02d}:00:00"
        rupees = f"{t.amount_paise // 100}" if t.amount_paise % 100 == 0 else f"{t.amount_paise / 100:.2f}"
        w.writerow([f"T{i:06d}", stamp, t.customer_id, rupees, "yes" if t.customer_id in consented else "no",
                    offers_last_30d.get(t.customer_id, 0)])
    return out.getvalue()
