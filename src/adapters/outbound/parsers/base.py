"""Shared parser contracts and errors."""

from typing import Protocol

from application.dto.documents import InputFile, ParsedDocument
from application.errors import UserInputError


class DocumentParseError(UserInputError):
    """Raised when a supplied document cannot be parsed safely."""


class FormatParser(Protocol):
    def supports(self, file: InputFile) -> bool: ...

    def parse(self, file: InputFile) -> ParsedDocument: ...
