"""Branded radiology report PDF (A4)."""

from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from apps.radiology.models import RadiologyOrder, StudyStatus


def _wrap(c, text: str, x: float, y: float, max_width: float = 170 * mm) -> float:
    c.setFont("Helvetica", 10)
    for raw in (text or "").splitlines() or [""]:
        line = raw.strip() or "—"
        while line:
            chunk = line
            while c.stringWidth(chunk, "Helvetica", 10) > max_width and len(chunk) > 1:
                chunk = chunk[:-1]
            c.drawString(x, y, chunk)
            y -= 5 * mm
            line = line[len(chunk) :].lstrip()
            if y < 25 * mm:
                c.showPage()
                y = A4[1] - 20 * mm
                c.setFont("Helvetica", 10)
    return y


def render_radiology_report_pdf(order: RadiologyOrder) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 18 * mm

    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, y, order.facility.name)
    y -= 6 * mm
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y, "Radiology Report")
    y -= 8 * mm

    patient = order.patient
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, patient.full_name)
    c.setFont("Helvetica", 10)
    c.drawRightString(width - 20 * mm, y, f"Rad No: {order.rad_no}")
    y -= 5 * mm
    c.drawString(20 * mm, y, f"UHID: {patient.uhid}")
    c.drawRightString(width - 20 * mm, y, f"Gender: {patient.gender}")
    y -= 5 * mm
    if order.doctor_id:
        c.drawString(20 * mm, y, f"Referring doctor: {order.doctor.name}")
        y -= 5 * mm
    y -= 3 * mm
    c.line(20 * mm, y, width - 20 * mm, y)
    y -= 8 * mm

    for item in order.items.select_related("test", "authorized_by").prefetch_related("reports"):
        if item.status == StudyStatus.CANCELLED:
            continue
        if y < 45 * mm:
            c.showPage()
            y = height - 20 * mm
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, y, f"{item.test.code} — {item.test.name}")
        y -= 5 * mm
        c.setFont("Helvetica", 9)
        c.drawString(
            20 * mm,
            y,
            f"Department: {item.test.get_department_display()}  |  Status: {item.status}",
        )
        y -= 6 * mm
        report = next((r for r in item.reports.all() if r.is_current), None)
        if not report:
            c.setFont("Helvetica-Oblique", 9)
            c.drawString(22 * mm, y, "Report pending")
            y -= 8 * mm
            continue
        c.setFont("Helvetica-Bold", 10)
        c.drawString(22 * mm, y, "Findings")
        y -= 5 * mm
        y = _wrap(c, report.findings, 22 * mm, y)
        y -= 2 * mm
        c.setFont("Helvetica-Bold", 10)
        c.drawString(22 * mm, y, "Impression")
        y -= 5 * mm
        y = _wrap(c, report.impression, 22 * mm, y)
        if item.authorized_by_id:
            c.setFont("Helvetica", 8)
            c.drawString(
                22 * mm,
                y,
                f"Authorized by {item.authorized_by.get_username()} at {item.authorized_at}",
            )
            y -= 5 * mm
        if item.pacs_url:
            c.setFont("Helvetica", 8)
            c.drawString(22 * mm, y, f"PACS: {item.pacs_url[:90]}")
            y -= 5 * mm
        y -= 4 * mm

    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 15 * mm, "Computer-generated radiology report.")
    c.showPage()
    c.save()
    return buffer.getvalue()
