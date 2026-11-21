"""Branded laboratory report PDF (A4)."""

from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from apps.laboratory.models import FieldType, LabOrder, SampleStatus


def render_lab_report_pdf(order: LabOrder) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 18 * mm

    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, y, order.facility.name)
    y -= 6 * mm
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y, "Laboratory Report")
    y -= 8 * mm

    patient = order.patient
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, patient.full_name)
    c.setFont("Helvetica", 10)
    c.drawRightString(width - 20 * mm, y, f"Lab No: {order.lab_no}")
    y -= 5 * mm
    c.drawString(20 * mm, y, f"UHID: {patient.uhid}")
    c.drawRightString(width - 20 * mm, y, f"Gender: {patient.gender}")
    y -= 5 * mm
    if order.doctor_id:
        c.drawString(20 * mm, y, f"Consulting doctor: {order.doctor.name}")
        y -= 5 * mm
    y -= 3 * mm
    c.line(20 * mm, y, width - 20 * mm, y)
    y -= 8 * mm

    items = list(
        order.items.select_related("test", "authorized_by").prefetch_related(
            "results__field", "results__entered_by"
        )
    )
    for item in items:
        if item.status == SampleStatus.CANCELLED:
            continue
        if y < 40 * mm:
            c.showPage()
            y = height - 20 * mm
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, y, f"{item.test.code} — {item.test.name}")
        y -= 5 * mm
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, y, f"Department: {item.test.get_department_display()}  |  Status: {item.status}")
        if item.barcode:
            c.drawRightString(width - 20 * mm, y, f"Barcode: {item.barcode}")
        y -= 6 * mm

        results = [r for r in item.results.all() if r.is_current]
        if not results:
            c.setFont("Helvetica-Oblique", 9)
            c.drawString(22 * mm, y, "Results pending")
            y -= 7 * mm
            continue

        c.setFont("Helvetica-Bold", 9)
        c.drawString(22 * mm, y, "Parameter")
        c.drawString(85 * mm, y, "Result")
        c.drawString(120 * mm, y, "Flag")
        c.drawString(145 * mm, y, "Reference")
        y -= 4 * mm
        c.line(22 * mm, y, width - 20 * mm, y)
        y -= 5 * mm
        c.setFont("Helvetica", 9)
        for row in sorted(results, key=lambda r: r.field.sort_order):
            if y < 25 * mm:
                c.showPage()
                y = height - 20 * mm
                c.setFont("Helvetica", 9)
            if row.field.field_type == FieldType.SUB_HEADER:
                c.setFont("Helvetica-Bold", 9)
                c.drawString(22 * mm, y, row.field.name)
                c.setFont("Helvetica", 9)
                y -= 5 * mm
                continue
            value = row.value_text
            if row.field.unit and row.value_numeric is not None:
                value = f"{row.value_text} {row.field.unit}"
            c.drawString(22 * mm, y, row.field.name[:40])
            c.drawString(85 * mm, y, value[:28])
            c.drawString(120 * mm, y, row.flag)
            c.drawString(145 * mm, y, (row.reference_text or "")[:30])
            y -= 5 * mm
        if item.authorized_by_id:
            c.setFont("Helvetica", 8)
            c.drawString(
                22 * mm,
                y,
                f"Authorized by {item.authorized_by.get_username()} at {item.authorized_at}",
            )
            y -= 6 * mm
        y -= 4 * mm

    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 15 * mm, "Computer-generated report. Verify critical values clinically.")
    c.showPage()
    c.save()
    return buffer.getvalue()
