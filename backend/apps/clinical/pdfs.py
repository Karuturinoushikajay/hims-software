"""Prescription and clinical summary PDFs (A4)."""

from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from apps.clinical.models import ClinicalNote, Prescription
from apps.clinical.services import note_payload, prescription_payload


def _header(c, facility, title: str, y: float) -> float:
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, y, facility.name)
    y -= 6 * mm
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y, title)
    return y - 8 * mm


def _lines(c, text: str, x: float, y: float, max_width: float = 170 * mm) -> float:
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
            if y < 20 * mm:
                c.showPage()
                y = A4[1] - 20 * mm
                c.setFont("Helvetica", 10)
    return y


def render_prescription_pdf(rx: Prescription) -> bytes:
    payload = prescription_payload(rx)
    visit = rx.visit
    patient = visit.patient
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    y = A4[1] - 20 * mm
    y = _header(c, rx.facility, "Prescription", y)
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y, f"Patient: {patient.full_name}  MR: {patient.uhid}")
    y -= 5 * mm
    c.drawString(20 * mm, y, f"Visit: {visit.visit_no}  Doctor: {rx.doctor.name}")
    y -= 8 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "Rx")
    y -= 6 * mm
    for index, item in enumerate(payload["items"], start=1):
        line = f"{index}. {item['name']}"
        if item["dose"]:
            line += f" — {item['dose']}"
        if item["frequency"]:
            line += f", {item['frequency']}"
        if item["duration_days"]:
            line += f" for {item['duration_days']} day(s)"
        y = _lines(c, line, 20 * mm, y)
        if item["instructions"]:
            y = _lines(c, f"   {item['instructions']}", 20 * mm, y)
    if payload["notes"]:
        y -= 3 * mm
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, y, "Advice")
        y -= 5 * mm
        y = _lines(c, payload["notes"], 20 * mm, y)
    alerts = payload["allergy_alerts"] + payload["interaction_alerts"]
    if alerts:
        y -= 3 * mm
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, y, "Alerts acknowledged")
        y -= 5 * mm
        for alert in alerts:
            y = _lines(c, f"- {alert.get('message', '')}", 20 * mm, y)
    c.showPage()
    c.save()
    return buffer.getvalue()


def render_clinical_summary_pdf(note: ClinicalNote) -> bytes:
    payload = note_payload(note)
    visit = note.visit
    patient = visit.patient
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    y = A4[1] - 20 * mm
    y = _header(c, note.facility, "Clinical summary", y)
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y, f"Patient: {patient.full_name}  MR: {patient.uhid}")
    y -= 5 * mm
    c.drawString(20 * mm, y, f"Visit: {visit.visit_no}  Doctor: {note.doctor.name}")
    y -= 8 * mm
    for label, value in (
        ("Complaints", payload["complaints"]),
        ("History", payload["history"]),
        ("Examination", payload["examination"]),
        ("Advice", payload["advice"]),
    ):
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, y, label)
        y -= 5 * mm
        y = _lines(c, value or "—", 20 * mm, y)
        y -= 2 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, "Diagnosis")
    y -= 5 * mm
    if payload["diagnoses"]:
        for d in payload["diagnoses"]:
            label = d["name"]
            if d["icd_code"]:
                label = f"{d['icd_code']} — {label}"
            if d["is_primary"]:
                label += " (primary)"
            y = _lines(c, label, 20 * mm, y)
    else:
        y = _lines(c, "—", 20 * mm, y)
    c.showPage()
    c.save()
    return buffer.getvalue()
