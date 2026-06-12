"""Date helpers for the invoice pipeline."""

from datetime import date, timedelta


def business_days(start, end):
    """Count of weekdays (Mon-Fri) from start to end, INCLUSIVE of both ends."""
    if end < start:
        raise ValueError("end before start")
    n = 0
    d = start
    while d <= end:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


def add_business_days(d, n):
    """The date n business days after d (n >= 0). Weekends are skipped."""
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def iso_week(d):
    """(iso_year, iso_week) for a date — ISO-8601 week numbering."""
    iso = d.isocalendar()
    return (iso[0], iso[1])


def quarter(d):
    """Calendar quarter 1-4."""
    return (d.month - 1) // 3 + 1


def days_in_range(start, end):
    """Number of days from start to end, inclusive of both ends."""
    return (end - start).days + 1
