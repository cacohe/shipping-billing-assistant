from datetime import date
from decimal import Decimal

from domain.billing.decision import decide_charge, determine_posting_type
from domain.billing.entities import (
    Bill,
    BillingDocument,
    Charge,
    DocumentInfo,
    Evidence,
    ExplicitChangeEvidence,
    SourceMaterial,
    TransactionParties,
)
from domain.billing.enums import ChargeDirection, IssueSeverity, Operation, PostingType
from domain.billing.matching import MatchResult, match_existing_bill
from domain.billing.normalization import (
    normalize_charge,
    normalize_currency,
    normalize_payment_term,
)
from domain.billing.validation import ValidationIssue, validate_document


def charge(**changes: object) -> Charge:
    values = {
        "raw_name": "Ocean Freight",
        "canonical_name": None,
        "amount": Decimal("100"),
        "currency": "usd",
        "evidence": (Evidence("invoice.pdf", "Ocean Freight USD 100", source_id="0"),),
    }
    values.update(changes)
    return Charge(**values)  # type: ignore[arg-type]


def document(item: Charge | None = None) -> BillingDocument:
    return BillingDocument(
        DocumentInfo(reference_no="INV-1", document_date=date(2026, 1, 2)),
        TransactionParties("Carrier", "Importer"),
        (item or normalize_charge(charge()),),
        ChargeDirection.ISSUER_CHARGES_RECIPIENT,
        raw_text="Ocean Freight USD 100",
        source_materials=(SourceMaterial("0", "invoice.pdf", "Ocean Freight USD 100"),),
    )


def test_normalization_and_validation() -> None:
    item = normalize_charge(charge())
    assert item.canonical_name == "Ocean Freight"
    assert item.currency == "USD"
    assert validate_document(document(item)) == []
    low = normalize_charge(charge(confidence=0.2))
    assert validate_document(document(low))[0].code == "low_confidence"
    assert normalize_payment_term("预付") == "PP"
    assert normalize_payment_term("到付") == "CC"
    assert normalize_payment_term("P") == "PP"
    assert normalize_payment_term("C") == "CC"
    assert normalize_currency("RMB") == "CNY"
    assert normalize_currency("人民币") == "CNY"


def test_document_totals_are_validated_against_charge_lines() -> None:
    doc = BillingDocument(
        DocumentInfo(reference_no="INV-2"),
        TransactionParties("Carrier", "Importer"),
        (normalize_charge(charge(amount=Decimal("100"))),),
        ChargeDirection.ISSUER_CHARGES_RECIPIENT,
        subtotal=Decimal("90"),
        tax=Decimal("5"),
        total=Decimal("100"),
        raw_text="Ocean Freight USD 100",
    )
    assert {issue.code for issue in validate_document(doc)} == {
        "detail_subtotal_mismatch",
        "total_mismatch",
    }


def test_only_duplicate_lines_at_same_source_location_are_blocking() -> None:
    first = normalize_charge(
        charge(evidence=(Evidence("invoice.pdf", "Ocean Freight USD 100", row=1, source_id="0"),))
    )
    second = normalize_charge(
        charge(evidence=(Evidence("invoice.pdf", "Ocean Freight USD 100", row=2, source_id="0"),))
    )
    doc = BillingDocument(
        DocumentInfo(reference_no="INV-3"),
        TransactionParties("Carrier", "Importer"),
        (first, second),
        ChargeDirection.ISSUER_CHARGES_RECIPIENT,
        raw_text="Ocean Freight USD 100\nOcean Freight USD 100",
        source_materials=(
            SourceMaterial("0", "invoice.pdf", "Ocean Freight USD 100\nOcean Freight USD 100"),
        ),
    )
    issues = validate_document(doc)
    assert not any(issue.code == "duplicate_charge" for issue in issues)

    duplicated = BillingDocument(
        doc.document_info,
        doc.parties,
        (first, first),
        doc.charge_direction,
        raw_text=doc.raw_text,
        source_materials=doc.source_materials,
    )
    duplicate_indexes = {
        issue.charge_index
        for issue in validate_document(duplicated)
        if issue.code == "duplicate_charge"
    }
    assert duplicate_indexes == {0, 1}


