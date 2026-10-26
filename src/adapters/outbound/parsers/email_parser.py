"""RFC email parsing with recursive attachment dispatch."""

import logging
import re
from collections.abc import Callable
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser

from application.dto.documents import InputFile, ParsedDocument, SourceLocation, TextBlock

logger = logging.getLogger("shipping_billing_assistant.parsers.email")


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


class EmlParser:
    def __init__(self, attachment_parser: Callable[[InputFile], ParsedDocument]) -> None:
        self._attachment_parser = attachment_parser

    def supports(self, file: InputFile) -> bool:
        return file.name.lower().endswith(".eml") or file.media_type == "message/rfc822"

    def parse(self, file: InputFile) -> ParsedDocument:
        logger.info("开始解析邮件 file=%s", file.name)
        message = BytesParser(policy=policy.default).parsebytes(file.content)
        body_parts: list[str] = []
        children: list[ParsedDocument] = []
        warnings: list[str] = []

        for part in message.walk():
            if part.is_multipart():
                continue
            disposition = part.get_content_disposition()
            filename = part.get_filename()
            if filename and disposition != "attachment" and part.get("Content-ID"):
                logger.debug("忽略邮件内嵌资源 email=%s attachment=%s", file.name, filename)
                warnings.append(f"已忽略邮件正文内嵌资源：{filename}")
                continue
            if disposition == "attachment" or filename:
                payload = part.get_payload(decode=True) or b""
                if not isinstance(payload, bytes):
                    payload = str(payload).encode()
                attachment = InputFile(
                    name=filename or "attachment.bin",
                    content=payload,
                    media_type=part.get_content_type(),
                )
                logger.debug("解析邮件附件 email=%s attachment=%s", file.name, attachment.name)
                children.append(self._attachment_parser(attachment))
                continue
            content_type = part.get_content_type()
            if content_type == "text/plain":
                body_parts.append(str(part.get_content()))
            elif content_type == "text/html" and not body_parts:
                extractor = _HtmlTextExtractor()
                extractor.feed(str(part.get_content()))
                body_parts.append("\n".join(extractor.parts))

        body = re.sub(r"\n{3,}", "\n\n", "\n".join(body_parts)).strip()
        logger.info(
            "邮件解析完成 file=%s attachment_count=%d warning_count=%d",
            file.name,
            len(children),
            len(warnings),
        )
        location = SourceLocation(source_name=file.name)
        return ParsedDocument(
            source_name=file.name,
            source_type="EML",
            text_blocks=(TextBlock(body, location),) if body else (),
            children=tuple(children),
            metadata={
                "subject": str(message.get("subject", "")),
                "from": str(message.get("from", "")),
                "to": str(message.get("to", "")),
                "date": str(message.get("date", "")),
            },
            raw_text=body,
            warnings=tuple(warnings),
        )
