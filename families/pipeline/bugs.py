"""Bug catalog for the pipeline family: (file, clean_snippet, buggy_snippet)."""

BUGS = [
    ("money.py",
     "return int(Decimal(amount_str) * 100)",
     "return int(float(amount_str) * 100)"),

    ("money.py",
     'return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)',
     'return d.quantize(Decimal("0.01"))'),

    ("money.py",
     "return math.floor(float(part) / float(whole) * 1000 + 0.5) / 10",
     "return int(part / whole * 1000) / 10"),

    ("money.py",
     'sign = "-" if cents < 0 else ""\n    cents = abs(cents)\n    return "%s$%s.%02d" % (sign, format(cents // 100, ","), cents % 100)',
     'dollars = cents / 100\n    return "$%.2f" % dollars'),

    ("money.py",
     "shares = [total_cents * w / total_weight for w in weights]\n    floors = [int(s) for s in shares]\n    leftover = total_cents - sum(floors)\n    order = sorted(range(len(weights)), key=lambda i: (-(shares[i] - floors[i]), i))\n    for i in order[:leftover]:\n        floors[i] += 1\n    return floors",
     "return [round(total_cents * w / total_weight) for w in weights]"),

    ("dates.py",
     "while d <= end:",
     "while d < end:"),

    ("dates.py",
     "while n > 0:\n        d += timedelta(days=1)\n        if d.weekday() < 5:\n            n -= 1\n    return d",
     "while n > 0:\n        d += timedelta(days=1)\n        n -= 1\n        if d.weekday() >= 5:\n            continue\n    return d"),

    ("dates.py",
     "iso = d.isocalendar()\n    return (iso[0], iso[1])",
     'return (d.year, int(d.strftime("%W")))'),

    ("dates.py",
     "return (end - start).days + 1",
     "return (end - start).days"),

    ("parsing.py",
     'fields = []\n    current = []\n    in_quotes = False\n    i = 0\n    while i < len(line):\n        c = line[i]\n        if c == \'"\':\n            if in_quotes and i + 1 < len(line) and line[i + 1] == \'"\':\n                current.append(\'"\')\n                i += 2\n                continue\n            in_quotes = not in_quotes\n        elif c == "," and not in_quotes:\n            fields.append("".join(current).strip())\n            current = []\n        else:\n            current.append(c)\n        i += 1\n    fields.append("".join(current).strip())\n    return fields',
     'return [f.strip() for f in line.split(",")]'),

    ("parsing.py",
     's = s.strip().lstrip("$").replace(",", "")',
     's = s.strip().lstrip("$")'),

    ("report.py",
     'ordered = sorted(records, key=lambda r: (-r["amount"], r["description"]))',
     'ordered = sorted(records, key=lambda r: -r["amount"])'),

    ("report.py",
     "return subtotal_cents + int(tax + 0.5)",
     "return subtotal_cents + int(tax)"),
]
