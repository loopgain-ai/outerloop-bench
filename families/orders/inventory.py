"""Inventory tracking for the order system."""

import re

SKU_RE = re.compile(r"^[A-Z]{2}-\d{4}$")


def valid_sku(s):
    """SKUs look like 'AB-1234': two uppercase letters, hyphen, four digits."""
    return bool(SKU_RE.match(s))


class Inventory:
    """In-memory stock ledger."""

    def __init__(self):
        self._stock = {}

    def add(self, sku, qty):
        """Add qty units (qty must be positive, sku must be valid)."""
        if not valid_sku(sku):
            raise ValueError("invalid sku: %s" % sku)
        if qty <= 0:
            raise ValueError("qty must be positive")
        self._stock[sku] = self._stock.get(sku, 0) + qty

    def available(self, sku):
        """Units on hand; 0 for unknown SKUs."""
        return self._stock.get(sku, 0)

    def reserve(self, sku, qty):
        """Atomically take qty units if available. True on success, False otherwise."""
        if qty <= 0:
            raise ValueError("qty must be positive")
        if self._stock.get(sku, 0) < qty:
            return False
        self._stock[sku] -= qty
        return True
