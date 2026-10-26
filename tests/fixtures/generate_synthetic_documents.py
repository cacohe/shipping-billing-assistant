"""Regenerate the repository's synthetic, public-safe document fixtures."""

from __future__ import annotations

from email.message import EmailMessage
from email.policy import SMTP
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = Path(__file__).with_name("documents")
PAGE_SIZE = (1240, 1754)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default(size=size)


def _document_image(title: str, sections: list[tuple[str, list[str]]]) -> Image.Image:
    image = Image.new("RGB", PAGE_SIZE, "white")
    draw = ImageDraw.Draw(image)
    navy = "#17324d"
    muted = "#526273"

    draw.rectangle((0, 0, PAGE_SIZE[0], 150), fill=navy)
    draw.text((70, 42), title, font=_font(48), fill="white")
    draw.text(
        (70, 112),
        "SYNTHETIC DEMO DOCUMENT - NO REAL CUSTOMER DATA",
        font=_font(20),
        fill="#d7e4ef",
    )

    y = 205
    for heading, lines in sections:
        draw.text((70, y), heading, font=_font(29), fill=navy)
        y += 48
        draw.line((70, y, 1170, y), fill="#ccd6df", width=2)
        y += 18
        for line in lines:
            draw.text((85, y), line, font=_font(25), fill="#15202b")
            y += 41
        y += 32

    draw.line((70, 1660, 1170, 1660), fill="#ccd6df", width=2)
    draw.text(
        (70, 1680),
        "Generated for automated tests and public demonstration only.",
        font=_font(19),
        fill=muted,
    )
    return image


def _save_pdf(path: Path, title: str, sections: list[tuple[str, list[str]]]) -> bytes:
    image = _document_image(title, sections)
    image.save(
        path,
        "PDF",
        resolution=150.0,
        title=title,
        author="Synthetic Fixture Generator",
        creationDate="D:20261026000000Z",
        modDate="D:20261026000000Z",
    )
    return path.read_bytes()


def _save_png(path: Path, title: str, sections: list[tuple[str, list[str]]]) -> None:
    image = _document_image(title, sections)
    image.save(path, "PNG", optimize=True)


def _inline_logo() -> bytes:
    image = Image.new("RGB", (120, 48), "#17324d")
    draw = ImageDraw.Draw(image)
    draw.text((12, 11), "DEMO", font=_font(22), fill="white")
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def generate() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    _save_png(
        OUTPUT_DIR / "synthetic-invoice.png",
        "INVOICE",
        [
            (
                "Document",
                [
                    "Invoice No: INV-DEMO-1001",
                    "Invoice Date: 2026-10-26",
                    "Payment Term: COLLECT",
                ],
            ),
            (
                "Parties",
                [
                    "Issuer: Harborline Carrier Demo Co.",
                    "Recipient: Northstar Logistics Demo Ltd.",
                    "Contact: billing@northstar.example.test",
                ],
            ),
            (
                "Shipment",
                [
                    "B/L No: MBL-DEMO-20261026",
                    "Container No: DEMU1234567",
                    "Route: Shanghai -> Los Angeles",
                ],
            ),
            (
                "Charges",
                [
                    "Documentation Fee     1 x USD 35.00     USD 35.00",
                    "Terminal Handling     1 x USD 180.00    USD 180.00",
                    "TOTAL                                      USD 215.00",
                ],
            ),
        ],
    )

    _save_pdf(
        OUTPUT_DIR / "synthetic-arrival-notice.pdf",
        "ARRIVAL NOTICE",
        [
            (
                "Document",
                [
                    "Notice No: AN-DEMO-2001",
                    "Notice Date: 2026-10-26",
                    "Freight Status: PREPAID",
                ],
            ),
            (
                "Parties",
                [
                    "Carrier: Harborline Carrier Demo Co.",
                    "Consignee: Northstar Logistics Demo Ltd.",
                    "Email: operations@northstar.example.test",
                ],
            ),
            (
                "Shipment",
                [
                    "Master B/L: MBL-DEMO-20261026",
                    "Container: DEMU1234567 / 1 x 40HQ",
                    "ETA: 2026-10-30",
                ],
            ),
            ("Charges", ["On-carriage charge                    USD 245.00"]),
        ],
    )

    _save_pdf(
        OUTPUT_DIR / "synthetic-debit-note.pdf",
        "DEBIT NOTE",
        [
            (
                "Document",
                [
                    "Debit Note No: DN-DEMO-3001",
                    "Document Date: 2026-10-26",
                    "Currency: USD",
                ],
            ),
            (
                "Parties",
                [
                    "Issuer: Northstar Logistics Demo Ltd.",
                    "Recipient: Bluewater Imports Demo LLC",
                    "Email: accounts@bluewater.example.test",
                ],
            ),
            (
                "Shipment",
                [
                    "House B/L: HBL-DEMO-20261026",
                    "Container: DEMU1234567",
                ],
            ),
            (
                "Charges",
                [
                    "Handling Charge       C      USD 65.00",
                    "Ocean Freight        C      USD 1,310.40",
                    "Documentation Fee    C      USD 35.00",
                    "TOTAL                        USD 1,410.40",
                ],
            ),
        ],
    )

    mbl = _save_pdf(
        OUTPUT_DIR / "_synthetic-mbl-attachment.pdf",
        "MASTER BILL OF LADING",
        [
            ("Shipment", ["Master B/L: MBL-DEMO-20261026", "Container: DEMU1234567"]),
            ("Terms", ["FREIGHT PREPAID", "No priced charge is stated on this attachment."]),
        ],
    )
    hbl = _save_pdf(
        OUTPUT_DIR / "_synthetic-hbl-attachment.pdf",
        "HOUSE BILL OF LADING",
        [
            ("Shipment", ["House B/L: HBL-DEMO-20261026", "Container: DEMU1234567"]),
            ("Terms", ["FREIGHT PREPAID", "No priced charge is stated on this attachment."]),
        ],
    )

    message = EmailMessage()
    message["From"] = "operations@seabridge.example.test"
    message["To"] = "billing@northstar.example.test"
    message["Date"] = "Mon, 26 Oct 2026 09:30:00 +0800"
    message["Subject"] = "DEMO-PREALERT-20261026 / HBL-DEMO-20261026 / DEMU1234567"
    message.set_content(
        "This is a synthetic pre-alert for automated tests.\n\n"
        "House B/L: HBL-DEMO-20261026\n"
        "Container: DEMU1234567\n"
        "Handling charge: H/C USD 50.00\n"
        "ETA: 2026-10-30\n"
    )
    message.add_related(
        _inline_logo(),
        maintype="image",
        subtype="png",
        cid="synthetic-logo",
        filename="synthetic-logo.png",
        disposition="inline",
    )
    message.add_attachment(
        mbl,
        maintype="application",
        subtype="pdf",
        filename="DEMO-MBL-20261026.pdf",
    )
    message.add_attachment(
        hbl,
        maintype="application",
        subtype="pdf",
        filename="DEMO-HBL-20261026.pdf",
    )
    for index, part in enumerate(message.walk()):
        if part.is_multipart():
            part.set_boundary(f"===============synthetic-boundary-{index}==")
    (OUTPUT_DIR / "synthetic-pre-alert.eml").write_bytes(message.as_bytes(policy=SMTP))

    (OUTPUT_DIR / "_synthetic-mbl-attachment.pdf").unlink()
    (OUTPUT_DIR / "_synthetic-hbl-attachment.pdf").unlink()


if __name__ == "__main__":
    generate()
