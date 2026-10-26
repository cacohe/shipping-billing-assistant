"""Technical document representations shared by parsers and extractors."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """Location of a text or table fragment in an input source."""

    source_name: str
    page: int | None = None
    sheet: str | None = None
    row: int | None = None
    attachment_name: str | None = None


@dataclass(frozen=True, slots=True)
class TextBlock:
    """Text and its source location."""

    text: str
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class TableBlock:
    """A normalized table extracted from a source."""

    headers: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """Format-neutral document passed to the semantic extractor."""

    source_name: str
    source_type: str
    text_blocks: tuple[TextBlock, ...] = field(default_factory=tuple)
    tables: tuple[TableBlock, ...] = field(default_factory=tuple)
    children: tuple["ParsedDocument", ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    raw_payload: dict[str, Any] | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class InputFile:
    """One supplied file, optionally already available through an external URL."""

    name: str
    content: bytes
    media_type: str | None = None
    source_url: str | None = None