def test_ocr_confusion_only_blocks_the_affected_charge() -> None:
    affected = normalize_charge(
        charge(evidence=(Evidence("invoice.pdf", "Ocean Freight USD 1O0", source_id="0"),))
    )
    clean = normalize_charge(
        charge(
            raw_name="Documentation Fee",
            amount=Decimal("20"),
            evidence=(Evidence("invoice.pdf", "Documentation Fee USD 20", source_id="0"),),
        )
    )
    doc = BillingDocument(
        DocumentInfo(reference_no="INV-3"),
        TransactionParties("Carrier", "Importer"),
        (affected, clean),
        ChargeDirection.ISSUER_CHARGES_RECIPIENT,
        raw_text="Ocean Freight USD 1O0\nDocumentation Fee USD 20",
        source_materials=(
            SourceMaterial("0", "invoice.pdf", "Ocean Freight USD 1O0\nDocumentation Fee USD 20"),
        ),
    )

    issues = validate_document(doc)

    assert {
        issue.charge_index
        for issue in issues
        if issue.code == "possible_ocr_confusion" and issue.severity.value == "ERROR"
    } == {0}


def test_non_finite_amount_is_invalid() -> None:
    issues = validate_document(document(normalize_charge(charge(amount=Decimal("NaN")))))
    assert any(issue.code == "invalid_amount" for issue in issues)


def test_evidence_must_be_grounded_in_source_text() -> None:
    doc = document(
        normalize_charge(
            charge(evidence=(Evidence("invoice.pdf", "Invented surcharge USD 100", source_id="0"),))
        )
    )

    issues = validate_document(doc)

    assert any(issue.code == "ungrounded_evidence" for issue in issues)


def test_evidence_must_be_grounded_in_the_named_source() -> None:
    item = normalize_charge(
        charge(evidence=(Evidence("other.pdf", "Ocean Freight USD 100", source_id="1"),))
    )
    doc = BillingDocument(
        DocumentInfo(reference_no="INV-1"),
        TransactionParties("Carrier", "Importer"),
        (item,),
        ChargeDirection.ISSUER_CHARGES_RECIPIENT,
        raw_text="Ocean Freight USD 100",
        source_materials=(
            SourceMaterial("0", "invoice.pdf", "Ocean Freight USD 100"),
            SourceMaterial("1", "other.pdf", "Documentation Fee USD 20"),
        ),
    )

    assert any(issue.code == "ungrounded_evidence" for issue in validate_document(doc))


def test_explicit_changes_require_supported_field_and_grounded_change_evidence() -> None:
    unsupported = normalize_charge(charge(explicit_changes=frozenset({"unsupported_field"})))
    assert any(
        issue.code == "unsupported_explicit_change"
        for issue in validate_document(document(unsupported))
    )

    missing_proof = normalize_charge(charge(explicit_changes=frozenset({"amount"})))
    assert any(
        issue.code == "unsubstantiated_explicit_change"
        for issue in validate_document(document(missing_proof))
    )

    proven = normalize_charge(
        charge(
            amount=Decimal("120"),
            explicit_changes=frozenset({"amount"}),
            evidence=(Evidence("invoice.pdf", "Ocean Freight USD 120", source_id="0"),),
            change_evidence=(
                ExplicitChangeEvidence(
                    "amount",
                    "120",
                    Evidence(
                        "invoice.pdf",
                        "Please change amount to USD 120",
                        source_id="0",
                    ),
                ),
            ),
        )
    )
    proven_document = BillingDocument(
        DocumentInfo(reference_no="INV-1"),
        TransactionParties("Carrier", "Importer"),
        (proven,),
        ChargeDirection.ISSUER_CHARGES_RECIPIENT,
        raw_text="Ocean Freight USD 120\nPlease change amount to USD 120",
        source_materials=(
            SourceMaterial(
                "0", "invoice.pdf", "Ocean Freight USD 120\nPlease change amount to USD 120"
            ),
        ),
    )
    assert not {
        issue.code
        for issue in validate_document(proven_document)
        if "explicit_change" in issue.code
        or issue.code
        in {"ungrounded_change_evidence", "change_value_mismatch", "missing_change_value"}
    }


