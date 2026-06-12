"""Bug catalog for the textstats family: (file, clean_snippet, buggy_snippet)."""

BUGS = [
    ("textstats.py",
     'return re.sub(r"\\s+", " ", text).strip()',
     'return text.replace("  ", " ").strip()'),

    ("textstats.py",
     'parts = re.split(r"[.!?]\\s+", text)',
     'parts = re.split(r"\\.\\s+", text)'),

    ("textstats.py",
     'words = [w.lower() for w in text.split()]',
     'words = text.split()'),

    ("textstats.py",
     'ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))\n    return [w for w, _ in ordered[:k]]',
     'ordered = sorted(counts.items(), key=lambda kv: -kv[1])\n    return [w for w, _ in ordered[:k]]'),

    ("textstats.py",
     'if n % 2 == 1:\n        return xs[n // 2]\n    return (xs[n // 2 - 1] + xs[n // 2]) / 2',
     'return xs[n // 2]'),

    ("textstats.py",
     'for i in range(len(xs) - w + 1):',
     'for i in range(len(xs) - w):'),

    ("textstats.py",
     'f = int(k)\n    c = min(f + 1, len(xs) - 1)\n    return xs[f] + (xs[c] - xs[f]) * (k - f)',
     'f = int(k)\n    return xs[f]'),

    ("textstats.py",
     'return s.strip("-")',
     'return s'),

    ("textstats.py",
     'minutes = int(m.group(2) or 0)\n    return hours * 60 + minutes',
     'return hours * 60'),

    ("textstats.py",
     'def __init__(self, counts=None):\n        self.counts = {} if counts is None else counts',
     'def __init__(self, counts={}):\n        self.counts = counts'),
]
