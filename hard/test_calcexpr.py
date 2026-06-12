"""Spec for the expression evaluator. THE TESTS ARE THE SPEC — do not modify this file."""

import pytest

from calcexpr import evaluate


# values

def test_precedence():
    assert evaluate("2+3*4") == 14

def test_parens():
    assert evaluate("(2+3)*4") == 20

def test_unary_minus_leading():
    assert evaluate("-3+5") == 2

def test_unary_minus_after_operator():
    assert evaluate("2*-3") == -6

def test_division_float():
    assert evaluate("10/4") == 2.5

def test_nested():
    assert evaluate("1 + 2 * (3 - 1)") == 5

def test_decimal():
    assert evaluate("3.5*2") == 7

def test_whitespace():
    assert evaluate(" 7 ") == 7


# errors — exact messages with character offsets into the original string

def test_empty():
    with pytest.raises(ValueError, match=r"^empty expression$"):
        evaluate("   ")

def test_division_by_zero():
    with pytest.raises(ValueError, match=r"^division by zero$"):
        evaluate("8/(3-3)")

def test_double_operator_position():
    with pytest.raises(ValueError, match=r"^unexpected '\+' at 2$"):
        evaluate("2++3")

def test_letter_position():
    with pytest.raises(ValueError, match=r"^unexpected 'a' at 0$"):
        evaluate("abc")

def test_letter_position_offset():
    with pytest.raises(ValueError, match=r"^unexpected 'x' at 4$"):
        evaluate("1 + x")

def test_missing_close_paren():
    with pytest.raises(ValueError, match=r"^missing '\)' at 4$"):
        evaluate("(1+2")

def test_stray_close_paren():
    with pytest.raises(ValueError, match=r"^unexpected '\)' at 3$"):
        evaluate("1+2)")
