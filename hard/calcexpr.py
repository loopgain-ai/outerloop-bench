"""Tiny arithmetic expression evaluator.

Grammar: integers/decimals, + - * /, parentheses, unary minus, spaces allowed.
evaluate(s) returns int when the result is integral, else float.

Errors are ValueErrors with EXACT messages (positions are character offsets
into the original string):
  "empty expression"
  "division by zero"
  "unexpected 'X' at N"   (offending character at offset N)
  "missing ')' at N"      (N = offset where the ')' should have been, i.e. len(s) when input ends)
"""


def _tokenize(s):
    tokens = []
    i = 0
    while i < len(s):
        c = s[i]
        if c.isspace():
            i += 1
            continue
        if c.isdigit() or c == ".":
            j = i
            while j < len(s) and (s[j].isdigit() or s[j] == "."):
                j += 1
            tokens.append(("num", float(s[i:j])))
            i = j
            continue
        if c in "+-*/()":
            tokens.append((c, c))
            i += 1
            continue
        raise ValueError("bad character")
    return tokens


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos][0] if self.pos < len(self.tokens) else None

    def take(self):
        t = self.tokens[self.pos]
        self.pos += 1
        return t

    def expr(self):
        v = self.term()
        while self.peek() in ("+", "-"):
            op = self.take()[0]
            r = self.term()
            v = v + r if op == "+" else v - r
        return v

    def term(self):
        v = self.factor()
        while self.peek() in ("*", "/"):
            op = self.take()[0]
            r = self.factor()
            if op == "/":
                if r == 0:
                    raise ValueError("division error")
                v = v / r
            else:
                v = v * r
        return v

    def factor(self):
        t = self.peek()
        if t == "-":
            self.take()
            return -self.factor()
        if t == "num":
            return self.take()[1]
        if t == "(":
            self.take()
            v = self.expr()
            if self.peek() != ")":
                raise ValueError("unbalanced parentheses")
            self.take()
            return v
        raise ValueError("invalid expression")


def evaluate(s):
    if not s.strip():
        raise ValueError("empty expression")
    tokens = _tokenize(s)
    p = _Parser(tokens)
    v = p.expr()
    if p.peek() is not None:
        raise ValueError("unbalanced parentheses")
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v
