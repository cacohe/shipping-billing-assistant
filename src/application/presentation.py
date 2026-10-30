"""Pure presentation helpers shared by the demo UI and its tests."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from application.errors import UserInputError

MAX_FILE_COUNT = 8
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_SIZE_BYTES = 25 * 1024 * 1024


class UploadedFile(Protocol):
    name: str

    def getvalue(self) -> bytes: ...


@dataclass(frozen=True, slots=True)
class ResultSummary:
    total_charges: int
    automatic_decisions: int
    pending_review: int
    currencies: tuple[str, ...]


def validate_uploads(files: Sequence[UploadedFile]) -> None:
    """Reject requests that exceed the demo's resource limits."""

    if len(files) > MAX_FILE_COUNT:
        raise UserInputError(f"一次最多上传 {MAX_FILE_COUNT} 个文件。")
    total_size = 0
    for file in files:
        size = len(file.getvalue())
        if size > MAX_FILE_SIZE_BYTES:
            raise UserInputError(f"{file.name} 超过单文件 10 MB 的限制。")
        total_size += size
    if total_size > MAX_TOTAL_SIZE_BYTES:
        raise UserInputError("上传文件合计超过 25 MB 的限制。")


def summarize_results(output: list[dict[str, Any]]) -> ResultSummary:
    pending = sum(item.get("operation") == "PENDING_REVIEW" for item in output)
    currencies = sorted(
        {
            str(item.get("charge_details", {}).get("currency"))
            for item in output
            if item.get("charge_details", {}).get("currency")
        }
    )
    return ResultSummary(
        total_charges=len(output),
        automatic_decisions=len(output) - pending,
        pending_review=pending,
        currencies=tuple(currencies),
    )


def build_result_rows(output: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Flatten the stable JSON contract into rows suitable for display."""

    rows: list[dict[str, str]] = []
    for item in output:
        document = item.get("document_info", {})
        charge = item.get("charge_details", {})
        financial = item.get("financial_attributes", {})
        amount = charge.get("amount")
        currency = charge.get("currency")
        formatted_amount = "—"
        if amount is not None:
            number = f"{float(amount):,.2f}"
            formatted_amount = f"{currency} {number}" if currency else number
        rows.append(
            {
                "决策": str(item.get("operation") or "—"),
                "单据号": str(document.get("reference_no") or "—"),
                "费用项": str(charge.get("charge_item") or "—"),
                "金额": formatted_amount,
                "付款方式": str(charge.get("payment_term") or "—"),
                "记账方向": str(financial.get("posting_type") or "—"),
            }
        )
    return rows
