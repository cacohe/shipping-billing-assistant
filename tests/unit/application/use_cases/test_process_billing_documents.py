import logging
from decimal import Decimal

import pytest

from application.dto.documents import InputFile, ParsedDocument
from application.dto.requests import ProcessingRequest, ProcessingStage
from application.use_cases.process_billing_documents import ProcessBillingDocuments
from domain.billing.entities import (
    Bill,
    BillingDocument,
    Charge,
    DocumentInfo,
    Evidence,
    ExplicitChangeEvidence,
    TransactionParties,
)
from domain.billing.enums import ChargeDirection


class Parser:
    def parse_all(self, files: tuple[InputFile, ...]) -> tuple[ParsedDocument, ...]:
        return (ParsedDocument(files[0].name, "TEST", raw_text="invoice"),)


class Extractor:
    def extract(self, documents: tuple[ParsedDocument, ...]) -> tuple[BillingDocument, ...]:
        return (
            BillingDocument(
                DocumentInfo(reference_no="1"),
                TransactionParties("A", "B"),
                (
                    Charge(
                        "freight",
                        None,
                        Decimal("10"),
                        "usd",
                        evidence=(Evidence("a.txt", "freight USD 10"),),
                    ),
                ),
                ChargeDirection.ISSUER_CHARGES_RECIPIENT,
                raw_text="freight USD 10",
            ),
        )


class EmptyExtractor:
    def extract(self, documents: tuple[ParsedDocument, ...]) -> tuple[BillingDocument, ...]:
        return ()


class UpdateExtractor:
    def __init__(self, amount: Decimal, evidence_value: str) -> None:
        self._amount = amount
        self._evidence_value = evidence_value

    def extract(self, documents: tuple[ParsedDocument, ...]) -> tuple[BillingDocument, ...]:
        change_text = f"Change amount to {self._evidence_value}"
        return (
            BillingDocument(
                DocumentInfo(reference_no="INV-1"),
                TransactionParties("A", "B"),
                (
                    Charge(
                        "freight",
                        None,
                        self._amount,
                        "usd",
                        explicit_changes=frozenset({"amount"}),
                        evidence=(Evidence("a.txt", f"freight USD {self._amount}"),),
                        change_evidence=(
                            ExplicitChangeEvidence(
                                "amount", self._evidence_value, Evidence("a.txt", change_text)
                            ),
                        ),
                    ),
                ),
                ChargeDirection.ISSUER_CHARGES_RECIPIENT,
                raw_text=f"freight USD {self._amount}\n{change_text}",
            ),
        )


def test_complete_flow_emits_stages_and_output() -> None:
    stages: list[ProcessingStage] = []
    result = ProcessBillingDocuments(Parser(), Extractor()).process(
        ProcessingRequest((InputFile("a.txt", b"x"),), accounting_entity="A"),
        lambda event: stages.append(event.stage),
    )
    assert result[0].operation == "CREATE"
    assert result[0].charge_details.charge_item == "freight"
    assert result[0].model_dump(mode="json").keys() == {
        "operation",
        "document_info",
        "transaction_party",
        "charge_details",
        "financial_attributes",
        "audit_trail",
    }
    assert result[0].charge_details.model_dump().keys() == {
        "charge_item",
        "amount",
        "currency",
        "payment_term",
    }
    assert result[0].audit_trail.model_dump().keys() == {"ai_reasoning"}
    assert stages[0] == ProcessingStage.RECEIVED
    assert stages[-1] == ProcessingStage.COMPLETED


def test_empty_request_is_rejected() -> None:
    try:
        ProcessBillingDocuments(Parser(), Extractor()).process(ProcessingRequest(()))
    except ValueError as exc:
        assert "至少" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_empty_extraction_is_rejected() -> None:
    try:
        ProcessBillingDocuments(Parser(), EmptyExtractor()).process(
            ProcessingRequest((InputFile("a.txt", b"x"),))
        )
    except ValueError as exc:
        assert "费用项目" in str(exc)
    else:
        raise AssertionError("expected ValueError")


@pytest.mark.parametrize(
    ("amount", "evidence_value", "expected_operation"),
    [
        (Decimal("12"), "12", "UPDATE"),
        (Decimal("12"), "999", "PENDING_REVIEW"),
        (Decimal("10"), "10", "NO_CHANGE"),
    ],
)
def test_change_evidence_controls_update_through_complete_flow(
    amount: Decimal, evidence_value: str, expected_operation: str
) -> None:
    existing_charge = Charge("freight", "freight", Decimal("10"), "USD")
    existing = Bill(
        "B-1",
        DocumentInfo(reference_no="INV-1"),
        TransactionParties("A", "B"),
        existing_charge,
    )

    result = ProcessBillingDocuments(Parser(), UpdateExtractor(amount, evidence_value)).process(
        ProcessingRequest(
            (InputFile("a.txt", b"x"),),
            existing_bills=(existing,),
            accounting_entity="A",
        )
    )

    assert result[0].operation == expected_operation


def test_pending_review_audits_and_logs_unique_candidate(
    caplog: pytest.LogCaptureFixture,
) -> None:
    existing = Bill(
        "B-1",
        DocumentInfo(reference_no="INV-1"),
        TransactionParties("A", "B"),
        Charge("freight", "freight", Decimal("10"), "USD"),
    )
    application_logger = logging.getLogger("shipping_billing_assistant.application")
    previous_level = application_logger.level
    application_logger.addHandler(caplog.handler)
    application_logger.setLevel(logging.INFO)
    try:
        result = ProcessBillingDocuments(Parser(), UpdateExtractor(Decimal("12"), "999")).process(
            ProcessingRequest(
                (InputFile("a.txt", b"x"),),
                existing_bills=(existing,),
                accounting_entity="A",
            )
        )
    finally:
        application_logger.removeHandler(caplog.handler)
        application_logger.setLevel(previous_level)

    assert result[0].operation == "PENDING_REVIEW"
    assert result[0].model_dump(mode="json").keys() == {
        "operation",
        "document_info",
        "transaction_party",
        "charge_details",
        "financial_attributes",
        "audit_trail",
    }
    assert any("候选账单 B-1" in reason for reason in result[0].audit_trail.ai_reasoning)
    assert any(
        "candidate_bill_id=B-1" in record.getMessage()
        and "match_rule=reference_no_and_charge" in record.getMessage()
        for record in caplog.records
    )