def test_change_evidence_value_must_match_candidate_value() -> None:
    mismatched = normalize_charge(
        charge(
            amount=Decimal("120"),
            explicit_changes=frozenset({"amount"}),
            change_evidence=(
                ExplicitChangeEvidence(
                    "amount",
                    "999",
                    Evidence(
                        "invoice.pdf",
                        "Please change amount to USD 999",
                        source_id="0",
                    ),
                ),
            ),
        )
    )
    doc = BillingDocument(
        DocumentInfo(reference_no="INV-1"),
        TransactionParties("Carrier", "Importer"),
        (mismatched,),
        raw_text="Ocean Freight USD 100\nPlease change amount to USD 999",
        source_materials=(
            SourceMaterial(
                "0", "invoice.pdf", "Ocean Freight USD 100\nPlease change amount to USD 999"
            ),
        ),
    )

    assert any(issue.code == "change_value_mismatch" for issue in validate_document(doc))

    missing_value = normalize_charge(
        charge(
            amount=None,
            explicit_changes=frozenset({"amount"}),
            change_evidence=(
                ExplicitChangeEvidence(
                    "amount",
                    "120",
                    Evidence("invoice.pdf", "Change amount to 120", source_id="0"),
                ),
            ),
        )
    )
    missing_doc = BillingDocument(
        doc.document_info,
        doc.parties,
        (missing_value,),
        raw_text="Change amount to 120",
        source_materials=(SourceMaterial("0", "invoice.pdf", "Change amount to 120"),),
    )
    assert any(issue.code == "missing_change_value" for issue in validate_document(missing_doc))

    substring_only = normalize_charge(
        charge(
            amount=Decimal("12"),
            explicit_changes=frozenset({"amount"}),
            change_evidence=(
                ExplicitChangeEvidence(
                    "amount",
                    "12",
                    Evidence("invoice.pdf", "Change amount to 123", source_id="0"),
                ),
            ),
        )
    )
    substring_doc = BillingDocument(
        doc.document_info,
        doc.parties,
        (substring_only,),
        raw_text="Ocean Freight USD 100\nChange amount to 123",
        source_materials=(
            SourceMaterial("0", "invoice.pdf", "Ocean Freight USD 100\nChange amount to 123"),
        ),
    )
    assert any(issue.code == "change_value_mismatch" for issue in validate_document(substring_doc))


def test_ambiguous_date_change_token_requires_review() -> None:
    item = normalize_charge(
        charge(
            explicit_changes=frozenset({"document_info.document_date"}),
            change_evidence=(
                ExplicitChangeEvidence(
                    "document_info.document_date",
                    "01/02/2026",
                    Evidence("invoice.pdf", "Change date to 01/02/2026", source_id="0"),
                ),
            ),
        )
    )
    doc = BillingDocument(
        DocumentInfo(reference_no="INV-1", document_date=date(2026, 1, 2)),
        TransactionParties("Carrier", "Importer"),
        (item,),
        raw_text="Ocean Freight USD 100\nChange date to 01/02/2026",
        source_materials=(
            SourceMaterial("0", "invoice.pdf", "Ocean Freight USD 100\nChange date to 01/02/2026"),
        ),
    )

    assert any(issue.code == "change_value_mismatch" for issue in validate_document(doc))


def test_conflicting_change_evidence_requires_review() -> None:
    item = normalize_charge(
        charge(
            amount=Decimal("120"),
            explicit_changes=frozenset({"amount"}),
            change_evidence=(
                ExplicitChangeEvidence(
                    "amount",
                    "120",
                    Evidence("invoice.pdf", "Change amount to 120", source_id="0"),
                ),
                ExplicitChangeEvidence(
                    "amount",
                    "999",
                    Evidence("invoice.pdf", "Correction: amount is 999", source_id="0"),
                ),
            ),
        )
    )
    source_text = "Ocean Freight USD 100\nChange amount to 120\nCorrection: amount is 999"
    doc = BillingDocument(
        DocumentInfo(reference_no="INV-1"),
        TransactionParties("Carrier", "Importer"),
        (item,),
        raw_text=source_text,
        source_materials=(SourceMaterial("0", "invoice.pdf", source_text),),
    )

    assert any(issue.code == "change_value_mismatch" for issue in validate_document(doc))


def test_duplicate_source_names_are_disambiguated_by_source_id() -> None:
    item = normalize_charge(
        charge(evidence=(Evidence("invoice.pdf", "Documentation Fee USD 20", source_id="0"),))
    )
    doc = BillingDocument(
        DocumentInfo(reference_no="INV-1"),
        TransactionParties("Carrier", "Importer"),
        (item,),
        raw_text="Ocean Freight USD 100\nDocumentation Fee USD 20",
        source_materials=(
            SourceMaterial("0", "invoice.pdf", "Ocean Freight USD 100"),
            SourceMaterial("1", "invoice.pdf", "Documentation Fee USD 20"),
        ),
    )

    assert any(issue.code == "ungrounded_evidence" for issue in validate_document(doc))


def test_evidence_grounding_ignores_case_and_whitespace() -> None:
    doc = document(
        normalize_charge(
            charge(evidence=(Evidence("invoice.pdf", "ocean   freight\nUSD 100", source_id="0"),))
        )
    )

    assert validate_document(doc) == []


