"""PDF and image parser backed by the provided OCR service."""

import logging
from collections.abc import Callable
from io import BytesIO

from pypdf import PdfReader

from adapters.outbound.parsers.base import DocumentParseError
from application.dto.documents import (
    InputFile,
    ParsedDocument,
    SourceLocation,
    TableBlock,
    TextBlock,
)
from application.ports.outbound.ocr import OcrPort, OcrResult
from application.ports.outbound.temporary_file_store import TemporaryFileStorePort

logger = logging.getLogger("shipping_billing_assistant.parsers.ocr")


def extract_embedded_pdf_text(content: bytes) -> str:
    """Extract a PDF's text layer as a supplement to the OCR result."""

    try:
        reader = PdfReader(BytesIO(content))
        return "\n".join(text for page in reader.pages if (text := page.extract_text()))
    except Exception as exc:
        logger.warning("PDF 文本层提取失败 error_type=%s", type(exc).__name__)
        return ""


class OcrDocumentParser:
    def __init__(
        self,
        ocr_client: OcrPort,
        temporary_file_store: TemporaryFileStorePort | None = None,
        download_url_ttl_seconds: int = 600,
        pdf_text_extractor: Callable[[bytes], str] = extract_embedded_pdf_text,
    ) -> None:
        self._ocr_client = ocr_client
        self._temporary_file_store = temporary_file_store
        self._download_url_ttl_seconds = download_url_ttl_seconds
        self._pdf_text_extractor = pdf_text_extractor

    def supports(self, file: InputFile) -> bool:
        return file.name.lower().endswith((".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"))

    def parse(self, file: InputFile) -> ParsedDocument:
        result = self._recognize(file)
        location = SourceLocation(source_name=file.name)
        tables = tuple(
            TableBlock(
                headers=tuple(str(value) for value in table[0]), rows=table[1:], location=location
            )
            for table in result.tables
            if table
        )
        source_type = "PDF" if file.name.lower().endswith(".pdf") else "IMAGE"
        raw_text = result.text
        if source_type == "PDF":
            embedded_text = self._pdf_text_extractor(file.content).strip()
            if embedded_text:
                raw_text = (
                    f"OCR structured result:\n{result.text}\n\nEmbedded PDF text:\n{embedded_text}"
                )
        return ParsedDocument(
            source_name=file.name,
            source_type=source_type,
            text_blocks=(TextBlock(raw_text, location),) if raw_text else (),
            tables=tables,
            raw_text=raw_text,
            raw_payload=result.raw_payload,
        )

    def _recognize(self, file: InputFile) -> OcrResult:
        if file.source_url:
            logger.info("使用已有下载地址调用 OCR file=%s", file.name)
            return self._ocr_client.recognize(file.source_url)
        if self._temporary_file_store is None:
            logger.warning("OCR 缺少临时存储配置 file=%s", file.name)
            raise DocumentParseError(f"{file.name} 需要配置七牛临时存储后才能调用 OCR")
        logger.info("上传 OCR 临时文件 file=%s size_bytes=%d", file.name, len(file.content))
        key = self._temporary_file_store.upload(file)
        try:
            logger.debug("生成 OCR 临时下载地址 object_key=%s", key)
            url = self._temporary_file_store.create_download_url(
                key, self._download_url_ttl_seconds
            )
            logger.info("开始 OCR 识别 file=%s object_key=%s", file.name, key)
            result = self._ocr_client.recognize(url)
        except Exception:
            logger.exception("OCR 处理失败 file=%s object_key=%s", file.name, key)
            try:
                self._temporary_file_store.delete(key)
                logger.info("已清理失败任务的临时文件 object_key=%s", key)
            except Exception:
                logger.exception("清理失败任务的临时文件失败 object_key=%s", key)
            raise
        try:
            self._temporary_file_store.delete(key)
            logger.info("OCR 处理完成并已清理临时文件 file=%s object_key=%s", file.name, key)
        except Exception:
            logger.exception("OCR 处理完成但临时文件清理失败 file=%s object_key=%s", file.name, key)
        return result
