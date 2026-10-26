"""Streamlit demonstration UI for the application use case."""

import json
import logging
from typing import Protocol

import streamlit as st
from pydantic import ValidationError

from application.dto.documents import InputFile
from application.dto.input_schema import ExistingBillInput
from application.dto.output import records_to_json_data
from application.dto.requests import ProcessingEvent, ProcessingRequest
from application.errors import ApplicationError, UserInputError
from bootstrap import build_application
from bootstrap.logging_config import configure_logging

configure_logging()
logger = logging.getLogger("shipping_billing_assistant.demo")


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


st.set_page_config(page_title="航运智能账单助手", layout="wide")
st.title("航运智能账单助手")
st.caption("上传材料，查看处理阶段，并获得逐费用项的结构化结果。")

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
        help="PDF、图片及邮件内的 OCR 附件会自动使用临时存储，无需填写文件 URL。",
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
