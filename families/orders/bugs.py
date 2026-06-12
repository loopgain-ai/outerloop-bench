"""Bug catalog for the orders family: (file, clean_snippet, buggy_snippet)."""

BUGS = [
    ("inventory.py",
     'SKU_RE = re.compile(r"^[A-Z]{2}-\\d{4}$")',
     'SKU_RE = re.compile(r"^[A-Za-z]{2}-\\d{4}$")'),

    ("inventory.py",
     '        if qty <= 0:\n            raise ValueError("qty must be positive")\n        self._stock[sku] = self._stock.get(sku, 0) + qty',
     '        self._stock[sku] = self._stock.get(sku, 0) + qty'),

    ("inventory.py",
     '        if self._stock.get(sku, 0) < qty:\n            return False\n        self._stock[sku] -= qty\n        return True',
     '        self._stock[sku] = self._stock.get(sku, 0) - qty\n        return True'),

    ("inventory.py",
     '        return self._stock.get(sku, 0)',
     '        return self._stock[sku]'),

    ("orders.py",
     '    raw = qty * unit_cents * (100 - discount_pct) / 100\n    return int(raw + 0.5)',
     '    raw = qty * unit_cents * (100 - discount_pct) / 100\n    return int(raw)'),

    ("orders.py",
     '    if s >= 50000:\n        rate = 10\n    elif s >= 10000:\n        rate = 5\n    else:\n        rate = 0',
     '    if s >= 10000:\n        rate = 5\n    elif s >= 50000:\n        rate = 10\n    else:\n        rate = 0'),

    ("orders.py",
     '    return start <= today <= end',
     '    return start <= today < end'),

    ("orders.py",
     '            if sum(b) + w <= max_weight:',
     '            if sum(b) + w < max_weight:'),

    ("orders.py",
     '    return "ORD-%04d%02d%02d-%06d" % (d.year, d.month, d.day, n)',
     '    return "ORD-%04d%02d%02d-%d" % (d.year, d.month, d.day, n)'),
]
