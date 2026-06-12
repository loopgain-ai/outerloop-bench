"""Line parsing for the invoice pipeline's CSV-ish input format."""

from decimal import Decimal


def parse_line(line):
    """Split one CSV line into fields.

    Rules (RFC-4180 style): fields are comma-separated; a field may be wrapped
    in double quotes, in which case it can contain commas; a doubled quote ("")
    inside a quoted field is a literal quote character.
    """
    fields = []
    current = []
    in_quotes = False
    i = 0
    while i < len(line):
        c = line[i]
        if c == '"':
            if in_quotes and i + 1 < len(line) and line[i + 1] == '"':
                current.append('"')
                i += 2
                continue
            in_quotes = not in_quotes
        elif c == "," and not in_quotes:
            fields.append("".join(current).strip())
            current = []
        else:
            current.append(c)
        i += 1
    fields.append("".join(current).strip())
    return fields


def parse_amount(s):
    """Parse a money string like '$1,234.56' or '12.30' into a Decimal."""
    s = s.strip().lstrip("$").replace(",", "")
    return Decimal(s)


def parse_record(line):
    """Parse 'date,category,description,amount' into a dict.

    date stays a string, amount becomes a Decimal via parse_amount.
    """
    fields = parse_line(line)
    if len(fields) != 4:
        raise ValueError("bad record: %r" % line)
    return {
        "date": fields[0],
        "category": fields[1],
        "description": fields[2],
        "amount": parse_amount(fields[3]),
    }
