"""Framework-free domain entities for extracted and existing bills."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from domain.billing.enums import ChargeDirection, Operation, PostingType


@dataclass(frozen=True, slots=True)
class Evidence:
    """Traceable source evidence for an extracted value."""

    source_name: str
    source_text: str
    page: int | None = None
    sheet: str | None = None
    row: int | None = None
    attachment_name: str | None = None
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class ExplicitChangeEvidence:
    """Source-grounded proof that one field was explicitly requested to change."""

    field_name: str
    new_value: str
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class SourceMaterial:
    """Validation corpus belonging to one concrete input source."""

    source_id: str
    source_name: str
    text: str


@dataclass(frozen=True, slots=True)
class DocumentInfo:
    """Document-level billing information."""

    document_type: str | None = None
    reference_no: str | None = None
    document_date: date | None = None
    bill_of_lading_no: str | None = None
    booking_no: str | None = None
    container_no: str | None = None


@dataclass(frozen=True, slots=True)
class TransactionParties:
    """Issuer and recipient named by the source document."""

    issuer: str | None = None
    recipient: str | None = None


@dataclass(frozen=True, slots=True)
class Charge:
    """One charge line extracted from a source document."""

    raw_name: str | None
    canonical_name: str | None
    amount: Decimal | None
    currency: str | None
    payment_term: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    confidence: float = 1.0
    explicit_changes: frozenset[str] = field(default_factory=frozenset)
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)
    change_evidence: tuple[ExplicitChangeEvidence, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class BillingDocument:
    """A source document containing one or more charge lines."""

    document_info: DocumentInfo
    parties: TransactionParties
    charges: tuple[Charge, ...]
    charge_direction: ChargeDirection | None = None
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    raw_text: str = ""
    reasoning: tuple[str, ...] = field(default_factory=tuple)
    source_materials: tuple[SourceMaterial, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Bill:
    """An existing charge-level bill used for matching and updates."""

    bill_id: str | None
    document_info: DocumentInfo
    parties: TransactionParties
    charge: Charge
    accounting_entity: str | None = None
    posting_type: PostingType | None = None


@dataclass(frozen=True, slots=True)
class BillingDecision:
    """Final domain decision for a single charge line."""

    operation: Operation
    document_info: DocumentInfo
    parties: TransactionParties
    charge: Charge
    accounting_entity: str | None
    posting_type: PostingType | None
    matched_bill_id: str | None
    candidate_bill_id: str | None
    reasons: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)
