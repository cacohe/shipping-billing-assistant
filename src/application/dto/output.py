"""Validated JSON output models."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from domain.billing.entities import BillingDecision


class DocumentInfoOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: str | None
    reference_no: str | None
    document_date: date | None


class TransactionPartyOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issuer: str | None
    recipient: str | None


class ChargeDetailsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    charge_item: str | None
    amount: float | None
    currency: str | None
    payment_term: str | None


class FinancialAttributesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accounting_entity: str | None
    posting_type: Literal["AR", "AP"] | None


class AuditTrailOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_reasoning: list[str]


class BillingRecordOutput(BaseModel):
    """One output entry per charge item."""

    model_config = ConfigDict(extra="forbid")

    operation: Literal["CREATE", "UPDATE", "NO_CHANGE", "PENDING_REVIEW"]
    document_info: DocumentInfoOutput
    transaction_party: TransactionPartyOutput
    charge_details: ChargeDetailsOutput
    financial_attributes: FinancialAttributesOutput
    audit_trail: AuditTrailOutput

    @classmethod
    def from_decision(cls, decision: BillingDecision) -> "BillingRecordOutput":
        return cls(
            operation=decision.operation.value,
            document_info=DocumentInfoOutput(
                document_type=decision.document_info.document_type,
                reference_no=decision.document_info.reference_no,
                document_date=decision.document_info.document_date,
            ),
            transaction_party=TransactionPartyOutput(
                issuer=decision.parties.issuer,
                recipient=decision.parties.recipient,
            ),
            charge_details=ChargeDetailsOutput(
                charge_item=decision.charge.canonical_name,
                amount=float(decision.charge.amount)
                if decision.charge.amount is not None and decision.charge.amount.is_finite()
                else None,
                currency=decision.charge.currency,
                payment_term=decision.charge.payment_term,
            ),
            financial_attributes=FinancialAttributesOutput(
                accounting_entity=decision.accounting_entity,
                posting_type=(decision.posting_type.value if decision.posting_type else None),
            ),
            audit_trail=AuditTrailOutput(
                ai_reasoning=[
                    *decision.reasons,
                    *(
                        f"来源 {item.source_name}: {item.source_text}"
                        for item in decision.charge.evidence
                    ),
                    *(
                        "显式变更证据 "
                        f"{item.field_name}={item.new_value} @ {item.evidence.source_name}: "
                        f"{item.evidence.source_text}"
                        for item in decision.charge.change_evidence
                    ),
                    *decision.warnings,
                ],
            ),
        )


def records_to_json_data(records: tuple[BillingRecordOutput, ...]) -> list[dict[str, Any]]:
    """Return JSON-safe dictionaries while preserving numeric amounts."""

    return [record.model_dump(mode="json") for record in records]
