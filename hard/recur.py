"""Recurrence rules for billing schedules.

Supported rule strings (case-insensitive):
  "every N days"             anchored at `anchor`: occurrences are anchor, anchor+N, ...
  "2nd tuesday of month"     Nth weekday (1st..5th); months without that Nth roll forward
  "last friday of month"
  "last business day of month"

next_occurrence(rule, after, anchor=None) returns the first occurrence STRICTLY
AFTER `after`. Unknown rules raise ValueError.
"""

import re
from datetime import date, timedelta

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def next_occurrence(rule, after, anchor=None):
    m = re.match(r"every (\d+) days", rule)
    if m:
        n = int(m.group(1))
        return after + timedelta(days=n)
    m = re.match(r"(\d)(?:st|nd|rd|th) (\w+) of month", rule)
    if m:
        nth = int(m.group(1))
        wd = WEEKDAYS.index(m.group(2))
        d = date(after.year, after.month, 1)
        offset = (wd - d.weekday()) % 7
        cand = d + timedelta(days=offset + (nth - 1) * 7)
        if cand <= after:
            nxt = date(after.year + (after.month == 12), after.month % 12 + 1, 1)
            offset = (wd - nxt.weekday()) % 7
            cand = nxt + timedelta(days=offset + (nth - 1) * 7)
        return cand
    m = re.match(r"last (\w+) of month", rule)
    if m:
        name = m.group(1)
        d = after
        for _ in range(60):
            d = d + timedelta(days=1)
            if name == "business day":
                ok = d.weekday() < 6
            else:
                ok = d.weekday() == WEEKDAYS.index(name)
            if ok and (d + timedelta(days=7)).month != d.month:
                return d
        return None
    raise ValueError("unknown rule: %s" % rule)
