"""Report aggregation for the invoice pipeline."""

from decimal import Decimal

from money import pct, round_money
from parsing import parse_record


def load_records(lines):
    """Parse every non-empty line into a record dict."""
    return [parse_record(ln) for ln in lines if ln.strip()]


def total(records):
    """Sum of record amounts as a Decimal rounded to 2 places."""
    t = Decimal("0")
    for r in records:
        t += r["amount"]
    return round_money(t)


def by_category(records):
    """{category: rounded Decimal subtotal}, categories sorted alphabetically."""
    g = {}
    for r in records:
        g.setdefault(r["category"], Decimal("0"))
        g[r["category"]] += r["amount"]
    return {k: round_money(g[k]) for k in sorted(g)}


def top_n(records, n):
    """The n largest records by amount, descending; ties broken by description A-Z."""
    ordered = sorted(records, key=lambda r: (-r["amount"], r["description"]))
    return ordered[:n]


def category_shares(records):
    """{category: % of grand total, one decimal place} using money.pct."""
    g = by_category(records)
    grand = sum(g.values())
    return {k: pct(v, grand) for k, v in g.items()}


def invoice_total_with_tax(subtotal_cents, tax_rate_pct):
    """Total in cents: subtotal plus tax, tax rounded half-up to the nearest cent."""
    tax = subtotal_cents * tax_rate_pct / 100
    return subtotal_cents + int(tax + 0.5)
