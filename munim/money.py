"""Money and percentage formatting.

Every amount in Munim is an integer number of paise. Floats are used only for
statistics, never for an amount that is stored, compared with a limit, or paid.
The formatters use integer arithmetic so the browser demo (docs/rules.js) can
reproduce them exactly.
"""

from __future__ import annotations


def fmt_inr(paise: int, decimals: bool = False, floor: bool = False) -> str:
    """Format paise as rupees with Indian digit grouping.

    Amounts round half up. Limits (largest allowed reward, budget left) pass
    floor=True so a cap is never displayed above its true value.

    >>> fmt_inr(1500)
    '₹15'
    >>> fmt_inr(123456789)
    '₹12,34,568'
    >>> fmt_inr(1090, floor=True)
    '₹10'
    >>> fmt_inr(-25050, decimals=True)
    '-₹250.50'
    """
    paise = int(paise)
    sign = "-" if paise < 0 else ""
    paise = abs(paise)
    if decimals:
        rupees, rem = divmod(paise, 100)
    elif floor and not sign:
        rupees, rem = paise // 100, 0
    else:
        rupees, rem = (paise + 50) // 100, 0
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        digits = ",".join(parts + [tail])
    out = f"{sign}₹{digits}"
    if decimals:
        out += f".{rem:02d}"
    return out


def _tenths(bps: int) -> str:
    """Basis points to a one-decimal percentage string, rounding half up."""
    bps = int(bps)
    sign = "-" if bps < 0 else ""
    tenths = (abs(bps) + 5) // 10
    return f"{sign}{tenths // 10}.{tenths % 10}"


def fmt_pct(bps: int) -> str:
    """1200 -> '12%', 1210 -> '12.1%'."""
    bps = int(bps)
    if bps % 100 == 0:
        return f"{bps // 100}%"
    return f"{_tenths(bps)}%"


def fmt_pp(bps: int) -> str:
    """Percentage points: 1210 -> '12.1 pp'."""
    return f"{_tenths(bps)} pp"


def rupees(amount: int) -> int:
    """Whole rupees to paise."""
    return int(amount) * 100
