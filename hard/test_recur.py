"""Spec for the recurrence engine. THE TESTS ARE THE SPEC — do not modify this file."""

from datetime import date

import pytest

from recur import next_occurrence


# every N days — anchored arithmetic, not "after + N"

def test_every_n_days_on_anchor():
    assert next_occurrence("every 3 days", date(2026, 1, 5),
                           anchor=date(2026, 1, 5)) == date(2026, 1, 8)

def test_every_n_days_between_phases():
    assert next_occurrence("every 3 days", date(2026, 1, 6),
                           anchor=date(2026, 1, 5)) == date(2026, 1, 8)

def test_every_n_days_long_after_anchor():
    assert next_occurrence("every 7 days", date(2026, 3, 1),
                           anchor=date(2026, 1, 5)) == date(2026, 3, 2)


# Nth weekday of month

def test_2nd_tuesday_before():
    assert next_occurrence("2nd tuesday of month", date(2026, 6, 1)) == date(2026, 6, 9)

def test_2nd_tuesday_rolls_to_next_month():
    assert next_occurrence("2nd tuesday of month", date(2026, 6, 9)) == date(2026, 7, 14)

def test_5th_friday_skips_months_without_one():
    # June 2026 has four Fridays; the next 5th Friday is 2026-07-31.
    assert next_occurrence("5th friday of month", date(2026, 6, 1)) == date(2026, 7, 31)

def test_case_insensitive():
    assert next_occurrence("2ND TUESDAY OF MONTH", date(2026, 6, 1)) == date(2026, 6, 9)


# last weekday of month

def test_last_friday_same_month():
    assert next_occurrence("last friday of month", date(2026, 6, 25)) == date(2026, 6, 26)

def test_last_friday_rolls_over():
    assert next_occurrence("last friday of month", date(2026, 6, 26)) == date(2026, 7, 31)


# last business day of month

def test_last_business_day_weekday_end():
    assert next_occurrence("last business day of month", date(2026, 6, 29)) == date(2026, 6, 30)

def test_last_business_day_weekend_end():
    # 2027-01-31 is a Sunday -> last business day is Friday 2027-01-29.
    assert next_occurrence("last business day of month", date(2027, 1, 15)) == date(2027, 1, 29)

def test_last_business_day_rolls_over():
    # After Jan's last business day: February 2027 ends Sunday the 28th -> Friday the 26th.
    assert next_occurrence("last business day of month", date(2027, 1, 29)) == date(2027, 2, 26)


# errors

def test_unknown_rule_raises():
    with pytest.raises(ValueError):
        next_occurrence("whenever", date(2026, 6, 1))
