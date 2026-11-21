"""IPD discharge summary and medical certificate PDFs."""

from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from apps.ipd.models import IpAdmission, MedicalCertificate


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


def render_discharge_summary_pdf(admission: IpAdmission) -> bytes:
    summary = admission.discharge_summary
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 18 * mm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, y, admission.facility.name)
    y -= 6 * mm
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y, "Discharge Summary")
    y -= 8 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, admission.patient.full_name)
    c.setFont("Helvetica", 10)
    c.drawRightString(width - 20 * mm, y, f"IP No: {admission.ip_no}")
    y -= 5 * mm
    c.drawString(20 * mm, y, f"UHID: {admission.patient.uhid}")
    c.drawRightString(width - 20 * mm, y, f"Doctor: {admission.doctor.name}")
    y -= 5 * mm
    c.drawString(20 * mm, y, f"Admitted: {admission.admitted_at}")
    if admission.discharged_at:
        c.drawRightString(width - 20 * mm, y, f"Discharged: {admission.discharged_at}")
    y -= 8 * mm
    for label, value in (
        ("Condition on admission", summary.condition_on_admission),
        ("Chief complaints", summary.chief_complaints),
        ("Diagnosis", summary.diagnosis),
        ("ICD", summary.icd_code),
        ("Surgery", summary.surgery),
        ("Investigations", summary.investigations),
        ("Treatment given", summary.treatment_given),
        ("Condition on discharge", summary.condition_on_discharge),
        ("Treatment advised", summary.treatment_advised),
    ):
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, y, label)
        y -= 5 * mm
        y = _wrap(c, value, 22 * mm, y)
        y -= 3 * mm
    if summary.next_visit_on:
        c.setFont("Helvetica", 10)
        c.drawString(20 * mm, y, f"Next visit: {summary.next_visit_on.isoformat()}")
    c.showPage()
    c.save()
    return buffer.getvalue()


def render_certificate_pdf(cert: MedicalCertificate) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 20 * mm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, y, cert.facility.name)
    y -= 6 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, f"Medical Certificate — {cert.get_kind_display()}")
    y -= 8 * mm
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y, f"Certificate No: {cert.cert_no}")
    y -= 5 * mm
    c.drawString(20 * mm, y, f"Patient: {cert.patient.full_name} ({cert.patient.uhid})")
    y -= 5 * mm
    if cert.admission_id:
        c.drawString(20 * mm, y, f"IP No: {cert.admission.ip_no}")
        y -= 5 * mm
    if cert.disease_name:
        c.drawString(20 * mm, y, f"Disease / condition: {cert.disease_name}")
        y -= 5 * mm
    if cert.occupation:
        c.drawString(20 * mm, y, f"Occupation: {cert.occupation}")
        y -= 5 * mm
    if cert.fit_on:
        c.drawString(20 * mm, y, f"Fit from: {cert.fit_on.isoformat()}")
        y -= 5 * mm
    if cert.rest_from or cert.rest_to:
        c.drawString(
            20 * mm,
            y,
            f"Rest advice: {cert.rest_from or '—'} to {cert.rest_to or '—'}",
        )
        y -= 5 * mm
    if cert.birth_on or cert.birth_details:
        c.drawString(20 * mm, y, f"Birth: {cert.birth_on or ''} {cert.birth_details}")
        y -= 5 * mm
    if cert.death_on or cert.death_time:
        c.drawString(20 * mm, y, f"Death: {cert.death_on or ''} {cert.death_time}")
        y -= 5 * mm
    y -= 3 * mm
    y = _wrap(c, cert.body or "This is to certify the above particulars.", 20 * mm, y)
    y -= 10 * mm
    c.drawString(20 * mm, y, f"Issued by: {cert.issued_by.get_username()} on {cert.issued_at}")
    c.showPage()
    c.save()
    return buffer.getvalue()
