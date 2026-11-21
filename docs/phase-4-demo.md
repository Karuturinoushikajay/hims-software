# Phase 4 demo — Clinical EMR

Sign in as `doctor` (password from `DEMO_SEED_PASSWORD`, demo default `ChangeMeDemo!2026`).

1. As receptionist, register a patient and open **Consultation**. Save vitals and collect the fee.
2. Click **Open clinical record**, or open **Clinical record** from the menu after searching for the patient.
3. Save a note with complaints, history, examination, and an ICD-10 diagnosis (for example J06.9).
4. Record an allergy to Amoxicillin, then try to prescribe Amoxicillin — the save is blocked until you acknowledge the allergy alert.
5. Prescribe Paracetamol and Ibuprofen together — the interaction alert appears until acknowledged.
6. Print the prescription PDF and the clinical summary PDF.
7. Place a lab order (Complete blood count). Schedule a follow-up date. Upload a small attachment.
8. Confirm the left timeline shows the visit, note, orders, follow-up, and allergy banner.

Cashier can open the timeline (read) but cannot save clinical notes.
Lab fulfillment is Phase 6 (`/laboratory`); radiology fulfillment is Phase 7 (`/radiology`). Phase 4 only places the clinical order.
