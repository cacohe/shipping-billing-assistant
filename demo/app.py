"""Streamlit demonstration UI for the application use case."""

import json
import logging
from pathlib import Path
from typing import Protocol

import streamlit as st
from pydantic import ValidationError

from application.dto.documents import InputFile
from application.dto.input_schema import ExistingBillInput
from application.dto.output import records_to_json_data
from application.dto.requests import ProcessingEvent, ProcessingRequest
from application.errors import ApplicationError, UserInputError
from application.presentation import build_result_rows, summarize_results, validate_uploads
from bootstrap import build_application
from bootstrap.logging_config import configure_logging

configure_logging()
logger = logging.getLogger("shipping_billing_assistant.demo")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class UploadedJson(Protocol):
    def getvalue(self) -> bytes: ...


def load_existing_bills(uploaded_file: UploadedJson | None) -> tuple[ExistingBillInput, ...]:
    """Read the optional existing-bill JSON upload."""

    if uploaded_file is None:
        return ()
    try:
        data = json.loads(uploaded_file.getvalue().decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UserInputError("已有账单文件不是有效的 UTF-8 JSON，请检查文件格式。") from exc
    if not isinstance(data, list):
        raise UserInputError("已有账单文件必须包含 JSON 数组")
    try:
        return tuple(ExistingBillInput.model_validate(item) for item in data)
    except ValidationError as exc:
        raise UserInputError("已有账单 JSON 的字段或数据类型不符合要求，请检查后重试。") from exc


def friendly_error_message(error: Exception) -> str:
    """Return safe, actionable text for the demo without exposing technical details."""

    if isinstance(error, ApplicationError):
        return error.user_message
    if isinstance(error, UserInputError):
        return str(error)
    return "处理过程中发生了意外错误，请稍后重试；详细信息请查看服务端日志。"


st.set_page_config(page_title="航运智能账单助手", page_icon="⚓", layout="wide")
st.title("⚓ 航运智能账单助手")
st.caption("从业务材料中抽取、校验并核对费用，所有财务决策都保留原文证据。")

with st.expander("安全处理流程", expanded=False):
    st.markdown(
        """
        **业务材料 → 格式解析与 OCR → 结构化抽取 → 原文证据与财务规则校验**

        **→ 已有账单匹配 → 创建、更新、无变化或待复核**

        系统不会猜测缺失的金额、币种、账单双方或记账方向。信息不足或证据冲突时，
        结果会明确进入 `PENDING_REVIEW`，并保留相关证据和告警。
        """
    )

with st.sidebar:
    st.header("合成演示文件")
    st.caption("下载安全的合成样本，然后在主表单中上传。")
    for label, relative_path, mime_type in (
        ("新账单图片", "tests/fixtures/documents/synthetic-invoice.png", "image/png"),
        ("账单更新请求", "demo/scenarios/update-request.eml", "message/rfc822"),
        (
            "更新场景已有账单",
            "demo/scenarios/existing-bills-update.json",
            "application/json",
        ),
        ("待复核通知", "demo/scenarios/pending-review.eml", "message/rfc822"),
    ):
        sample_path = PROJECT_ROOT / relative_path
        st.download_button(
            label,
            sample_path.read_bytes(),
            file_name=sample_path.name,
            mime=mime_type,
            use_container_width=True,
        )

with st.form("billing-input"):
    files = st.file_uploader(
        "输入文件",
        accept_multiple_files=True,
        type=[
            "eml",
            "pdf",
            "png",
            "jpg",
            "jpeg",
            "tif",
            "tiff",
            "xls",
            "xlsx",
            "xlsm",
            "doc",
            "docx",
        ],
        help=(
            "最多上传 8 个文件；单文件不超过 10 MB，合计不超过 25 MB。"
            "PDF、图片及邮件内的 OCR 附件会自动使用临时存储。"
        ),
    )
    accounting_entity = st.text_input(
        "当前记账主体",
        help="用于判断应收（AR）或应付（AP）；无法确认时结果会进入待复核。",
    )
    existing_file = st.file_uploader(
        "已有账单 JSON（可选）",
        type=["json"],
        help="仅在需要判断更新或无变化时提供，文件顶层必须是 JSON 数组。",
    )
    submitted = st.form_submit_button("开始处理", type="primary")

if submitted:
    logger.info("用户提交处理请求 uploaded_file_count=%d", len(files or ()))
    progress = st.status("正在处理", expanded=True)

    def on_progress(event: ProcessingEvent) -> None:
        progress.write(f"{event.stage.value} — {event.message}")

    try:
        validate_uploads(files or ())
        existing = tuple(item.to_domain() for item in load_existing_bills(existing_file))
        inputs = tuple(
            InputFile(
                file.name,
                file.getvalue(),
                file.type,
            )
            for file in files
        )
        if not inputs:
            raise UserInputError("请上传至少一个输入文件")
        records = build_application().process(
            ProcessingRequest(inputs, existing, accounting_entity or None), on_progress
        )
        output = records_to_json_data(records)
        progress.update(label="处理完成", state="complete", expanded=False)
        st.subheader("最终输出")
        summary = summarize_results(output)
        total_column, automatic_column, review_column, currency_column = st.columns(4)
        total_column.metric("费用项", summary.total_charges)
        automatic_column.metric("自动决策", summary.automatic_decisions)
        review_column.metric("待复核", summary.pending_review)
        currency_column.metric("币种", ", ".join(summary.currencies) or "—")
        if output:
            st.dataframe(build_result_rows(output), use_container_width=True, hide_index=True)
            st.subheader("证据与决策轨迹")
            for index, item in enumerate(output, start=1):
                charge = item["charge_details"]
                title = f"{index}. {charge.get('charge_item') or '未命名费用'}"
                with st.expander(title):
                    st.write(f"**决策：** `{item['operation']}`")
                    for reason in item["audit_trail"]["ai_reasoning"]:
                        st.write(f"- {reason}")
        else:
            st.info("未从已提交材料中抽取到费用记录。")
        with st.expander("原始 JSON 输出", expanded=False):
            st.json(output)
        st.download_button(
            "下载 JSON",
            json.dumps(output, ensure_ascii=False, indent=2),
            "billing-result.json",
            "application/json",
        )
    except Exception as exc:
        logger.exception("处理请求失败 error_type=%s", type(exc).__name__)
        progress.update(label="处理失败", state="error")
        st.error(friendly_error_message(exc))
