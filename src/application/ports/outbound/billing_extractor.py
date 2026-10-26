"""Port for semantic extraction from parsed documents."""

from typing import Protocol

from application.dto.documents import ParsedDocument
from domain.billing.entities import BillingDocument


class BillingExtractorPort(Protocol):
    def extract(self, documents: tuple[ParsedDocument, ...]) -> tuple[BillingDocument, ...]: ...
