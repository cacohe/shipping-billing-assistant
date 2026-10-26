"""Port for the configured OCR service."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class OcrResult:
    text: str
    tables: tuple[tuple[tuple[Any, ...], ...], ...] = ()
    raw_payload: dict[str, Any] | None = None


class OcrPort(Protocol):
    def recognize(self, file_url: str) -> OcrResult: ...
