"""Test suite for the order system. THE TESTS ARE THE SPEC — do not modify this file."""

from datetime import date

import pytest

from inventory import Inventory, valid_sku
from orders import (
    format_order_id,
    line_total,
    order_total,
    promo_active,
    split_shipments,
)


# --- valid_sku ---

def test_sku_valid():
    assert valid_sku("AB-1234") is True

def test_sku_lowercase_rejected():
    assert valid_sku("ab-1234") is False

def test_sku_too_many_digits():
    assert valid_sku("AB-12345") is False

def test_sku_one_letter():
    assert valid_sku("A-1234") is False


# --- Inventory ---

def test_add_and_available():
    inv = Inventory()
    inv.add("AB-1234", 5)
    assert inv.available("AB-1234") == 5

def test_available_unknown_sku_is_zero():
    inv = Inventory()
    assert inv.available("ZZ-9999") == 0

def test_add_invalid_sku_raises():
    inv = Inventory()
    with pytest.raises(ValueError):
        inv.add("bad", 1)

def test_add_zero_qty_raises():
    inv = Inventory()
    with pytest.raises(ValueError):
        inv.add("AB-1234", 0)

def test_reserve_success():
    inv = Inventory()
    inv.add("AB-1234", 5)
    assert inv.reserve("AB-1234", 3) is True
    assert inv.available("AB-1234") == 2

def test_reserve_insufficient_leaves_stock():
    inv = Inventory()
    inv.add("AB-1234", 2)
    assert inv.reserve("AB-1234", 3) is False
    assert inv.available("AB-1234") == 2

def test_reserve_exact():
    inv = Inventory()
    inv.add("AB-1234", 4)
    assert inv.reserve("AB-1234", 4) is True
    assert inv.available("AB-1234") == 0


# --- line_total ---

def test_line_total_no_discount():
    assert line_total(3, 1000, 0) == 3000

def test_line_total_rounds_half_up():
    assert line_total(1, 999, 50) == 500  # 499.5 -> 500

def test_line_total_discount():
    assert line_total(2, 125, 10) == 225

def test_line_total_truncation_trap():
    assert line_total(1, 105, 50) == 53  # 52.5 -> 53


# --- order_total ---

def test_order_total_no_discount():
    assert order_total([5000]) == 5000

def test_order_total_five_pct():
    assert order_total([6000, 5000]) == 10450  # 11000 -> 5% off

def test_order_total_ten_pct():
    assert order_total([30000, 25000]) == 49500  # 55000 -> 10% off


# --- promo_active ---

def test_promo_start_inclusive():
    assert promo_active(date(2026, 6, 1), date(2026, 6, 1), date(2026, 6, 30)) is True

def test_promo_end_inclusive():
    assert promo_active(date(2026, 6, 30), date(2026, 6, 1), date(2026, 6, 30)) is True

def test_promo_after_end():
    assert promo_active(date(2026, 7, 1), date(2026, 6, 1), date(2026, 6, 30)) is False


# --- split_shipments ---

def test_split_basic():
    assert split_shipments([5, 5, 5], 10) == [[5, 5], [5]]

def test_split_exact_fit():
    assert split_shipments([6, 4], 10) == [[6, 4]]

def test_split_oversize_raises():
    with pytest.raises(ValueError):
        split_shipments([11], 10)

def test_split_empty():
    assert split_shipments([], 10) == []


# --- format_order_id ---

def test_order_id_padded():
    assert format_order_id(123, date(2026, 6, 1)) == "ORD-20260601-000123"

def test_order_id_single_digit():
    assert format_order_id(1, date(2026, 12, 31)) == "ORD-20261231-000001"
