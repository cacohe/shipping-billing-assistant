"""Enumerations that form part of the billing output contract."""

from enum import StrEnum


class Operation(StrEnum):
    """Operation proposed for a charge record."""

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    NO_CHANGE = "NO_CHANGE"
    PENDING_REVIEW = "PENDING_REVIEW"


class PostingType(StrEnum):
    """Posting type from the accounting entity's perspective."""

    AR = "AR"
    AP = "AP"


class ChargeDirection(StrEnum):
    """The party charging the other party."""

    ISSUER_CHARGES_RECIPIENT = "ISSUER_CHARGES_RECIPIENT"
    RECIPIENT_CHARGES_ISSUER = "RECIPIENT_CHARGES_ISSUER"


class IssueSeverity(StrEnum):
    """Severity used by deterministic validation."""

    ERROR = "ERROR"
    WARNING = "WARNING"
