"""Test suite for the invoice pipeline. THE TESTS ARE THE SPEC — do not modify this file."""

from datetime import date
from decimal import Decimal

import pytest

from dates import add_business_days, business_days, days_in_range, iso_week, quarter
from money import fmt_money, pct, prorate, round_money, to_cents
from parsing import parse_amount, parse_line, parse_record
from report import (
    by_category,
    category_shares,
    invoice_total_with_tax,
    load_records,
    top_n,
    total,
)


# --- money.to_cents ---

def test_to_cents_simple():
    assert to_cents("5.00") == 500

def test_to_cents_exact_1999():
    assert to_cents("19.99") == 1999

def test_to_cents_exact_113():
    assert to_cents("1.13") == 113

def test_to_cents_dime():
    assert to_cents("0.10") == 10


# --- money.round_money ---

def test_round_money_down():
    assert round_money(Decimal("2.344")) == Decimal("2.34")

def test_round_money_half_up():
    assert round_money(Decimal("2.345")) == Decimal("2.35")

def test_round_money_half_up_2125():
    assert round_money(Decimal("2.125")) == Decimal("2.13")


# --- money.pct ---

def test_pct_third():
    assert pct(1, 3) == 33.3

def test_pct_two_thirds():
    assert pct(2, 3) == 66.7

def test_pct_exact():
    assert pct(1, 8) == 12.5

def test_pct_zero_whole():
    assert pct(5, 0) == 0.0


# --- money.fmt_money ---

def test_fmt_money_thousands():
    assert fmt_money(123456) == "$1,234.56"

def test_fmt_money_small():
    assert fmt_money(99) == "$0.99"

def test_fmt_money_negative():
    assert fmt_money(-123) == "-$1.23"

def test_fmt_money_five():
    assert fmt_money(500) == "$5.00"


# --- money.prorate ---

def test_prorate_sums_exactly_three_ways():
    assert prorate(100, [1, 1, 1]) == [34, 33, 33]

def test_prorate_even_split():
    assert prorate(100, [1, 1]) == [50, 50]

def test_prorate_odd_cent():
    assert prorate(101, [1, 1]) == [51, 50]

def test_prorate_200_three_ways():
    assert prorate(200, [1, 1, 1]) == [67, 67, 66]

def test_prorate_zero_weights():
    with pytest.raises(ValueError):
        prorate(100, [0, 0])


# --- dates.business_days ---

def test_business_days_full_week():
    assert business_days(date(2026, 6, 1), date(2026, 6, 5)) == 5  # Mon..Fri

def test_business_days_weekend_only():
    assert business_days(date(2026, 6, 6), date(2026, 6, 7)) == 0  # Sat..Sun

def test_business_days_same_day():
    assert business_days(date(2026, 6, 1), date(2026, 6, 1)) == 1  # a Monday

def test_business_days_bad_order():
    with pytest.raises(ValueError):
        business_days(date(2026, 6, 5), date(2026, 6, 1))


# --- dates.add_business_days ---

def test_add_business_days_over_weekend():
    assert add_business_days(date(2026, 6, 5), 1) == date(2026, 6, 8)  # Fri+1 -> Mon

def test_add_business_days_within_week():
    assert add_business_days(date(2026, 6, 1), 4) == date(2026, 6, 5)  # Mon+4 -> Fri

def test_add_business_days_two_over_weekend():
    assert add_business_days(date(2026, 6, 4), 2) == date(2026, 6, 8)  # Thu+2 -> Mon


# --- dates.iso_week ---

def test_iso_week_year_boundary():
    assert iso_week(date(2027, 1, 1)) == (2026, 53)

def test_iso_week_midyear():
    assert iso_week(date(2026, 6, 10)) == (2026, 24)


# --- dates.quarter ---

def test_quarter_q1():
    assert quarter(date(2026, 2, 14)) == 1

def test_quarter_q4():
    assert quarter(date(2026, 10, 1)) == 4


# --- dates.days_in_range ---

def test_days_in_range_same_day():
    assert days_in_range(date(2026, 6, 1), date(2026, 6, 1)) == 1

def test_days_in_range_three():
    assert days_in_range(date(2026, 6, 1), date(2026, 6, 3)) == 3


# --- parsing.parse_line ---

def test_parse_line_plain():
    assert parse_line("a,b,c") == ["a", "b", "c"]

def test_parse_line_quoted_comma():
    assert parse_line('a,"b,c",d') == ["a", "b,c", "d"]

def test_parse_line_doubled_quotes():
    assert parse_line('x,"say ""hi"", ok",3') == ["x", 'say "hi", ok', "3"]

def test_parse_line_single_quoted_field():
    assert parse_line('"q"') == ["q"]


# --- parsing.parse_amount ---

def test_parse_amount_plain():
    assert parse_amount("12.30") == Decimal("12.30")

def test_parse_amount_dollar_comma():
    assert parse_amount("$1,234.56") == Decimal("1234.56")


# --- parsing.parse_record ---

def test_parse_record_plain():
    r = parse_record("2026-06-01,tools,license,49.00")
    assert r == {"date": "2026-06-01", "category": "tools",
                 "description": "license", "amount": Decimal("49.00")}

def test_parse_record_quoted_description():
    r = parse_record('2026-06-02,travel,"flight, return leg",812.40')
    assert r["description"] == "flight, return leg"
    assert r["amount"] == Decimal("812.40")


# --- report ---

LINES = [
    "2026-06-01,tools,license,49.00",
    "2026-06-02,tools,plugin,15.50",
    "2026-06-03,travel,train,30.25",
]


def _records(lines=LINES):
    return load_records(lines)


def test_total_basic():
    assert total(_records()) == Decimal("94.75")

def test_by_category_sorted_and_summed():
    g = by_category(_records())
    assert list(g) == ["tools", "travel"]
    assert g["tools"] == Decimal("64.50")
    assert g["travel"] == Decimal("30.25")

def test_top_n_descending():
    t = top_n(_records(), 2)
    assert [r["description"] for r in t] == ["license", "train"]

def test_top_n_tie_alphabetical():
    recs = load_records([
        "2026-06-01,a,zeta,5.00",
        "2026-06-01,a,alpha,5.00",
        "2026-06-01,a,small,3.00",
    ])
    t = top_n(recs, 2)
    assert [r["description"] for r in t] == ["alpha", "zeta"]

def test_category_shares_two_thirds():
    recs = load_records([
        "2026-06-01,a,x,2.00",
        "2026-06-01,b,y,1.00",
    ])
    shares = category_shares(recs)
    assert shares["a"] == 66.7
    assert shares["b"] == 33.3

def test_load_records_quoted_line():
    recs = load_records(['2026-06-02,travel,"flight, return leg",812.40'])
    assert recs[0]["amount"] == Decimal("812.40")

def test_invoice_tax_rounds_half_up():
    assert invoice_total_with_tax(1000, 8.875) == 1089  # tax 88.75 -> 89

def test_invoice_tax_exact():
    assert invoice_total_with_tax(1000, 5) == 1050
