"""Money math for the invoice pipeline. All amounts are integer cents or Decimal."""

import math
from decimal import Decimal, ROUND_HALF_UP


def to_cents(amount_str):
    """Parse a decimal string like '19.99' into integer cents, exactly."""
    return int(Decimal(amount_str) * 100)


def round_money(d):
    """Round a Decimal to 2 places, half-up (0.005 rounds to 0.01)."""
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def pct(part, whole):
    """part/whole as a percentage with one decimal place, half-up. 0 if whole==0."""
    if whole == 0:
        return 0.0
    return math.floor(float(part) / float(whole) * 1000 + 0.5) / 10


def fmt_money(cents):
    """Format integer cents as a dollar string: 123456 -> '$1,234.56', -123 -> '-$1.23'."""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return "%s$%s.%02d" % (sign, format(cents // 100, ","), cents % 100)


def prorate(total_cents, weights):
    """Split total_cents across weights so the parts sum to total_cents exactly.

    Largest-remainder method: floor each proportional share, then hand out the
    leftover cents to the largest fractional remainders (index order on ties).
    """
    total_weight = sum(weights)
    if total_weight == 0:
        raise ValueError("weights sum to zero")
    shares = [total_cents * w / total_weight for w in weights]
    floors = [int(s) for s in shares]
    leftover = total_cents - sum(floors)
    order = sorted(range(len(weights)), key=lambda i: (-(shares[i] - floors[i]), i))
    for i in order[:leftover]:
        floors[i] += 1
    return floors
