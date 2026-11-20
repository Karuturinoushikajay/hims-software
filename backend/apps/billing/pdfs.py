"""A4 invoice and 80mm thermal receipt. Amounts come from the posted bill."""

from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def render_bill_pdf(bill, layout: str, document: str) -> bytes:
    buffer = BytesIO()
    thermal = layout == "thermal"
    page = (80 * mm, 220 * mm) if thermal else A4
    pdf = canvas.Canvas(buffer, pagesize=page)
    width, height = page
    y = height - (8 * mm if thermal else 20 * mm)
    left = 4 * mm if thermal else 18 * mm
    size = 8 if thermal else 11

    def line(text, step=12, bold=False):
        nonlocal y
        pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        pdf.drawString(left, y, str(text)[: (42 if thermal else 90)])
        y -= step

    facility = bill.facility
    settings_row = facility.settings
    line(settings_row.letterhead_text or facility.name, bold=True)
    if settings_row.gstin and settings_row.gstin_confirmed:
        line(f"GSTIN {settings_row.gstin}")
    line(facility.city)
    line("")
    title = "RECEIPT" if document == "receipt" else "TAX INVOICE" if bill.gst_applied else "BILL"
    line(title, bold=True)
    line(f"No {bill.bill_no}")
    line(f"{bill.patient.full_name}  {bill.patient.uhid}")
    line("")
    if document != "receipt":
        for item in bill.lines.all():
            line(f"{item.description}")
            line(f"  {item.amount}")
        line(f"Gross {bill.gross_amount}")
        if bill.discount_amount:
            line(f"Discount {bill.discount_amount}")
        if bill.gst_applied:
            if bill.igst_amount:
                line(f"IGST {bill.igst_amount}")
            else:
                line(f"CGST {bill.cgst_amount}")
                line(f"SGST {bill.sgst_amount}")
        line(f"Net {bill.net_amount}", bold=True)
        line("")
    for payment in bill.payments.select_related("receipt"):
        line(f"{payment.receipt.receipt_no} {payment.mode} {payment.amount}")
    for refund in bill.refunds.filter(status="POSTED"):
        line(f"{refund.refund_no or 'Refund'} {refund.amount}")
    line(f"Paid {bill.paid_amount}")
    line(f"Due {bill.due_amount}", bold=True)
    pdf.save()
    return buffer.getvalue()
