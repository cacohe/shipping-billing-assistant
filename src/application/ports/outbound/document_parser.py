"""Port for turning input files into format-neutral documents."""

from typing import Protocol

from application.dto.documents import InputFile, ParsedDocument


class DocumentParserPort(Protocol):
    def parse_all(self, files: tuple[InputFile, ...]) -> tuple[ParsedDocument, ...]: ...
