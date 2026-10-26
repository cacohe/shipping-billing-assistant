"""Deterministic validation for extracted charge data."""

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pycountry

from domain.billing.entities import BillingDocument, Charge, Evidence
from domain.billing.enums import IssueSeverity
from domain.billing.normalization import (
    normalize_charge_name,
    normalize_currency,
    normalize_payment_term,
)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A field-level validation finding."""

    code: str
    message: str
    severity: IssueSeverity
    charge_index: int | None = None


def _is_iso_currency(currency: str) -> bool:
    return pycountry.currencies.get(alpha_3=currency) is not None


def _comparable_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


_SUPPORTED_EXPLICIT_CHANGES = frozenset(
    {
        "canonical_name",
        "amount",
        "currency",
        "payment_term",
        "quantity",
        "unit_price",
        "document_info.document_type",
        "document_info.reference_no",
        "document_info.document_date",
        "document_info.bill_of_lading_no",
        "document_info.booking_no",
        "document_info.container_no",
        "transaction_party.issuer",
        "transaction_party.recipient",
    }
)

_OCR_CONFUSION = re.compile(r"(?<=\d)[OI](?=\d)|(?<=\d)[OI]\b|\b[OI](?=\d)")


def _is_grounded(evidence: Evidence, document: BillingDocument) -> bool:
    evidence_text = _comparable_text(evidence.source_text)
    if document.source_materials:
        source_name = _comparable_text(evidence.source_name)
        return any(
            evidence.source_id is not None
            and material.source_id == evidence.source_id
            and _comparable_text(material.source_name) == source_name
            and evidence_text in _comparable_text(material.text)
            for material in document.source_materials
        )
    return evidence_text in _comparable_text(document.raw_text)


def _evidence_identity(charge: Charge) -> tuple[object, ...]:
    return tuple(
        (
            item.source_id,
            _comparable_text(item.source_name),
            _comparable_text(item.source_text),
            item.page,
            item.sheet,
            item.row,
            item.attachment_name,
        )
        for item in charge.evidence
    )


def _has_precise_line_location(charge: Charge) -> bool:
    return bool(charge.evidence) and all(item.row is not None for item in charge.evidence)


def _candidate_change_value(
    field_name: str, document: BillingDocument, charge: Charge
) -> object | None:
    values: dict[str, object | None] = {
        "canonical_name": charge.canonical_name,
        "amount": charge.amount,
        "currency": charge.currency,
        "payment_term": charge.payment_term,
        "quantity": charge.quantity,
        "unit_price": charge.unit_price,
        "document_info.document_type": document.document_info.document_type,
        "document_info.reference_no": document.document_info.reference_no,
        "document_info.document_date": document.document_info.document_date,
        "document_info.bill_of_lading_no": document.document_info.bill_of_lading_no,
        "document_info.booking_no": document.document_info.booking_no,
        "document_info.container_no": document.document_info.container_no,
        "transaction_party.issuer": document.parties.issuer,
        "transaction_party.recipient": document.parties.recipient,
    }
    return values.get(field_name)


def _parse_date_token(value: str) -> tuple[date, ...]:
    parsed: list[date] = []
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            candidate = datetime.strptime(value.strip(), pattern).date()
        except ValueError:
            continue
        if candidate not in parsed:
            parsed.append(candidate)
    return tuple(parsed)


def _change_token_matches(field_name: str, token: str, candidate: object) -> bool:
    if isinstance(candidate, Decimal):
        try:
            return Decimal(token.replace(",", "").strip()) == candidate
        except InvalidOperation:
            return False
    if isinstance(candidate, date):
        parsed_dates = _parse_date_token(token)
        return len(parsed_dates) == 1 and parsed_dates[0] == candidate
    if field_name == "currency":
        return normalize_currency(token) == candidate
    if field_name == "payment_term":
        return normalize_payment_term(token) == candidate
    if field_name == "canonical_name":
        return normalize_charge_name(token) == candidate
    return _comparable_text(token) == _comparable_text(str(candidate))


def _change_evidence_matches_value(
    field_name: str, token: str, evidence: Evidence, candidate: object
) -> bool:
    normalized_token = _comparable_text(token)
    normalized_evidence = _comparable_text(evidence.source_text)
    contains_token = bool(
        normalized_token
        and re.search(rf"(?<!\w){re.escape(normalized_token)}(?!\w)", normalized_evidence)
    )
    return contains_token and _change_token_matches(field_name, token, candidate)


def validate_charge(charge: Charge, charge_index: int | None = None) -> list[ValidationIssue]:
    """Validate one charge without mutating it."""

    issues: list[ValidationIssue] = []
    if charge.amount is None:
        issues.append(
            ValidationIssue("missing_amount", "费用金额无法确定", IssueSeverity.ERROR, charge_index)
        )
    elif not charge.amount.is_finite():
        issues.append(
            ValidationIssue(
                "invalid_amount", "费用金额必须是有限数字", IssueSeverity.ERROR, charge_index
            )
        )
    if charge.currency is None:
        issues.append(
            ValidationIssue(
                "missing_currency", "费用币种无法确定", IssueSeverity.ERROR, charge_index
            )
        )
    elif not _is_iso_currency(charge.currency):
        issues.append(
            ValidationIssue(
                "invalid_currency",
                f"币种 {charge.currency!r} 不是有效的 ISO 4217 三位代码",
                IssueSeverity.ERROR,
                charge_index,
            )
        )
    if charge.canonical_name is None:
        issues.append(
            ValidationIssue(
                "missing_charge_name", "费用名称无法确定", IssueSeverity.ERROR, charge_index
            )
        )
    if not charge.evidence:
        issues.append(
            ValidationIssue(
                "missing_evidence",
                "费用项目缺少可核对的文件来源和原始文本",
                IssueSeverity.ERROR,
                charge_index,
            )
        )
    if not 0 <= charge.confidence <= 1:
        issues.append(
            ValidationIssue(
                "invalid_confidence",
                "置信度必须位于 0 到 1 之间",
                IssueSeverity.ERROR,
                charge_index,
            )
        )
    elif charge.confidence < 0.6:
        issues.append(
            ValidationIssue(
                "low_confidence",
                f"费用抽取置信度较低：{charge.confidence:.2f}",
                IssueSeverity.ERROR,
                charge_index,
            )
        )
    return issues


def validate_document(document: BillingDocument) -> list[ValidationIssue]:
    """Validate charges, duplicated lines, and likely OCR character confusion."""

    issues: list[ValidationIssue] = []
    semantic_signatures = tuple(
        (charge.canonical_name, charge.amount, charge.currency) for charge in document.charges
    )
    semantic_counts = Counter(semantic_signatures)
    exact_signatures = tuple(
        (*semantic_signatures[index], _evidence_identity(charge))
        for index, charge in enumerate(document.charges)
    )
    exact_counts = Counter(exact_signatures)
    for index, charge in enumerate(document.charges):
        issues.extend(validate_charge(charge, index))
        if charge.evidence and any(not _is_grounded(item, document) for item in charge.evidence):
            issues.append(
                ValidationIssue(
                    "ungrounded_evidence",
                    "费用证据不是输入材料中的连续原文",
                    IssueSeverity.ERROR,
                    index,
                )
            )
        unsupported_changes = charge.explicit_changes - _SUPPORTED_EXPLICIT_CHANGES
        if unsupported_changes:
            issues.append(
                ValidationIssue(
                    "unsupported_explicit_change",
                    f"变更字段不受支持：{', '.join(sorted(unsupported_changes))}",
                    IssueSeverity.ERROR,
                    index,
                )
            )
        change_fields = {item.field_name for item in charge.change_evidence}
        missing_change_evidence = charge.explicit_changes - change_fields
        if missing_change_evidence:
            issues.append(
                ValidationIssue(
                    "unsubstantiated_explicit_change",
                    f"显式变更缺少可核对的原文证据：{', '.join(sorted(missing_change_evidence))}",
                    IssueSeverity.ERROR,
                    index,
                )
            )
        for field_name in charge.explicit_changes & _SUPPORTED_EXPLICIT_CHANGES:
            candidate = _candidate_change_value(field_name, document, charge)
            field_evidence = tuple(
                item for item in charge.change_evidence if item.field_name == field_name
            )
            if candidate is None:
                issues.append(
                    ValidationIssue(
                        "missing_change_value",
                        f"显式变更字段 {field_name} 缺少候选新值",
                        IssueSeverity.ERROR,
                        index,
                    )
                )
            elif field_evidence and not all(
                _is_grounded(item.evidence, document)
                and _change_evidence_matches_value(
                    field_name, item.new_value, item.evidence, candidate
                )
                for item in field_evidence
            ):
                issues.append(
                    ValidationIssue(
                        "change_value_mismatch",
                        f"字段 {field_name} 的变更证据与候选新值不一致",
                        IssueSeverity.ERROR,
                        index,
                    )
                )
        for item in charge.change_evidence:
            if item.field_name not in charge.explicit_changes:
                issues.append(
                    ValidationIssue(
                        "orphan_change_evidence",
                        f"字段 {item.field_name} 的变更证据没有对应的显式变更",
                        IssueSeverity.ERROR,
                        index,
                    )
                )
            if not _is_grounded(item.evidence, document):
                issues.append(
                    ValidationIssue(
                        "ungrounded_change_evidence",
                        "字段变更证据不是其所标注来源文件中的连续原文",
                        IssueSeverity.ERROR,
                        index,
                    )
                )

        if exact_counts[exact_signatures[index]] > 1 and _has_precise_line_location(charge):
            issues.append(
                ValidationIssue(
                    "duplicate_charge",
                    "检测到来自同一来源行的重复费用项目",
                    IssueSeverity.ERROR,
                    index,
                )
            )
        elif semantic_counts[semantic_signatures[index]] > 1:
            issues.append(
                ValidationIssue(
                    "possible_duplicate_charge",
                    "存在同名、同金额、同币种费用；来源位置不同或不够精确，已逐行保留",
                    IssueSeverity.WARNING,
                    index,
                )
            )

        if any(_OCR_CONFUSION.search(item.source_text) for item in charge.evidence):
            issues.append(
                ValidationIssue(
                    "possible_ocr_confusion",
                    "该费用原文中存在可能的 0/O 或 1/I OCR 混淆",
                    IssueSeverity.ERROR,
                    index,
                )
            )

    amounts = tuple(charge.amount for charge in document.charges)
    if document.subtotal is not None and amounts and all(amount is not None for amount in amounts):
        detail_sum = sum((amount for amount in amounts if amount is not None), Decimal("0"))
        if abs(detail_sum - document.subtotal) > Decimal("0.01"):
            issues.append(
                ValidationIssue(
                    "detail_subtotal_mismatch",
                    "费用明细金额之和不等于单据小计",
                    IssueSeverity.ERROR,
                )
            )
    if (
        document.subtotal is not None
        and document.tax is not None
        and document.total is not None
        and abs((document.subtotal + document.tax) - document.total) > Decimal("0.01")
    ):
        issues.append(
            ValidationIssue(
                "total_mismatch",
                "单据小计与税额之和不等于总计",
                IssueSeverity.ERROR,
            )
        )

    evidence_texts = "\n".join(
        item.source_text for charge in document.charges for item in charge.evidence
    )
    if _OCR_CONFUSION.search(document.raw_text) and not _OCR_CONFUSION.search(evidence_texts):
        issues.append(
            ValidationIssue(
                "possible_ocr_confusion",
                "输入材料的非费用内容中存在可能的 0/O 或 1/I OCR 混淆",
                IssueSeverity.WARNING,
            )
        )
    return issues
