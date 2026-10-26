"""Existing-bill matching in the configured business priority order."""

from collections.abc import Callable
from dataclasses import dataclass

from domain.billing.entities import Bill, BillingDocument, Charge
from domain.billing.normalization import normalize_party_identity


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Candidate result for one extracted charge."""

    candidates: tuple[Bill, ...]
    rule: str | None

    @property
    def unique_match(self) -> Bill | None:
        return self.candidates[0] if len(self.candidates) == 1 else None

    @property
    def ambiguous(self) -> bool:
        return len(self.candidates) > 1


def _same(left: str | None, right: str | None) -> bool:
    return bool(left and right and left.strip().casefold() == right.strip().casefold())


def _charge_name_matches(charge: Charge, bill: Bill) -> bool:
    return _same(charge.canonical_name, bill.charge.canonical_name)


def _same_party(left: str | None, right: str | None) -> bool:
    return bool(
        left and right and normalize_party_identity(left) == normalize_party_identity(right)
    )


def match_existing_bill(
    document: BillingDocument, charge: Charge, existing_bills: tuple[Bill, ...]
) -> MatchResult:
    """Apply the four matching rules in order, stopping at the first non-empty set."""

    info = document.document_info
    parties = document.parties
    rules: tuple[tuple[str, Callable[[Bill], bool]], ...] = (
        (
            "reference_no_and_charge",
            lambda bill: (
                _same(info.reference_no, bill.document_info.reference_no)
                and _charge_name_matches(charge, bill)
            ),
        ),
        (
            "bill_of_lading_charge_currency",
            lambda bill: (
                _same(info.bill_of_lading_no, bill.document_info.bill_of_lading_no)
                and _charge_name_matches(charge, bill)
                and _same(charge.currency, bill.charge.currency)
            ),
        ),
        (
            "booking_charge_currency",
            lambda bill: (
                _same(info.booking_no, bill.document_info.booking_no)
                and _charge_name_matches(charge, bill)
                and _same(charge.currency, bill.charge.currency)
            ),
        ),
        (
            "container_parties_date_amount",
            lambda bill: (
                _same(info.container_no, bill.document_info.container_no)
                and _same_party(parties.issuer, bill.parties.issuer)
                and _same_party(parties.recipient, bill.parties.recipient)
                and info.document_date is not None
                and info.document_date == bill.document_info.document_date
                and charge.amount is not None
                and charge.amount == bill.charge.amount
            ),
        ),
    )
    for name, predicate in rules:
        matches = tuple(bill for bill in existing_bills if predicate(bill))
        if matches:
            return MatchResult(matches, name)
    return MatchResult((), None)
