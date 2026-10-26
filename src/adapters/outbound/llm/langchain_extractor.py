"""LangChain extraction chain backed by a LiteLLM chat model."""

import json
import logging
import re
from dataclasses import asdict
from email.utils import getaddresses
from typing import Any

import pycountry
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import ValidationError

from adapters.outbound.llm.schemas import (
    ExtractedBillingDocument,
    ExtractedParties,
    ExtractionEnvelope,
)
from application.dto.documents import ParsedDocument
from application.errors import ApplicationError
from domain.billing.entities import (
    BillingDocument,
    Charge,
    DocumentInfo,
    Evidence,
    ExplicitChangeEvidence,
    SourceMaterial,
    TransactionParties,
)
from domain.billing.enums import ChargeDirection
from domain.billing.normalization import normalize_currency

logger = logging.getLogger("shipping_billing_assistant.llm")

_SYSTEM_PROMPT = """你是航运账单信息抽取器。只提取输入材料中存在的信息，不得补全或猜测。
每个费用项目单独输出。无法确定的字段使用 null。金额使用数字，币种使用三位代码。
quantity 和 unit_price 属于费用行；subtotal、tax 和 total 属于整个单据，不得放入费用行。
explicit_changes 只列出材料明确要求相对已有账单修改的字段；普通账单陈述不是变更指令。
每个输入及附件都有唯一 source_id。每条 evidence 必须原样复制对应输入的 source_id 和
source_name。每个 explicit_changes 字段必须在 change_evidence 中提供同名 field_name、
原文里代表候选新值的逐字 new_value，以及包含该新值和变更指令的连续逐字原文；
没有可核对变更原文时，explicit_changes 必须为空。
费用字段使用 amount、currency、payment_term、quantity、unit_price 或 canonical_name；
费用行的 P/C、PREPAID/COLLECT 或明确等价列表示付款方式：P/PP/PREPAID 输出 PP，
C/CC/COLLECT 输出 CC。单据头的 TERMS COD、NET 等是结算条件，不得代替费用行付款方式。
单据和交易方字段使用 document_info.document_type、document_info.reference_no、
document_info.document_date、transaction_party.issuer、transaction_party.recipient 等完整路径。
reference_no 只填写当前发票、Debit/Credit Note 或通知本身明确标注的单据号（如 Invoice No.、
D/C No.）；B/L、MBL/HBL、Booking No. 和 Container No. 必须分别放入对应字段，绝不能复制到
reference_no；材料没有独立单据号时 reference_no 使用 null。
issuer 和 recipient 表示本账单的开具方与受单方。账单明确由一方开具，并把客户或 CONSIGNEE
列为本账单受单方时，可将其作为 recipient；普通运输提单中的 CONSIGNEE 本身不足以证明收费关系。
charge_direction 表示谁向谁收费，不能仅由 Debit Note 或 Credit Note 标题推断；当费用列明确为
DEBIT、余额明确应付给 issuer，且 recipient 有原文依据时，可输出 ISSUER_CHARGES_RECIPIENT；
当 issuer 明确向 recipient 发出账单或费用通知，且费用表或应付合计要求 recipient 付款时，也可
输出 ISSUER_CHARGES_RECIPIENT。不得仅凭提单中的 SHIPPER/CONSIGNEE 角色推断收费方向。
OCR structured result 中的 createDate（若旧响应仍包含）是 OCR 任务处理时间，不是单据日期；
PAI-* fileType 是 OCR 分类标签，应优先使用 PDF 文本层中的实际单据类型。
只抽取当前单据实际应付/应收费用表中的行项目；通知条款、费率示例、潜在罚款、银行说明
以及“如发生则收费”等说明性文字不是本单据费用。重复出现的同名实际费用行必须逐行保留，不能合并。
每个费用项目必须至少提供一条可核对的文件名和原文证据；source_text 必须是
输入材料中连续的逐字原文，不得改写、概括或拼接。输出必须严格符合给定 JSON Schema。"""

_REPAIR_PROMPT = """你是 JSON 结构修复器。只修复给定输出的 JSON 语法和 Schema 结构，
不得增加原输出中不存在的业务事实。无法恢复的字段使用 null。只返回修复后的 JSON。"""

_EMPTY_RESULT_REVIEW_PROMPT = """上一次抽取输出结构合法，但没有包含任何费用项目。
输入中存在金额候选，请进行一次保守复核。
请重新逐项检查邮件正文、单据正文和费用表，只提取材料中明确存在的实际应付或应收费用。
邮件或通知中“某方 pay 某方：费用名 + 金额”这类明确指定费用名称、承担方和金额的语句，
属于需要复核的实际费用候选；只有 PREPAID/COLLECT 而没有金额的运输条款不是金额费用。
潜在罚款、费率示例、银行说明和“如发生则收费”的条件文字仍不得抽取。
如果复核后确实没有实际费用，保持 charges 为空；不得猜测或补全。只返回符合 Schema 的 JSON。"""

