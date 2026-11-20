# Phase 2 demo — Patient and OPD

Sign in at http://127.0.0.1:5173 as `receptionist` (password from `DEMO_SEED_PASSWORD`).

1. Open **Register**. Enter a first name, gender, and mobile. Submit.
2. Confirm the MR number (`DHG/MR/...`), a registration bill of 100.00, a receipt, and validity about one year out.
3. Submit the same mobile again. The screen lists the existing patient and asks you to confirm before creating another record.
4. Open **Queue**. Choose Dr. Divya Sharma, find the patient, and issue a walk-in token. The token is 1 for that doctor today. The reminder status is `NOT_CONFIGURED` because no SMS or WhatsApp provider is set.
5. Use the header search (name, MR, mobile, or ABHA) and press Enter to open **Consultation**.
6. Save a consultation. The bill is 500.00, split 300 hospital / 200 doctor. A 5% discount is allowed for reception; 10% is rejected.
7. Save a second consultation for the same patient and doctor. The fee is waived as a free review (7 days).
8. Open **Procedures**, charge Dressing (200.00), and confirm the bill is paid.
9. Sign in as `cashier` and open `/register`. Registration is not in the cashier menu. The API returns 403.

Assumptions for this phase: registration and consultation fees are posted on the shared bill and receipt tables. Discount comes off the hospital share first. GST is not calculated. SMS is queued and not sent.
