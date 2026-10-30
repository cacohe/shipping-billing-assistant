import pytest

from application.errors import UserInputError
from application.presentation import (
    MAX_FILE_COUNT,
    MAX_FILE_SIZE_BYTES,
    MAX_TOTAL_SIZE_BYTES,
    build_result_rows,
    summarize_results,
    validate_uploads,
)


class Upload:
    def __init__(self, name: str, content: bytes) -> None:
        self.name = name
        self._content = content

    def getvalue(self) -> bytes:
        return self._content


def test_validate_uploads_accepts_exact_limits() -> None:
    count_limited = [Upload(f"bill-{index}.pdf", b"x") for index in range(MAX_FILE_COUNT)]
    size_limited = Upload("large.pdf", b"x" * MAX_FILE_SIZE_BYTES)
    total_limited = [
        Upload("a.pdf", b"x" * MAX_FILE_SIZE_BYTES),
        Upload("b.pdf", b"x" * MAX_FILE_SIZE_BYTES),
        Upload("c.pdf", b"x" * (MAX_TOTAL_SIZE_BYTES - 2 * MAX_FILE_SIZE_BYTES)),
    ]

    validate_uploads(count_limited)
    validate_uploads([size_limited])
    validate_uploads(total_limited)


def test_validate_uploads_rejects_too_many_files() -> None:
    uploads = [Upload(f"bill-{index}.pdf", b"x") for index in range(MAX_FILE_COUNT + 1)]

    with pytest.raises(UserInputError, match="最多上传 8 个"):
        validate_uploads(uploads)


def test_validate_uploads_rejects_oversized_file() -> None:
    upload = Upload("large.pdf", b"x" * (MAX_FILE_SIZE_BYTES + 1))

    with pytest.raises(UserInputError, match=r"large\.pdf.*10 MB"):
        validate_uploads([upload])


def test_validate_uploads_rejects_oversized_request() -> None:
    uploads = [
        Upload("a.pdf", b"x" * MAX_FILE_SIZE_BYTES),
        Upload("b.pdf", b"x" * MAX_FILE_SIZE_BYTES),
        Upload("c.pdf", b"x" * (MAX_TOTAL_SIZE_BYTES - 2 * MAX_FILE_SIZE_BYTES + 1)),
    ]

    with pytest.raises(UserInputError, match="合计.*25 MB"):
        validate_uploads(uploads)


def test_summarize_results_handles_decisions_and_empty_output() -> None:
    output = [
        {
            "operation": "CREATE",
            "charge_details": {"currency": "USD"},
        },
        {
            "operation": "PENDING_REVIEW",
            "charge_details": {"currency": "CNY"},
        },
        {
            "operation": "UPDATE",
            "charge_details": {"currency": "USD"},
        },
    ]

    summary = summarize_results(output)
    empty = summarize_results([])

    assert summary.total_charges == 3
    assert summary.automatic_decisions == 2
    assert summary.pending_review == 1
    assert summary.currencies == ("CNY", "USD")
    assert empty.total_charges == 0
    assert empty.automatic_decisions == 0
    assert empty.pending_review == 0
    assert empty.currencies == ()


def test_build_result_rows_formats_amounts_and_missing_values() -> None:
    output = [
        {
            "operation": "CREATE",
            "document_info": {"reference_no": "INV-1"},
            "charge_details": {
                "charge_item": "Ocean Freight",
                "amount": 120,
                "currency": "USD",
                "payment_term": "CC",
            },
            "financial_attributes": {"posting_type": "AP"},
        },
        {
            "operation": "PENDING_REVIEW",
            "document_info": {},
            "charge_details": {
                "charge_item": "Handling",
                "amount": None,
                "currency": None,
                "payment_term": None,
            },
            "financial_attributes": {"posting_type": None},
        },
    ]

    rows = build_result_rows(output)

    assert rows[0] == {
        "决策": "CREATE",
        "单据号": "INV-1",
        "费用项": "Ocean Freight",
        "金额": "USD 120.00",
        "付款方式": "CC",
        "记账方向": "AP",
    }
    assert rows[1] == {
        "决策": "PENDING_REVIEW",
        "单据号": "—",
        "费用项": "Handling",
        "金额": "—",
        "付款方式": "—",
        "记账方向": "—",
    }
