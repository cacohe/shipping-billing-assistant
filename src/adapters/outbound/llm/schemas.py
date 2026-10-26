"""Structured LLM response schemas."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ExtractedEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    source_text: str = Field(min_length=1)
    page: int | None = None
    sheet: str | None = None
    row: int | None = None
    attachment_name: str | None = None


class ExtractedChangeEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_name: str = Field(min_length=1)
    new_value: str = Field(min_length=1)
    evidence: ExtractedEvidence


class ExtractedDocumentInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: str | None = None
    reference_no: str | None = None
    document_date: date | None = None
    bill_of_lading_no: str | None = None
    booking_no: str | None = None
    container_no: str | None = None


class ExtractedParties(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issuer: str | None = None
    recipient: str | None = None


class ExtractedCharge(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    raw_name: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    payment_term: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    confidence: float = Field(ge=0, le=1)
    explicit_changes: list[str] = Field(default_factory=list)
    evidence: list[ExtractedEvidence] = Field(min_length=1)
    change_evidence: list[ExtractedChangeEvidence] = Field(default_factory=list)


class ExtractedBillingDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_info: ExtractedDocumentInfo
    parties: ExtractedParties
    charges: list[ExtractedCharge]
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    charge_direction: Literal["ISSUER_CHARGES_RECIPIENT", "RECIPIENT_CHARGES_ISSUER"] | None = None
    reasoning: list[str] = Field(default_factory=list)


class ExtractionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents: list[ExtractedBillingDocument]
