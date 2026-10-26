"""Operation selection, update merging, and AR/AP determination."""

from dataclasses import fields, replace

from domain.billing.entities import (
    Bill,
    BillingDecision,
    BillingDocument,
    Charge,
    DocumentInfo,
    TransactionParties,
)
from domain.billing.enums import ChargeDirection, IssueSeverity, Operation, PostingType
from domain.billing.matching import MatchResult
from domain.billing.normalization import normalize_party_identity
from domain.billing.validation import ValidationIssue

_CHANGEABLE_FIELDS = {
    "canonical_name",
    "amount",
    "currency",
    "payment_term",
    "quantity",
    "unit_price",
}

_DOCUMENT_CHANGE_PATHS = {
    "document_info.document_type": "document_type",
    "document_info.reference_no": "reference_no",
    "document_info.document_date": "document_date",
    "document_info.bill_of_lading_no": "bill_of_lading_no",
    "document_info.booking_no": "booking_no",
    "document_info.container_no": "container_no",
}

_PARTY_CHANGE_PATHS = {
    "transaction_party.issuer": "issuer",
    "transaction_party.recipient": "recipient",
}


def determine_posting_type(
    accounting_entity: str | None,
    document: BillingDocument,
) -> PostingType | None:
    """Determine AR/AP from party role and explicit charge direction."""

    if not accounting_entity or document.charge_direction is None:
        return None
    entity = normalize_party_identity(accounting_entity)
    issuer = normalize_party_identity(document.parties.issuer)
    recipient = normalize_party_identity(document.parties.recipient)

    if document.charge_direction == ChargeDirection.ISSUER_CHARGES_RECIPIENT:
        if entity == issuer:
            return PostingType.AR
        if entity == recipient:
            return PostingType.AP
    if document.charge_direction == ChargeDirection.RECIPIENT_CHARGES_ISSUER:
        if entity == recipient:
            return PostingType.AR
        if entity == issuer:
            return PostingType.AP
    return None


def _merge_explicit_changes(extracted: Charge, existing: Charge) -> tuple[Charge, bool]:
    values = {field.name: getattr(existing, field.name) for field in fields(Charge)}
    values["raw_name"] = extracted.raw_name or existing.raw_name
    values["canonical_name"] = existing.canonical_name
    values["confidence"] = extracted.confidence
    values["explicit_changes"] = extracted.explicit_changes
    values["evidence"] = extracted.evidence
    values["change_evidence"] = extracted.change_evidence

    changed = False
    for field_name in extracted.explicit_changes & _CHANGEABLE_FIELDS:
        new_value = getattr(extracted, field_name)
        if new_value is not None:
            changed = changed or new_value != getattr(existing, field_name)
            values[field_name] = new_value
    return Charge(**values), changed


def _merge_document_context(
    document: BillingDocument,
    existing: Bill,
    explicit_changes: frozenset[str],
) -> tuple[DocumentInfo, TransactionParties, bool]:
    info_values = {
        field.name: getattr(existing.document_info, field.name) for field in fields(DocumentInfo)
    }
    party_values = {
        field.name: getattr(existing.parties, field.name) for field in fields(TransactionParties)
    }
    changed = False
    for path, field_name in _DOCUMENT_CHANGE_PATHS.items():
        if path in explicit_changes:
            value = getattr(document.document_info, field_name)
            if value is not None:
                changed = changed or value != info_values[field_name]
                info_values[field_name] = value
    for path, field_name in _PARTY_CHANGE_PATHS.items():
        if path in explicit_changes:
            value = getattr(document.parties, field_name)
            if value is not None:
                changed = changed or value != party_values[field_name]
                party_values[field_name] = value
    return DocumentInfo(**info_values), TransactionParties(**party_values), changed


def decide_charge(
    *,
    document: BillingDocument,
    charge: Charge,
    match: MatchResult,
    validation_issues: tuple[ValidationIssue, ...],
    accounting_entity: str | None,
) -> BillingDecision:
    """Produce the final charge-level decision required by the JSON contract."""

    errors = tuple(
        issue.message for issue in validation_issues if issue.severity == IssueSeverity.ERROR
    )
    warnings = tuple(
        issue.message for issue in validation_issues if issue.severity == IssueSeverity.WARNING
    )
    reasons = list(document.reasoning)
    effective_info = document.document_info
    effective_parties = document.parties
    effective_charge = charge
    changed = False
    if match.unique_match is not None:
        effective_charge, charge_changed = _merge_explicit_changes(
            charge, match.unique_match.charge
        )
        effective_info, effective_parties, context_changed = _merge_document_context(
            document, match.unique_match, charge.explicit_changes
        )
        changed = charge_changed or context_changed
    effective_document = replace(
        document,
        document_info=effective_info,
        parties=effective_parties,
        charges=(effective_charge,),
    )
    posting_type = determine_posting_type(accounting_entity, effective_document)

    if errors:
        candidate_bill_id = match.unique_match.bill_id if match.unique_match else None
        if match.unique_match is not None:
            candidate_label = candidate_bill_id or "<未提供账单号>"
            reasons.append(
                f"通过 {match.rule} 找到唯一候选账单 {candidate_label}，但校验失败，未确认更新目标"
            )
        reasons.extend(errors)
        return BillingDecision(
            Operation.PENDING_REVIEW,
            effective_info,
            effective_parties,
            effective_charge,
            accounting_entity,
            posting_type,
            None,
            candidate_bill_id,
            tuple(reasons),
            warnings,
        )
    if match.ambiguous:
        reasons.append("多个已有账单满足同一匹配规则，无法唯一确定更新目标")
        return BillingDecision(
            Operation.PENDING_REVIEW,
            effective_info,
            effective_parties,
            effective_charge,
            accounting_entity,
            posting_type,
            None,
            None,
            tuple(reasons),
            warnings,
        )
    if posting_type is None:
        reasons.append("缺少记账主体、交易方向或可识别的交易方，无法可靠判断 AR/AP")
        return BillingDecision(
            Operation.PENDING_REVIEW,
            effective_info,
            effective_parties,
            effective_charge,
            accounting_entity,
            None,
            match.unique_match.bill_id if match.unique_match else None,
            None,
            tuple(reasons),
            warnings,
        )
    if match.unique_match is None:
        reasons.append("未匹配到已有账单，创建新的费用记录")
        return BillingDecision(
            Operation.CREATE,
            document.document_info,
            document.parties,
            charge,
            accounting_entity,
            posting_type,
            None,
            None,
            tuple(reasons),
            warnings,
        )

    existing: Bill = match.unique_match
    reasons.append(f"通过 {match.rule} 匹配到已有账单")
    if changed:
        reasons.append("仅更新输入材料明确变更的字段，其他字段继承原账单")
        operation = Operation.UPDATE
    else:
        reasons.append("输入材料未产生明确字段变化")
        operation = Operation.NO_CHANGE
    return BillingDecision(
        operation,
        effective_info,
        effective_parties,
        effective_charge,
        accounting_entity,
        posting_type,
        existing.bill_id,
        None,
        tuple(reasons),
        warnings,
    )
