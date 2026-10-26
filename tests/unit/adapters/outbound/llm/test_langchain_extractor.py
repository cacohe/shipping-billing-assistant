from decimal import Decimal

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from adapters.outbound.llm.langchain_extractor import (
    ExtractionError,
    LangChainBillingExtractor,
)
from application.dto.documents import ParsedDocument, SourceLocation, TableBlock

VALID_RESPONSE = """{
  "documents": [{
    "document_info": {"reference_no": "INV-1"},
    "parties": {"issuer": "Carrier", "recipient": "Importer"},
    "charges": [{
      "raw_name": "THC", "amount": 10, "currency": "USD", "confidence": 0.9,
      "evidence": [{"source_id": "0", "source_name": "invoice.pdf", "source_text": "THC USD 10"}]
    }],
    "charge_direction": "ISSUER_CHARGES_RECIPIENT",
    "subtotal": 10,
    "tax": 1,
    "total": 11,
    "reasoning": ["invoice text"]
  }]
}"""

EMPTY_RESPONSE = """{
  "documents": [{
    "document_info": {"document_type": "PRE-ALERT"},
    "parties": {"issuer": null, "recipient": null},
    "charges": [],
    "reasoning": ["No charge table found"]
  }]
}"""

EMPTY_ENVELOPE_RESPONSE = """{"documents": []}"""

EMAIL_CHARGE_RESPONSE = """{
  "documents": [{
    "document_info": {"document_type": "PRE-ALERT"},
    "parties": {"issuer": null, "recipient": null},
    "charges": [{
      "raw_name": "H/C", "amount": 50, "currency": "USD", "confidence": 0.8,
      "evidence": [{
        "source_id": "0", "source_name": "mail.eml",
        "source_text": "SHA pay TAR：H/C $50"
      }]
    }],
    "reasoning": ["Email body contains an assigned charge and amount"]
  }]
}"""

ALTERED_CONTEXT_CHARGE_RESPONSE = """{
  "documents": [{
    "document_info": {
      "document_type": "INVENTED TYPE", "reference_no": "INVENTED-1",
      "document_date": "2026-01-01"
    },
    "parties": {"issuer": "Invented Issuer", "recipient": "Invented Recipient"},
    "charges": [{
      "raw_name": "H/C", "amount": 50, "currency": "USD", "confidence": 0.8,
      "evidence": [{
        "source_id": "0", "source_name": "mail.eml",
        "source_text": "SHA pay TAR：H/C $50"
      }]
    }],
    "subtotal": 50, "total": 50,
    "charge_direction": "ISSUER_CHARGES_RECIPIENT",
    "reasoning": ["Invented context"]
  }]
}"""


def test_extractor_repairs_invalid_output_once_and_includes_child_text() -> None:
    model = FakeListChatModel(responses=["not-json", VALID_RESPONSE])
    extractor = LangChainBillingExtractor(model)
    documents = (
        ParsedDocument(
            "mail.eml",
            "EML",
            raw_text="mail body",
            children=(ParsedDocument("invoice.pdf", "PDF", raw_text="child invoice"),),
        ),
    )

    result = extractor.extract(documents)

    assert result[0].charges[0].amount == Decimal("10")
    assert result[0].subtotal == Decimal("10")
    assert result[0].tax == Decimal("1")
    assert result[0].total == Decimal("11")
    assert result[0].raw_text == "mail body\nchild invoice"


def test_extractor_fails_after_one_repair_attempt() -> None:
    extractor = LangChainBillingExtractor(
        FakeListChatModel(responses=["not-json", "still-not-json"])
    )
    with pytest.raises(ExtractionError):
        extractor.extract((ParsedDocument("bill.txt", "TEXT", raw_text="bill"),))


def test_extractor_rechecks_empty_result_when_input_contains_amount_candidate() -> None:
    extractor = LangChainBillingExtractor(
        FakeListChatModel(responses=[EMPTY_RESPONSE, EMAIL_CHARGE_RESPONSE])
    )

    result = extractor.extract(
        (ParsedDocument("mail.eml", "EML", raw_text="SHA pay TAR：H/C $50"),)
    )

    assert result[0].charges[0].raw_name == "H/C"
    assert result[0].charges[0].amount == Decimal("50")


def test_empty_result_recheck_only_merges_charges() -> None:
    extractor = LangChainBillingExtractor(
        FakeListChatModel(responses=[EMPTY_RESPONSE, ALTERED_CONTEXT_CHARGE_RESPONSE])
    )

    result = extractor.extract(
        (ParsedDocument("mail.eml", "EML", raw_text="SHA pay TAR：H/C $50"),)
    )

    assert result[0].charges[0].amount == Decimal("50")
    assert result[0].document_info.document_type == "PRE-ALERT"
    assert result[0].document_info.reference_no is None
    assert result[0].parties.issuer is None
    assert result[0].subtotal is None
    assert result[0].total is None
    assert result[0].charge_direction is None
    assert result[0].reasoning == ("No charge table found",)


def test_empty_envelope_recheck_accepts_one_unambiguous_document() -> None:
    extractor = LangChainBillingExtractor(
        FakeListChatModel(responses=[EMPTY_ENVELOPE_RESPONSE, EMAIL_CHARGE_RESPONSE])
    )

    result = extractor.extract(
        (ParsedDocument("mail.eml", "EML", raw_text="SHA pay TAR：H/C $50"),)
    )

    assert len(result) == 1
    assert result[0].document_info.document_type == "PRE-ALERT"
    assert len(result[0].charges) == 1
    charge = result[0].charges[0]
    assert charge.raw_name == "H/C"
    assert charge.amount == Decimal("50")
    assert charge.currency == "USD"
    assert len(charge.evidence) == 1
    assert charge.evidence[0].source_id == "0"
    assert charge.evidence[0].source_name == "mail.eml"
    assert charge.evidence[0].source_text == "SHA pay TAR：H/C $50"


