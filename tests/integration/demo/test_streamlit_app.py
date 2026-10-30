from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from adapters.outbound.ocr.http_client import OcrServiceError
from application.dto.documents import InputFile

APP_PATH = Path(__file__).parents[3] / "demo" / "app.py"
EXISTING_BILL_PATH = APP_PATH.parent / "scenarios" / "existing-bills-update.json"
MB = 1024 * 1024


@patch("bootstrap.build_application")
def test_demo_accepts_input_and_renders_output(build_application: object) -> None:
    application = build_application.return_value  # type: ignore[attr-defined]
    application.process.return_value = ()

    app = AppTest.from_file(APP_PATH).run(timeout=30)
    app.file_uploader[0].upload(
        "bill.xlsx",
        b"workbook",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    app.text_input[0].set_value("Carrier")
    app.button[0].click().run(timeout=30)

    assert not app.exception
    assert app.subheader[0].value == "最终输出"
    application.process.assert_called_once()


@patch("bootstrap.build_application")
def test_demo_accepts_local_pdf_upload(build_application: object) -> None:
    application = build_application.return_value  # type: ignore[attr-defined]
    application.process.return_value = ()

    app = AppTest.from_file(APP_PATH).run(timeout=30)
    app.file_uploader[0].upload("invoice.pdf", b"pdf", "application/pdf")
    app.button[0].click().run(timeout=30)

    assert not app.exception
    request = application.process.call_args.args[0]
    assert request.source_files == (InputFile("invoice.pdf", b"pdf", "application/pdf"),)


def test_demo_reports_invalid_existing_bill_json_shape() -> None:
    app = AppTest.from_file(APP_PATH).run(timeout=30)
    app.file_uploader[0].upload(
        "bill.xlsx",
        b"workbook",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    app.file_uploader[1].upload("existing.json", b"{}", "application/json")
    app.button[0].click().run(timeout=30)

    assert not app.exception
    assert "必须包含 JSON 数组" in app.error[0].value


def test_demo_requires_at_least_one_source() -> None:
    app = AppTest.from_file(APP_PATH).run(timeout=30)
    app.button[0].click().run(timeout=30)

    assert not app.exception
    assert "请上传至少一个" in app.error[0].value


@patch("bootstrap.build_application")
def test_demo_hides_technical_ocr_error(build_application: object) -> None:
    application = build_application.return_value  # type: ignore[attr-defined]
    application.process.side_effect = OcrServiceError(
        "OCR 服务请求失败（HTTP 502）：https://private.example/signed-token"
    )

    app = AppTest.from_file(APP_PATH).run(timeout=30)
    app.file_uploader[0].upload("invoice.pdf", b"pdf", "application/pdf")
    app.button[0].click().run(timeout=30)

    assert not app.exception
    assert "OCR 服务暂时不可用" in app.error[0].value
    assert "502" not in app.error[0].value
    assert "signed-token" not in app.error[0].value


@patch("bootstrap.build_application")
def test_demo_hides_unexpected_error_details(build_application: object) -> None:
    application = build_application.return_value  # type: ignore[attr-defined]
    application.process.side_effect = ValueError("internal URL and implementation details")

    app = AppTest.from_file(APP_PATH).run(timeout=30)
    app.file_uploader[0].upload("bill.xlsx", b"workbook")
    app.button[0].click().run(timeout=30)

    assert not app.exception
    assert "发生了意外错误" in app.error[0].value
    assert "internal URL" not in app.error[0].value


@patch("bootstrap.build_application")
def test_demo_rejects_oversized_existing_bill_json(build_application: object) -> None:
    application = build_application.return_value  # type: ignore[attr-defined]
    application.process.return_value = ()
    payload = EXISTING_BILL_PATH.read_bytes()
    oversized_payload = payload + b" " * (10 * MB + 1 - len(payload))

    app = AppTest.from_file(APP_PATH).run(timeout=30)
    app.file_uploader[0].upload("bill.xlsx", b"workbook")
    app.file_uploader[1].upload("existing.json", oversized_payload, "application/json")
    app.button[0].click().run(timeout=30)

    assert not app.exception
    assert "10 MB" in app.error[0].value
    application.process.assert_not_called()


@patch("bootstrap.build_application")
def test_demo_counts_existing_bill_json_toward_request_limit(build_application: object) -> None:
    application = build_application.return_value  # type: ignore[attr-defined]
    application.process.return_value = ()
    payload = EXISTING_BILL_PATH.read_bytes()
    ten_mb_payload = payload + b" " * (10 * MB - len(payload))

    app = AppTest.from_file(APP_PATH).run(timeout=30)
    app.file_uploader[0].upload("bill-a.xlsx", b"a" * (8 * MB))
    app.file_uploader[0].upload("bill-b.xlsx", b"b" * (8 * MB))
    app.file_uploader[1].upload("existing.json", ten_mb_payload, "application/json")
    app.button[0].click().run(timeout=30)

    assert not app.exception
    assert "合计" in app.error[0].value
    assert "25 MB" in app.error[0].value
    application.process.assert_not_called()
