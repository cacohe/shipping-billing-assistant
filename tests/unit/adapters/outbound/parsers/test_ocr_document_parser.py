import pytest

from adapters.outbound.parsers.base import DocumentParseError
from adapters.outbound.parsers.ocr_document_parser import OcrDocumentParser
from application.dto.documents import InputFile
from application.ports.outbound.ocr import OcrResult


class Ocr:
    def __init__(self, error: Exception | None = None) -> None:
        self.urls: list[str] = []
        self.error = error

    def recognize(self, file_url: str) -> OcrResult:
        self.urls.append(file_url)
        if self.error:
            raise self.error
        return OcrResult("Invoice")


class Store:
    def __init__(self, delete_error: Exception | None = None) -> None:
        self.uploaded: list[InputFile] = []
        self.deleted: list[str] = []
        self.delete_error = delete_error

    def upload(self, file: InputFile) -> str:
        self.uploaded.append(file)
        return "ocr-inputs/file.pdf"

    def create_download_url(self, key: str, expires_in_seconds: int) -> str:
        assert key == "ocr-inputs/file.pdf"
        assert expires_in_seconds == 600
        return "https://storage.test/file.pdf?token=test"

    def delete(self, key: str) -> None:
        self.deleted.append(key)
        if self.delete_error:
            raise self.delete_error


def test_local_ocr_file_is_hosted_and_deleted() -> None:
    ocr = Ocr()
    store = Store()

    parsed = OcrDocumentParser(ocr, store).parse(InputFile("invoice.pdf", b"pdf"))

    assert parsed.raw_text == "Invoice"
    assert store.uploaded == [InputFile("invoice.pdf", b"pdf")]
    assert ocr.urls == ["https://storage.test/file.pdf?token=test"]
    assert store.deleted == ["ocr-inputs/file.pdf"]


def test_pdf_embedded_text_is_combined_with_ocr_result() -> None:
    ocr = Ocr()
    store = Store()
    extracted_contents: list[bytes] = []

    def extract_pdf_text(content: bytes) -> str:
        extracted_contents.append(content)
        return "D/C No. DN-DEMO-3001\nCURRENCY USD\nHANDLING CHARGE 65.00"

    parsed = OcrDocumentParser(ocr, store, pdf_text_extractor=extract_pdf_text).parse(
        InputFile("invoice.pdf", b"pdf")
    )

    assert extracted_contents == [b"pdf"]
    assert parsed.raw_text == (
        "OCR structured result:\nInvoice\n\n"
        "Embedded PDF text:\n"
        "D/C No. DN-DEMO-3001\nCURRENCY USD\nHANDLING CHARGE 65.00"
    )


def test_image_does_not_run_pdf_text_extractor() -> None:
    parsed = OcrDocumentParser(
        Ocr(),
        Store(),
        pdf_text_extractor=lambda _: (_ for _ in ()).throw(AssertionError("not expected")),
    ).parse(InputFile("invoice.png", b"png"))

    assert parsed.raw_text == "Invoice"


def test_temporary_file_is_deleted_when_ocr_fails() -> None:
    ocr = Ocr(RuntimeError("OCR unavailable"))
    store = Store()

    with pytest.raises(RuntimeError, match="OCR unavailable"):
        OcrDocumentParser(ocr, store).parse(InputFile("invoice.pdf", b"pdf"))

    assert store.deleted == ["ocr-inputs/file.pdf"]


def test_cleanup_failure_after_success_does_not_discard_ocr_result() -> None:
    store = Store(RuntimeError("delete unavailable"))

    parsed = OcrDocumentParser(Ocr(), store).parse(InputFile("invoice.pdf", b"pdf"))

    assert parsed.raw_text == "Invoice"
    assert store.deleted == ["ocr-inputs/file.pdf"]


def test_local_ocr_file_requires_temporary_storage_configuration() -> None:
    with pytest.raises(DocumentParseError, match="需要配置七牛临时存储"):
        OcrDocumentParser(Ocr()).parse(InputFile("invoice.pdf", b"pdf"))