_CURRENCY_SYMBOL_AMOUNT_PATTERN = re.compile(r"[$€£¥￥]\s*\d")
_CURRENCY_CODE_AMOUNT_PATTERN = re.compile(
    r"\b([A-Z]{3})\s*[:：]?\s*\d|\d[\d,.]*\s*([A-Z]{3})\b",
    re.IGNORECASE,
)


class ExtractionError(ApplicationError):
    """Raised when the model cannot produce a valid extraction envelope."""

    user_message = "智能信息提取暂时未能生成有效结果，请稍后重试或更换输入文件。"


class LangChainBillingExtractor:
    def __init__(self, model: BaseChatModel) -> None:
        self._model = model
        self._parser: PydanticOutputParser[ExtractionEnvelope] = PydanticOutputParser(
            pydantic_object=ExtractionEnvelope
        )
        self._prompt = ChatPromptTemplate.from_messages(
            [
                ("system", _SYSTEM_PROMPT),
                (
                    "human",
                    "{format_instructions}\n\n以下是解析后的输入文档：\n{documents}",
                ),
            ]
        )

    def extract(self, documents: tuple[ParsedDocument, ...]) -> tuple[BillingDocument, ...]:
        logger.info("LLM 结构化抽取开始 document_count=%d", len(documents))
        payload = json.dumps(
            [
                _document_to_prompt_data(document, str(index))
                for index, document in enumerate(documents)
            ],
            ensure_ascii=False,
            default=str,
        )
        chain = self._prompt | self._model | StrOutputParser()
        raw = chain.invoke(
            {
                "format_instructions": self._parser.get_format_instructions(),
                "documents": payload,
            }
        )
        try:
            envelope = self._parser.parse(raw)
        except (OutputParserException, ValidationError, ValueError):
            logger.warning("LLM 首次输出不符合 Schema，尝试一次结构修复")
            envelope = self._repair_once(raw)
        if not any(
            document.charges for document in envelope.documents
        ) and _documents_contain_amount_candidate(documents):
            logger.warning("LLM 返回空费用但输入含金额候选，尝试一次语义复核")
            reviewed = self._review_empty_once(payload)
            if reviewed is not None:
                envelope = _merge_reviewed_charges(envelope, reviewed)
        result = tuple(_to_domain(document, documents) for document in envelope.documents)
        logger.info(
            "LLM 结构化抽取完成 document_count=%d charge_count=%d",
            len(result),
            sum(len(document.charges) for document in result),
        )
        return result

    def _review_empty_once(self, payload: str) -> ExtractionEnvelope | None:
        review_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", f"{_SYSTEM_PROMPT}\n\n{_EMPTY_RESULT_REVIEW_PROMPT}"),
                (
                    "human",
                    "{format_instructions}\n\n以下是解析后的输入文档：\n{documents}",
                ),
            ]
        )
        reviewed = (review_prompt | self._model | StrOutputParser()).invoke(
            {
                "format_instructions": self._parser.get_format_instructions(),
                "documents": payload,
            }
        )
        try:
            return self._parser.parse(reviewed)
        except (OutputParserException, ValidationError, ValueError):
            logger.warning("LLM 空费用语义复核未返回有效 Schema，保留首次结构化结果")
            return None

    def _repair_once(self, raw: str) -> ExtractionEnvelope:
        repair_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", _REPAIR_PROMPT),
                (
                    "human",
                    "{format_instructions}\n\n待修复输出:\n{raw_output}",
                ),
            ]
        )
        repaired = (repair_prompt | self._model | StrOutputParser()).invoke(
            {
                "format_instructions": self._parser.get_format_instructions(),
                "raw_output": raw,
            }
        )
        try:
            envelope = self._parser.parse(repaired)
            logger.info("LLM 输出结构修复成功")
            return envelope
        except (OutputParserException, ValidationError, ValueError) as exc:
            logger.error("LLM 输出结构修复失败 error_type=%s", type(exc).__name__)
            raise ExtractionError("LLM 未返回符合约定 Schema 的账单数据") from exc


def _has_amount_candidate(payload: str) -> bool:
    if _CURRENCY_SYMBOL_AMOUNT_PATTERN.search(payload):
        return True
    for match in _CURRENCY_CODE_AMOUNT_PATTERN.finditer(payload):
        code = normalize_currency(match.group(1) or match.group(2))
        if code is not None and pycountry.currencies.get(alpha_3=code) is not None:
            return True
    return False


def _documents_contain_amount_candidate(documents: tuple[ParsedDocument, ...]) -> bool:
    for document in documents:
        fragments = [document.raw_text]
        fragments.extend(block.text for block in document.text_blocks)
        fragments.extend(str(value) for value in document.metadata.values() if value is not None)
        fragments.extend(
            " ".join(str(value) for value in row if value is not None)
            for table in document.tables
            for row in table.rows
        )
        if any(_has_amount_candidate(fragment) for fragment in fragments if fragment):
            return True
        if _documents_contain_amount_candidate(document.children):
            return True
    return False