def test_matching_and_update_only_explicit_fields() -> None:
    existing = Bill(
        "B-1",
        DocumentInfo(
            document_type="Invoice",
            reference_no="INV-1",
            document_date=date(2025, 12, 31),
        ),
        TransactionParties("Carrier", "Original Importer"),
        normalize_charge(charge()),
        posting_type=PostingType.AP,
    )
    extracted = normalize_charge(
        charge(amount=Decimal("120"), explicit_changes=frozenset({"amount"}))
    )
    doc = document(extracted)
    matched = match_existing_bill(doc, extracted, (existing,))
    assert matched.unique_match == existing
    result = decide_charge(
        document=doc,
        charge=extracted,
        match=matched,
        validation_issues=(),
        accounting_entity="Original Importer",
    )
    assert result.operation == Operation.UPDATE
    assert result.charge.amount == Decimal("120")
    assert result.posting_type == PostingType.AP
    assert result.document_info.document_date == date(2025, 12, 31)
    assert result.parties.recipient == "Original Importer"


def test_validation_failure_preserves_unique_match_as_candidate() -> None:
    existing = Bill(
        "B-1",
        DocumentInfo(reference_no="INV-1"),
        TransactionParties("Carrier", "Importer"),
        normalize_charge(charge()),
    )
    extracted = normalize_charge(charge())
    doc = document(extracted)

    result = decide_charge(
        document=doc,
        charge=extracted,
        match=match_existing_bill(doc, extracted, (existing,)),
        validation_issues=(
            ValidationIssue("invalid_evidence", "来源证据无效", IssueSeverity.ERROR, 0),
        ),
        accounting_entity="Carrier",
    )

    assert result.operation == Operation.PENDING_REVIEW
    assert result.matched_bill_id is None
    assert result.candidate_bill_id == "B-1"
    assert any(
        "候选账单 B-1" in reason and "reference_no_and_charge" in reason
        for reason in result.reasons
    )


def test_validation_failure_does_not_promote_ambiguous_matches_to_candidate() -> None:
    extracted = normalize_charge(charge())
    doc = document(extracted)
    candidates = tuple(
        Bill(
            bill_id,
            DocumentInfo(reference_no="INV-1"),
            TransactionParties("Carrier", "Importer"),
            normalize_charge(charge()),
        )
        for bill_id in ("B-1", "B-2")
    )

    result = decide_charge(
        document=doc,
        charge=extracted,
        match=MatchResult(candidates, "reference_no_and_charge"),
        validation_issues=(
            ValidationIssue("invalid_evidence", "来源证据无效", IssueSeverity.ERROR, 0),
        ),
        accounting_entity="Carrier",
    )

    assert result.operation == Operation.PENDING_REVIEW
    assert result.matched_bill_id is None
    assert result.candidate_bill_id is None


def test_create_and_pending_review() -> None:
    doc = document()
    result = decide_charge(
        document=doc,
        charge=doc.charges[0],
        match=MatchResult((), None),
        validation_issues=(),
        accounting_entity="Carrier",
    )
    assert result.operation == Operation.CREATE
    assert determine_posting_type("Carrier", doc) == PostingType.AR
    pending = decide_charge(
        document=doc,
        charge=doc.charges[0],
        match=MatchResult((), None),
        validation_issues=(),
        accounting_entity=None,
    )
    assert pending.operation == Operation.PENDING_REVIEW


def test_posting_type_treats_parenthesized_office_as_same_legal_party() -> None:
    doc = BillingDocument(
        DocumentInfo(reference_no="DN-1"),
        TransactionParties("NORTHSTAR LOGISTICS DEMO LTD (LAX)", None),
        (normalize_charge(charge()),),
        ChargeDirection.ISSUER_CHARGES_RECIPIENT,
        raw_text="Ocean Freight USD 100",
    )

    assert determine_posting_type("NORTHSTAR LOGISTICS DEMO LTD", doc) == PostingType.AR


def test_posting_type_does_not_strip_descriptive_parenthetical_identity() -> None:
    doc = BillingDocument(
        DocumentInfo(reference_no="DN-2"),
        TransactionParties("NORTHSTAR LOGISTICS DEMO LTD (HOLDINGS)", None),
        (normalize_charge(charge()),),
        ChargeDirection.ISSUER_CHARGES_RECIPIENT,
        raw_text="Ocean Freight USD 100",
    )

    assert determine_posting_type("NORTHSTAR LOGISTICS DEMO LTD", doc) is None


def test_matching_uses_the_same_office_normalization_as_posting_type() -> None:
    item = normalize_charge(charge())
    doc = BillingDocument(
        DocumentInfo(container_no="DEMU1234567", document_date=date(2026, 10, 30)),
        TransactionParties("NORTHSTAR LOGISTICS DEMO LTD (LAX)", "IMPORTER (NYC)"),
        (item,),
    )
    existing = Bill(
        "B-2",
        DocumentInfo(container_no="DEMU1234567", document_date=date(2026, 10, 30)),
        TransactionParties("NORTHSTAR LOGISTICS DEMO LTD", "IMPORTER"),
        item,
    )

    assert match_existing_bill(doc, item, (existing,)).unique_match == existing
