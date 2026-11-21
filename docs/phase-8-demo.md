# Phase 8 demo — In-patient (IPD)

Sign in as `receptionist` (password from `DEMO_SEED_PASSWORD`, demo default `ChangeMeDemo!2026`) and open **In-patient**.

1. Register a patient if needed. On **Admit**, search the patient, pick a doctor and vacant bed, set an advance, then admit. First-day bed + nursing charges post automatically; the bed shows occupied on **Board**.
2. Transfer bed (API/worklist) or open **Care** as `nurse`: add a nursing note with vitals, record a MAR dose. As `doctor`, add a doctor order.
3. **Discharge.** Save a discharge summary (diagnosis + condition), then **Settle & discharge**. Advances apply to open IP dues; the bed returns to vacant. Open the discharge PDF.
4. Issue a **Fitness** (or other) medical certificate and open its PDF.
5. Cancel discharge with a reason to reopen the admission on the same bed if still vacant.

Demo user `nurse` is seeded for ward care. Automatic daily room posting also runs via `POST /api/v1/ipd/daily-charges`.
