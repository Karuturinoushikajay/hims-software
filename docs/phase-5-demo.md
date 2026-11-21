# Phase 5 demo — Pharmacy

Sign in as `pharmacist` (password from `DEMO_SEED_PASSWORD`, demo default `ChangeMeDemo!2026`) and open **Pharmacy**.

1. **Stock.** Seeded drugs include Paracetamol, Ibuprofen, Amoxicillin, Omeprazole, and Tramadol (H1). Add another drug if you want.
2. **Purchase.** MedSupply India is seeded. Create a purchase order for Paracetamol (100), then receive a GRN with two batches: one expiring sooner and one later.
3. **Dispense.** Sell 10 tablets to a registered patient (paste the patient UUID from registration/consult). The earlier-expiry batch is used first (FEFO). A bill is posted when a patient is linked.
4. Sell Tramadol — it appears on the controlled-drug register under **Alerts**.
5. Try to sell more than on hand — the API returns `insufficient_stock`.
6. **Adjust.** Dump damaged stock from a batch.
7. **Alerts.** Low-stock rows appear when on-hand is below reorder level. Near-expiry uses a 30-day window.

Doctor accounts cannot dispense. IP pharmacy issue (`kind: IP_ISSUE`) posts to the patient bill with due amount and no immediate collection.
