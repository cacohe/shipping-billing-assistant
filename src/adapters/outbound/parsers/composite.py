"""Format dispatch and recursive attachment parsing."""

import logging

from adapters.outbound.parsers.base import DocumentParseError, FormatParser
from adapters.outbound.parsers.email_parser import EmlParser
from adapters.outbound.parsers.excel_parser import ExcelParser
from adapters.outbound.parsers.ocr_document_parser import OcrDocumentParser
from adapters.outbound.parsers.word_parser import LegacyDocParser, WordParser
from application.dto.documents import InputFile, ParsedDocument
from application.ports.outbound.ocr import OcrPort
from application.ports.outbound.temporary_file_store import TemporaryFileStorePort

logger = logging.getLogger("shipping_billing_assistant.parsers")


class CompositeDocumentParser:
    """Select the concrete parser and recursively parse EML attachments."""

    def __init__(
        self,
        ocr_client: OcrPort,
        temporary_file_store: TemporaryFileStorePort | None = None,
        download_url_ttl_seconds: int = 600,
        legacy_doc_command: str = "soffice",
    ) -> None:
        self._parsers: list[FormatParser] = []
        self._parsers.extend(
            [
                EmlParser(self.parse_one),
                ExcelParser(),
                WordParser(),
                LegacyDocParser(legacy_doc_command),
                OcrDocumentParser(ocr_client, temporary_file_store, download_url_ttl_seconds),
            ]
        )

    def parse_all(self, files: tuple[InputFile, ...]) -> tuple[ParsedDocument, ...]:
        logger.info("开始解析输入文件 file_count=%d", len(files))
        return tuple(self.parse_one(file) for file in files)

    def parse_one(self, file: InputFile) -> ParsedDocument:
        for parser in self._parsers:
            if parser.supports(file):
                logger.info("解析文件 file=%s parser=%s", file.name, type(parser).__name__)
                document = parser.parse(file)
                logger.info(
                    "文件解析完成 file=%s source_type=%s child_count=%d warning_count=%d",
                    file.name,
                    document.source_type,
                    len(document.children),
                    len(document.warnings),
                )
                return document
        logger.warning("不支持的文件格式 file=%s", file.name)
        raise DocumentParseError(f"不支持的文件格式：{file.name}")
