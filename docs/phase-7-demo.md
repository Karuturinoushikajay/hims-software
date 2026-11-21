# Phase 7 demo — Radiology

Sign in as `radtech` (password from `DEMO_SEED_PASSWORD`, demo default `ChangeMeDemo!2026`) and open **Radiology**.

1. As receptionist, register a patient. On Radiology **Register**, search the patient and book Chest X-ray PA (or Ultrasound abdomen / CT Brain / MRI Knee).
2. **Schedule.** Select the new item, set a date/time and slot, then Schedule. It appears on today’s board.
3. **Worklist.** Start the study, optionally paste a PACS URL, then **Complete acquisition**. X-ray film / USG gel stock decreases when linked.
4. Sign in as `radiologist`. Open **Report**, apply the CXR or USG template, edit findings/impression, **Save report**.
5. **Authorize**, then **Dispatch**. Open the PDF report link.
6. Re-save a report after authorization to amend (version increments; status returns to Reported for re-authorize).
7. **Consumables.** Dump stock for breakage/loss.

Doctor accounts can view reports but cannot register radiology orders. DICOM/PACS deep integration stays deferred; only a link-out URL is stored.