def test_empty_envelope_recheck_rejects_ambiguous_multiple_documents() -> None:
    reviewed = EMAIL_CHARGE_RESPONSE.replace(
        '"documents": [{',
        '"documents": [{"document_info": {}, "parties": {}, "charges": []}, {',
        1,
    )
    extractor = LangChainBillingExtractor(
        FakeListChatModel(responses=[EMPTY_ENVELOPE_RESPONSE, reviewed])
    )

    result = extractor.extract(
        (ParsedDocument("mail.eml", "EML", raw_text="SHA pay TAR：H/C $50"),)
    )

    assert result == ()


def test_empty_result_recheck_supports_iso_4217_currency_candidates() -> None:
    chf_response = EMAIL_CHARGE_RESPONSE.replace('"USD"', '"CHF"').replace("$50", "CHF 50")
    extractor = LangChainBillingExtractor(
        FakeListChatModel(responses=[EMPTY_RESPONSE, chf_response])
    )

    result = extractor.extract(
        (ParsedDocument("mail.eml", "EML", raw_text="SHA pay TAR：H/C CHF\n50"),)
    )

    assert result[0].charges[0].currency == "CHF"
    assert result[0].charges[0].amount == Decimal("50")


def test_empty_result_recheck_detects_currency_and_amount_in_adjacent_table_cells() -> None:
    chf_response = EMAIL_CHARGE_RESPONSE.replace('"USD"', '"CHF"').replace("$50", "CHF 50")
    extractor = LangChainBillingExtractor(
        FakeListChatModel(responses=[EMPTY_RESPONSE, chf_response])
    )
    document = ParsedDocument(
        "mail.eml",
        "EML",
        tables=(
            TableBlock(
                headers=("Charge", "Currency", "Amount"),
                rows=(("H/C", "CHF", 50),),
                location=SourceLocation("mail.eml", row=1),
            ),
        ),
    )

    result = extractor.extract((document,))

    assert result[0].charges[0].currency == "CHF"
    assert result[0].charges[0].amount == Decimal("50")


def test_empty_result_recheck_does_not_positionally_merge_multiple_documents() -> None:
    initial = """{
      "documents": [
        {"document_info": {"reference_no": "A"}, "parties": {}, "charges": []},
        {"document_info": {"reference_no": "B"}, "parties": {}, "charges": []}
      ]
    }"""
    reviewed = """{
      "documents": [
        {
          "document_info": {"reference_no": "B"}, "parties": {},
          "charges": [{
            "raw_name": "H/C", "amount": 50, "currency": "USD", "confidence": 0.8,
            "evidence": [{
              "source_id": "1", "source_name": "b.txt", "source_text": "H/C $50"
            }]
          }]
        },
        {"document_info": {"reference_no": "A"}, "parties": {}, "charges": []}
      ]
    }"""
    extractor = LangChainBillingExtractor(FakeListChatModel(responses=[initial, reviewed]))

    result = extractor.extract(
        (
            ParsedDocument("a.txt", "TEXT", raw_text="No charge"),
            ParsedDocument("b.txt", "TEXT", raw_text="H/C $50"),
        )
    )

    assert [document.document_info.reference_no for document in result] == ["A", "B"]
    assert all(not document.charges for document in result)


def test_extractor_keeps_empty_result_when_input_has_no_amount_candidate() -> None:
    extractor = LangChainBillingExtractor(
        FakeListChatModel(responses=[EMPTY_RESPONSE, EMAIL_CHARGE_RESPONSE])
    )

    result = extractor.extract(
        (ParsedDocument("notice.eml", "EML", raw_text="No priced charges in this notice"),)
    )

    assert result[0].charges == ()


def test_extractor_keeps_tables_and_metadata_in_validation_corpus() -> None:
    extractor = LangChainBillingExtractor(FakeListChatModel(responses=[VALID_RESPONSE]))
    documents = (
        ParsedDocument(
            "invoice.pdf",
            "PDF",
            metadata={"subject": "Invoice INV-1"},
            tables=(
                TableBlock(
                    headers=("Charge", "Amount"),
                    rows=(("THC", "USD 10"),),
                    location=SourceLocation("invoice.pdf", page=1),
                ),
            ),
        ),
    )

    result = extractor.extract(documents)

    assert "Invoice INV-1" in result[0].raw_text
    assert "Charge | Amount" in result[0].raw_text
    assert "THC | USD 10" in result[0].raw_text


def test_extractor_keeps_validation_corpus_separate_by_source_name() -> None:
    extractor = LangChainBillingExtractor(FakeListChatModel(responses=[VALID_RESPONSE]))
    documents = (
        ParsedDocument("invoice.pdf", "PDF", raw_text="THC USD 10"),
        ParsedDocument("other.pdf", "PDF", raw_text="Documentation Fee USD 20"),
    )

    result = extractor.extract(documents)

    assert [
        (item.source_id, item.source_name, item.text) for item in result[0].source_materials
    ] == [
        ("0", "invoice.pdf", "THC USD 10"),
        ("1", "other.pdf", "Documentation Fee USD 20"),
    ]
