"""Application request and progress contracts."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from application.dto.documents import InputFile
from domain.billing.entities import Bill


class ProcessingStage(StrEnum):
    RECEIVED = "RECEIVED"
    PARSING = "PARSING"
    EXTRACTING = "EXTRACTING"
    NORMALIZING = "NORMALIZING"
    VALIDATING = "VALIDATING"
    MATCHING = "MATCHING"
    DECIDING = "DECIDING"
    BUILDING_OUTPUT = "BUILDING_OUTPUT"
    COMPLETED = "COMPLETED"


@dataclass(frozen=True, slots=True)
class ProcessingEvent:
    stage: ProcessingStage
    message: str


ProgressCallback = Callable[[ProcessingEvent], None]


@dataclass(frozen=True, slots=True)
class ProcessingRequest:
    source_files: tuple[InputFile, ...]
    existing_bills: tuple[Bill, ...] = ()
    accounting_entity: str | None = None
