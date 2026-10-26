"""Input JSON schema and mapping for existing bills."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from domain.billing.entities import Bill, Charge, DocumentInfo, TransactionParties
from domain.billing.enums import PostingType
from domain.billing.normalization import normalize_charge


class ExistingDocumentInfoInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    document_type: str | None = None
    reference_no: str | None = None
    document_date: date | None = None
    bill_of_lading_no: str | None = None
    booking_no: str | None = None
    container_no: str | None = None


class ExistingTransactionPartyInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    issuer: str | None = None
    recipient: str | None = None


class ExistingChargeInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True, allow_inf_nan=False)

    raw_charge_item: str | None = None
    charge_item: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    payment_term: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None


class ExistingFinancialAttributesInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    accounting_entity: str | None = None
    posting_type: Literal["AR", "AP"] | None = None


class ExistingBillInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bill_id: str | None = None
    document_info: ExistingDocumentInfoInput
    transaction_party: ExistingTransactionPartyInput
    charge_details: ExistingChargeInput
    financial_attributes: ExistingFinancialAttributesInput | None = None

    def to_domain(self) -> Bill:
        charge = normalize_charge(
            Charge(
                raw_name=self.charge_details.raw_charge_item or self.charge_details.charge_item,
                canonical_name=self.charge_details.charge_item,
                amount=self.charge_details.amount,
                currency=self.charge_details.currency,
                payment_term=self.charge_details.payment_term,
                quantity=self.charge_details.quantity,
                unit_price=self.charge_details.unit_price,
            )
        )
        financial = self.financial_attributes
        return Bill(
            bill_id=self.bill_id,
            document_info=DocumentInfo(**self.document_info.model_dump()),
            parties=TransactionParties(**self.transaction_party.model_dump()),
            charge=charge,
            accounting_entity=financial.accounting_entity if financial else None,
            posting_type=(
                PostingType(financial.posting_type)
                if financial and financial.posting_type
                else None
            ),
        )
