"""Main application workflow used by the Streamlit demo and Python callers."""

import logging
from dataclasses import replace

from application.dto.output import BillingRecordOutput
from application.dto.requests import (
    ProcessingEvent,
    ProcessingRequest,
    ProcessingStage,
    ProgressCallback,
)
from application.errors import UserInputError
from application.ports.outbound.billing_extractor import BillingExtractorPort
from application.ports.outbound.document_parser import DocumentParserPort
from domain.billing.decision import decide_charge
from domain.billing.matching import match_existing_bill
from domain.billing.normalization import normalize_charge
from domain.billing.validation import ValidationIssue, validate_document

logger = logging.getLogger("shipping_billing_assistant.application")


class ProcessBillingDocuments:
    """Coordinate parsing, extraction, domain decisions, and output validation."""

    def __init__(
        self,
        document_parser: DocumentParserPort,
        billing_extractor: BillingExtractorPort,
    ) -> None:
        self._document_parser = document_parser
        self._billing_extractor = billing_extractor

    @staticmethod
    def _emit(callback: ProgressCallback | None, stage: ProcessingStage, message: str) -> None:
        if callback:
            callback(ProcessingEvent(stage, message))

    def process(
        self,
        request: ProcessingRequest,
        progress_callback: ProgressCallback | None = None,
    ) -> tuple[BillingRecordOutput, ...]:
        self._emit(progress_callback, ProcessingStage.RECEIVED, "已接收处理请求")
        if not request.source_files:
            raise UserInputError("至少需要提供一个输入文件")

        self._emit(progress_callback, ProcessingStage.PARSING, "正在解析输入文件及附件")
        parsed_documents = self._document_parser.parse_all(request.source_files)

        self._emit(progress_callback, ProcessingStage.EXTRACTING, "正在提取账单和费用信息")
        extracted_documents = self._billing_extractor.extract(parsed_documents)
        if not extracted_documents or not any(document.charges for document in extracted_documents):
            raise UserInputError("未能从输入材料中提取到费用项目，请确认文件内容是否清晰完整")

        self._emit(progress_callback, ProcessingStage.NORMALIZING, "正在标准化费用字段")
        normalized_documents = tuple(
            replace(
                document, charges=tuple(normalize_charge(charge) for charge in document.charges)
            )
            for document in extracted_documents
        )

        self._emit(progress_callback, ProcessingStage.VALIDATING, "正在执行数据校验")
        document_issues = {
            index: tuple(validate_document(document))
            for index, document in enumerate(normalized_documents)
        }

        records: list[BillingRecordOutput] = []
        for document_index, document in enumerate(normalized_documents):
            self._emit(progress_callback, ProcessingStage.MATCHING, "正在匹配已有账单")
            for charge_index, charge in enumerate(document.charges):
                match = match_existing_bill(document, charge, request.existing_bills)
                relevant_issues = _issues_for_charge(document_issues[document_index], charge_index)
                self._emit(progress_callback, ProcessingStage.DECIDING, "正在判断操作类型和 AR/AP")
                decision = decide_charge(
                    document=document,
                    charge=charge,
                    match=match,
                    validation_issues=relevant_issues,
                    accounting_entity=request.accounting_entity,
                )
                logger.info(
                    "账单决策完成 operation=%s matched_bill_id=%s "
                    "candidate_bill_id=%s match_rule=%s",
                    decision.operation.value,
                    decision.matched_bill_id,
                    decision.candidate_bill_id,
                    match.rule,
                )
                records.append(BillingRecordOutput.from_decision(decision))

        self._emit(progress_callback, ProcessingStage.BUILDING_OUTPUT, "正在校验最终 JSON")
        validated = tuple(BillingRecordOutput.model_validate(record) for record in records)
        self._emit(progress_callback, ProcessingStage.COMPLETED, "处理完成")
        return validated


def _issues_for_charge(
    issues: tuple[ValidationIssue, ...], charge_index: int
) -> tuple[ValidationIssue, ...]:
    return tuple(issue for issue in issues if issue.charge_index in {None, charge_index})
