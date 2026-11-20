# Phase 3 demo — Billing

Sign in at http://127.0.0.1:5173 as `cashier` (password from `DEMO_SEED_PASSWORD`).

1. Open **Billing**. The amber note says GST and TDS are not applied until someone confirms them in facility settings.
2. Open a shift with opening cash `1000`.
3. Find Sita (`DHG/MR/000001`, or any registered patient) and raise a service bill of `250`, collected now `100`, mode Cash. The bill is `PARTIALLY_PAID` with due `150.00`.
4. Collect the remaining `150` by UPI. Status becomes `PAID`. Open **A4 invoice** and **Thermal receipt**.
5. Take an advance of `200` for the same patient. Raise another bill collected now `0`, then apply `200` from the advance. The receipt mode is `ADVANCE` and it is not new cash in the drawer.
6. Cancel a paid bill with a reason. You get a credit note (`DMSH/CN/...`) and a refund (`DMSH/REF/...`). The original bill number stays. Refunds above the facility threshold (seeded at `5000`) stay pending until `facadmin` authorizes them.
7. On **Consultation**, a receptionist discount above 5% is rejected. **Send discount for approval**, then sign in as `facadmin` and approve it on **Billing**. The consultation posts at the approver's limit.
8. Close the shift and compare counted cash with the expected cash. Close the day only when you are finished: new bills for today are refused until **Reopen today**.

Assumptions: GST stays zero while `gstin_confirmed` is false, even if the outpatient category is 18%. Intra-state tax splits into CGST and SGST; a different place of supply becomes IGST. Commission is a percent of hospital share after discount, and TDS (seeded at 10%) is calculated only when `tds_rate_confirmed` is true. Discount reduces hospital share first. A shift is not required to post a bill.
