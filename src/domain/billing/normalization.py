"""Deterministic normalization for shipping charge fields."""

import re
from dataclasses import replace

from domain.billing.entities import Charge

_CHARGE_ALIASES = {
    "handling fee": "Handling Charge",
    "h/d fee": "Handling Charge",
    "handling charge": "Handling Charge",
    "doc fee": "Documentation Fee",
    "documentation fee": "Documentation Fee",
    "thc": "Terminal Handling Charge",
    "terminal handling charge": "Terminal Handling Charge",
    "trucking fee": "Trucking Charge",
    "trucking charge": "Trucking Charge",
    "customs fee": "Customs Clearance Fee",
    "customs clearance fee": "Customs Clearance Fee",
    "storage fee": "Storage Charge",
    "storage charge": "Storage Charge",
}

_PAYMENT_TERMS = {
    "P": "PP",
    "PP": "PP",
    "PREPAID": "PP",
    "PRE-PAID": "PP",
    "C": "CC",
    "CC": "CC",
    "COLLECT": "CC",
    "FREIGHT COLLECT": "CC",
    "预付": "PP",
    "到付": "CC",
}

_CURRENCY_ALIASES = {
    "RMB": "CNY",
    "人民币": "CNY",
    "美元": "USD",
    "美金": "USD",
}


def _normalized_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def normalize_party_identity(value: str | None) -> str:
    """Normalize a legal party while ignoring a short office/location suffix."""

    normalized = re.sub(r"\s+", " ", (value or "").strip()).casefold()
    return re.sub(r"\s*\([a-z0-9-]{2,5}\)\s*$", "", normalized).strip()


def normalize_charge_name(raw_name: str | None) -> str | None:
    """Map known aliases while preserving unknown non-empty names."""

    if raw_name is None or not raw_name.strip():
        return None
    cleaned = re.sub(r"\s+", " ", raw_name.strip())
    return _CHARGE_ALIASES.get(_normalized_key(cleaned), cleaned)


def normalize_currency(currency: str | None) -> str | None:
    """Normalize a currency token without claiming it is valid."""

    if currency is None or not currency.strip():
        return None
    value = currency.strip().upper()
    return _CURRENCY_ALIASES.get(value, value)


def normalize_payment_term(payment_term: str | None) -> str | None:
    """Normalize prepaid/collect aliases."""

    if payment_term is None or not payment_term.strip():
        return None
    value = re.sub(r"\s+", " ", payment_term.strip()).upper()
    return _PAYMENT_TERMS.get(value, value)


def normalize_charge(charge: Charge) -> Charge:
    """Return a normalized copy while retaining the raw charge name."""

    return replace(
        charge,
        canonical_name=normalize_charge_name(charge.raw_name or charge.canonical_name),
        currency=normalize_currency(charge.currency),
        payment_term=normalize_payment_term(charge.payment_term),
    )