def _merge_reviewed_charges(
    initial: ExtractionEnvelope,
    reviewed: ExtractionEnvelope,
) -> ExtractionEnvelope:
    if not initial.documents and len(reviewed.documents) == 1:
        logger.info("LLM 首次返回空信封，接受语义复核得到的唯一单据")
        return reviewed
    if len(initial.documents) != 1 or len(reviewed.documents) != 1:
        logger.warning(
            "LLM 空费用语义复核不是唯一单据，无法安全合并费用，保留首次结构化结果 "
            "initial_count=%d reviewed_count=%d",
            len(initial.documents),
            len(reviewed.documents),
        )
        return initial
    document = initial.documents[0].model_copy(update={"charges": reviewed.documents[0].charges})
    return initial.model_copy(update={"documents": [document]})


def _document_to_prompt_data(document: ParsedDocument, source_id: str) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "source_name": document.source_name,
        "source_type": document.source_type,
        "metadata": document.metadata,
        "raw_text": document.raw_text,
        "tables": [
            {
                "headers": table.headers,
                "rows": table.rows,
                "source": asdict(table.location),
            }
            for table in document.tables
        ],
        "children": [
            _document_to_prompt_data(child, f"{source_id}/{index}")
            for index, child in enumerate(document.children)
        ],
        "warnings": document.warnings,
    }


def _to_domain(
    extracted: ExtractedBillingDocument,
    source_documents: tuple[ParsedDocument, ...],
) -> BillingDocument:
    charges = tuple(
        Charge(
            raw_name=charge.raw_name,
            canonical_name=None,
            amount=charge.amount,
            currency=charge.currency,
            payment_term=charge.payment_term,
            quantity=charge.quantity,
            unit_price=charge.unit_price,
            confidence=charge.confidence,
            explicit_changes=frozenset(charge.explicit_changes),
            evidence=tuple(Evidence(**item.model_dump()) for item in charge.evidence),
            change_evidence=tuple(
                ExplicitChangeEvidence(
                    field_name=item.field_name,
                    new_value=item.new_value,
                    evidence=Evidence(**item.evidence.model_dump()),
                )
                for item in charge.change_evidence
            ),
        )
        for charge in extracted.charges
    )
    source_materials = _source_materials(source_documents)
    raw_text = "\n".join(material.text for material in source_materials if material.text)
    parties = _validated_parties(extracted.parties, source_documents)
    parties_changed = parties != TransactionParties(**extracted.parties.model_dump())
    return BillingDocument(
        document_info=DocumentInfo(**extracted.document_info.model_dump()),
        parties=parties,
        charges=charges,
        charge_direction=(
            ChargeDirection(extracted.charge_direction)
            if extracted.charge_direction and not parties_changed
            else None
        ),
        subtotal=extracted.subtotal,
        tax=extracted.tax,
        total=extracted.total,
        raw_text=raw_text,
        reasoning=tuple(extracted.reasoning),
        source_materials=source_materials,
    )


def _validated_parties(
    extracted: ExtractedParties,
    source_documents: tuple[ParsedDocument, ...],
) -> TransactionParties:
    """Reject parties copied only from email transport headers."""

    header_values: set[str] = set()
    business_fragments: list[str] = []

    def visit(document: ParsedDocument) -> None:
        if document.raw_text:
            business_fragments.append(document.raw_text)
        business_fragments.extend(block.text for block in document.text_blocks)
        business_fragments.extend(
            " ".join(str(value) for value in row if value is not None)
            for table in document.tables
            for row in table.rows
        )
        if document.source_type == "EML":
            headers = [str(document.metadata.get(key, "")) for key in ("from", "to")]
            header_values.update(value.strip().casefold() for value in headers if value.strip())
            for display_name, address in getaddresses(headers):
                if display_name.strip():
                    header_values.add(display_name.strip().casefold())
                if address.strip():
                    header_values.add(address.strip().casefold())
        for child in document.children:
            visit(child)

    for source in source_documents:
        visit(source)
    business_text = "\n".join(business_fragments).casefold()

    def keep(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().casefold()
        if normalized in header_values and normalized not in business_text:
            return None
        return value

    return TransactionParties(issuer=keep(extracted.issuer), recipient=keep(extracted.recipient))


def _source_materials(
    documents: tuple[ParsedDocument, ...], parent_id: str | None = None
) -> tuple[SourceMaterial, ...]:
    materials: list[SourceMaterial] = []
    for index, document in enumerate(documents):
        source_id = f"{parent_id}/{index}" if parent_id is not None else str(index)
        fragments: list[str] = []
        if document.raw_text:
            fragments.append(document.raw_text)
        fragments.extend(str(value) for value in document.metadata.values() if value)
        for table in document.tables:
            fragments.append(" | ".join(table.headers))
            fragments.extend(
                " | ".join(str(value) for value in row if value is not None) for row in table.rows
            )
        materials.append(SourceMaterial(source_id, document.source_name, "\n".join(fragments)))
        materials.extend(_source_materials(document.children, source_id))
    return tuple(materials)
