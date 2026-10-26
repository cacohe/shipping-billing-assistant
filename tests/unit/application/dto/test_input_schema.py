from application.dto.input_schema import ExistingBillInput
from domain.billing.enums import PostingType


def test_existing_bill_json_maps_to_domain() -> None:
    bill = ExistingBillInput.model_validate(
        {
            "bill_id": "B1",
            "document_info": {"reference_no": "INV-1"},
            "transaction_party": {"issuer": "Carrier", "recipient": "Importer"},
            "charge_details": {"raw_charge_item": "THC", "amount": 10, "currency": "usd"},
            "financial_attributes": {"accounting_entity": "Importer", "posting_type": "AP"},
        }
    ).to_domain()
    assert bill.charge.canonical_name == "Terminal Handling Charge"
    assert bill.charge.currency == "USD"
    assert bill.posting_type == PostingType.AP
