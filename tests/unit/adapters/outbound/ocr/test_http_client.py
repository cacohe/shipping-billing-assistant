import json

import httpx
import pytest

from adapters.outbound.ocr.http_client import HttpOcrClient, OcrServiceError


def test_ocr_response_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    def post(*args: object, **kwargs: object) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": {"text": "Invoice", "tables": [["a"], ["b"]]}},
            request=httpx.Request("POST", "https://ocr.test"),
        )

    monkeypatch.setattr(httpx, "post", post)
    result = HttpOcrClient("https://ocr.test").recognize("https://files.test/a.pdf")
    assert json.loads(result.text) == {"text": "Invoice", "tables": [["a"], ["b"]]}
    assert result.tables


def test_structured_ocr_data_is_preserved_as_extraction_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "data": {
            "list": [
                {
                    "invoiceNumber": "TEST-2026-003",
                    "chargeList": [{"chargeItem": "Handling Fee", "amount": "40.00"}],
                }
            ]
        },
        "success": True,
        "message": "文档处理成功",
    }
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200, json=payload, request=httpx.Request("POST", "https://ocr.test")
        ),
    )

    result = HttpOcrClient("https://ocr.test").recognize("https://files.test/a.png")

    assert json.loads(result.text) == payload["data"]
    assert result.raw_payload == payload


def test_ocr_processing_metadata_is_not_exposed_as_document_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "data": {
            "createDate": "2026-10-22 11:40:51",
            "fileName": "",
            "list": [{"invoiceNumber": "INV-1"}],
            "orderType": "INVOICE",
            "pages_split": [[0, 1]],
        },
        "success": True,
    }
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200, json=payload, request=httpx.Request("POST", "https://ocr.test")
        ),
    )

    result = HttpOcrClient("https://ocr.test").recognize("https://files.test/a.pdf")

    assert json.loads(result.text) == {
        "list": [{"invoiceNumber": "INV-1"}],
        "orderType": "INVOICE",
    }
    assert result.raw_payload == payload


def test_structured_ocr_data_is_not_truncated_by_nested_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structured_data = {
        "invoiceNumber": "TEST-2026-005",
        "chargeList": [{"content": "Handling Fee", "amount": "40.00"}],
    }
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={"data": structured_data, "success": True},
            request=httpx.Request("POST", "https://ocr.test"),
        ),
    )

    result = HttpOcrClient("https://ocr.test").recognize("https://files.test/a.png")

    assert json.loads(result.text) == structured_data


def test_ocr_rejects_empty_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200, json={}, request=httpx.Request("POST", "https://ocr.test")
        ),
    )
    with pytest.raises(OcrServiceError):
        HttpOcrClient("https://ocr.test").recognize("https://files.test/a.pdf")


def test_ocr_retries_transient_gateway_error(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter(
        [
            httpx.Response(
                502,
                request=httpx.Request("POST", "https://ocr.test"),
            ),
            httpx.Response(
                200,
                json={"text": "Recovered"},
                request=httpx.Request("POST", "https://ocr.test"),
            ),
        ]
    )
    calls = 0

    def post(*args: object, **kwargs: object) -> httpx.Response:
        nonlocal calls
        calls += 1
        return next(responses)

    monkeypatch.setattr(httpx, "post", post)
    result = HttpOcrClient(
        "https://ocr.test", retry_delay_seconds=0, sleep=lambda _: None
    ).recognize("https://files.test/a.pdf")

    assert calls == 2
    assert result.text == "Recovered"


def test_ocr_returns_safe_error_after_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def post(*args: object, **kwargs: object) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            502,
            request=httpx.Request("POST", "https://ocr.test"),
        )

    monkeypatch.setattr(httpx, "post", post)
    client = HttpOcrClient("https://ocr.test", retry_delay_seconds=0, sleep=lambda _: None)

    with pytest.raises(OcrServiceError, match="HTTP 502") as error:
        client.recognize("https://files.test/private-signed-url")

    assert calls == 3
    assert "private-signed-url" not in str(error.value)
