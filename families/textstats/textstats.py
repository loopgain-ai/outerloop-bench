"""Small text/number utilities used by a report generator."""

import re


def normalize_whitespace(text):
    """Collapse every run of whitespace to a single space and strip the ends."""
    return re.sub(r"\s+", " ", text).strip()


def sentence_split(text):
    """Split text into sentences on ./!/? boundaries, trailing punctuation removed."""
    parts = re.split(r"[.!?]\s+", text)
    return [p.strip().rstrip(".!?") for p in parts if p.strip()]


def word_count(text):
    """Number of whitespace-separated words."""
    return len(text.split())


def top_k_words(text, k):
    """The k most frequent words, case-insensitive, ties broken alphabetically."""
    words = [w.lower() for w in text.split()]
    counts = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, _ in ordered[:k]]


def median(xs):
    """Median of a list of numbers."""
    if not xs:
        raise ValueError("median of empty list")
    xs = sorted(xs)
    n = len(xs)
    if n % 2 == 1:
        return xs[n // 2]
    return (xs[n // 2 - 1] + xs[n // 2]) / 2


def moving_average(xs, w):
    """Moving average with window w (one value per full window)."""
    if w <= 0:
        raise ValueError("window must be positive")
    out = []
    for i in range(len(xs) - w + 1):
        out.append(sum(xs[i:i + w]) / w)
    return out


def percentile(xs, p):
    """p-th percentile (0-100) with linear interpolation between ranks."""
    if not xs:
        raise ValueError("percentile of empty list")
    xs = sorted(xs)
    k = (len(xs) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def slugify(text):
    """URL slug: lowercase, alphanumeric runs joined by single hyphens."""
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def parse_duration(s):
    """Parse '2h', '45m', or '1h30m' into total minutes."""
    m = re.match(r"(?:(\d+)h)?(?:(\d+)m)?$", s)
    if not m or (m.group(1) is None and m.group(2) is None):
        raise ValueError("bad duration: %s" % s)
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    return hours * 60 + minutes


class WordCounter:
    """Accumulates word counts across multiple documents."""

    def __init__(self, counts=None):
        self.counts = {} if counts is None else counts

    def add(self, text):
        for w in text.lower().split():
            self.counts[w] = self.counts.get(w, 0) + 1

    def most_common(self):
        return sorted(self.counts.items(), key=lambda kv: (-kv[1], kv[0]))
