"""Order math for the order system. Amounts are integer cents."""


def line_total(qty, unit_cents, discount_pct):
    """Total cents for a line: qty x unit price, percent discount, rounded half-up."""
    raw = qty * unit_cents * (100 - discount_pct) / 100
    return int(raw + 0.5)


def order_total(line_totals):
    """Sum of line totals with a volume discount applied to the whole order.

    >= 50000 cents -> 10% off; >= 10000 cents -> 5% off; otherwise none.
    Only the best single tier applies. Result rounded half-up.
    """
    s = sum(line_totals)
    if s >= 50000:
        rate = 10
    elif s >= 10000:
        rate = 5
    else:
        rate = 0
    return int(s * (100 - rate) / 100 + 0.5)


def promo_active(today, start, end):
    """A promo runs from start to end, INCLUSIVE of both ends."""
    return start <= today <= end


def split_shipments(weights, max_weight):
    """Pack item weights into shipments, first-fit in the given order.

    Each shipment's total stays <= max_weight (exact fits allowed). An item
    heavier than max_weight is a ValueError.
    """
    bins = []
    for w in weights:
        if w > max_weight:
            raise ValueError("item exceeds max weight")
        for b in bins:
            if sum(b) + w <= max_weight:
                b.append(w)
                break
        else:
            bins.append([w])
    return bins


def format_order_id(n, d):
    """Order ids look like ORD-20260601-000123 (date + 6-digit zero-padded number)."""
    return "ORD-%04d%02d%02d-%06d" % (d.year, d.month, d.day, n)
