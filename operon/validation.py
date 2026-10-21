"""Shared monetary validation for policy checks, tools, and ledger verification."""

import re
from decimal import Decimal


def parse_amount(value) -> float:
    """Accept positive finite USD amounts without discarding signs or other text."""
    if isinstance(value, bool):
        raise ValueError("Amount must be a positive number.")
    text = str(value).strip()
    match = re.fullmatch(
        r"(?:USD\s*|\$\s*)?([+\-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)(?:\s*USD)?",
        text,
        re.IGNORECASE,
    )
    if not match:
        raise ValueError("Amount must be a positive number with at most two decimal places.")
    amount = Decimal(match.group(1).replace(",", ""))
    if not amount.is_finite() or amount <= 0:
        raise ValueError("Amount must be positive and finite.")
    result = float(amount)
    if result == float("inf"):
        raise ValueError("Amount is too large.")
    return result
