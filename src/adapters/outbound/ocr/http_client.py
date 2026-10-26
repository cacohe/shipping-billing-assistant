"""HTTP client for the OCR protocol supported by this application."""

import json
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from application.errors import ApplicationError
from application.ports.outbound.ocr import OcrResult

logger = logging.getLogger("shipping_billing_assistant.ocr")


class OcrServiceError(ApplicationError):
    """Raised when OCR cannot return a usable result."""

    user_message = "OCR 服务暂时不可用，请稍后重新提交；已上传的临时文件会自动清理。"


class HttpOcrClient:
    def __init__(
        self,
        endpoint: str,
        *,
        connect_timeout: float = 10.0,
        read_timeout: float = 300.0,
        max_attempts: int = 3,
        retry_delay_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts 必须大于 0")
        self._endpoint = endpoint
        self._timeout = httpx.Timeout(read_timeout, connect=connect_timeout)
        self._max_attempts = max_attempts
        self._retry_delay_seconds = retry_delay_seconds
        self._sleep = sleep

    def recognize(self, file_url: str) -> OcrResult:
        logger.info("OCR 服务请求开始")
        payload = {
            "file": file_url,
            "task": "orderChange",
            "callBack": "",
            "taskType": "",
        }
        response = self._post_with_retry(payload)
        try:
            data = response.json()
        except ValueError as exc:
            logger.error("OCR 服务返回的内容不是有效 JSON")
            raise OcrServiceError("OCR 服务返回的内容不是有效 JSON") from exc
        if not isinstance(data, dict):
            logger.error("OCR 服务返回了非对象 JSON")
            raise OcrServiceError("OCR 响应必须是 JSON 对象")
        tables = _extract_tables(data)
        structured_data = data.get("data")
        if isinstance(structured_data, (dict, list)) and structured_data:
            text = json.dumps(_business_data(structured_data), ensure_ascii=False)
        else:
            text = _extract_text(data)
        if not text and not tables:
            logger.warning("OCR 响应不包含文本或表格")
            raise OcrServiceError("OCR 响应中未找到文本或表格")
        logger.info("OCR 服务请求完成 text_chars=%d table_count=%d", len(text), len(tables))
        return OcrResult(text=text, tables=tables, raw_payload=data)

    def _post_with_retry(self, payload: dict[str, str]) -> httpx.Response:
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = httpx.post(self._endpoint, json=payload, timeout=self._timeout)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if status_code in {502, 503, 504} and attempt < self._max_attempts:
                    logger.warning(
                        "OCR 服务暂时不可用，准备重试 status_code=%d attempt=%d/%d",
                        status_code,
                        attempt,
                        self._max_attempts,
                    )
                    self._sleep(self._retry_delay_seconds * attempt)
                    continue
                logger.error(
                    "OCR 服务请求失败 status_code=%d attempt=%d/%d",
                    status_code,
                    attempt,
                    self._max_attempts,
                )
                raise OcrServiceError(f"OCR 服务请求失败（HTTP {status_code}）") from exc
            except httpx.RequestError as exc:
                if attempt < self._max_attempts:
                    logger.warning(
                        "OCR 服务连接异常，准备重试 error_type=%s attempt=%d/%d",
                        type(exc).__name__,
                        attempt,
                        self._max_attempts,
                    )
                    self._sleep(self._retry_delay_seconds * attempt)
                    continue
                logger.error(
                    "OCR 服务连接失败 error_type=%s attempt=%d/%d",
                    type(exc).__name__,
                    attempt,
                    self._max_attempts,
                )
                raise OcrServiceError(f"OCR 服务连接失败：{type(exc).__name__}") from exc
        raise AssertionError("OCR retry loop ended unexpectedly")


def _business_data(value: dict[str, Any] | list[Any]) -> dict[str, Any] | list[Any]:
    """Remove OCR job metadata that must not be interpreted as document facts."""

    if not isinstance(value, dict):
        return value
    metadata_keys = {"createDate", "fileName", "pages_split"}
    return {key: child for key, child in value.items() if key not in metadata_keys}


def _extract_text(value: Any) -> str:
    fragments: list[str] = []

    def visit(item: Any, key: str | None = None) -> None:
        if isinstance(item, dict):
            for child_key, child in item.items():
                visit(child, str(child_key).casefold())
        elif isinstance(item, list):
            for child in item:
                visit(child, key)
        elif (
            isinstance(item, str)
            and key in {"text", "content", "markdown", "ocr_text"}
            and item.strip()
        ):
            fragments.append(item.strip())

    visit(value)
    return "\n".join(dict.fromkeys(fragments))


def _extract_tables(value: Any) -> tuple[tuple[tuple[Any, ...], ...], ...]:
    candidates: list[tuple[tuple[Any, ...], ...]] = []

    def visit(item: Any, key: str | None = None) -> None:
        if isinstance(item, dict):
            for child_key, child in item.items():
                visit(child, str(child_key).casefold())
        elif isinstance(item, list):
            if (
                key in {"table", "tables", "rows"}
                and item
                and all(isinstance(row, list) for row in item)
            ):
                candidates.append(tuple(tuple(cell for cell in row) for row in item))
            else:
                for child in item:
                    visit(child, key)

    visit(value)
    return tuple(candidates)
