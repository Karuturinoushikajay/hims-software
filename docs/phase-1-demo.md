# Phase 1 demo — Masters

Sign in as `facadmin` (password from `DEMO_SEED_PASSWORD`, demo default `ChangeMeDemo!2026`) and open **Masters**.

1. **Departments.** Add ENT. Adding the same name again is rejected.
2. **Doctors.** Add a specialization under General Medicine, then a doctor. Hospital share and doctor share must add up to the consultation fee. Save Monday clinic hours.
3. **Services and procedures.** Add a general service and a procedure. Shares must add up to the amount.
4. **Wards and beds.** Room types are seeded (ER, General, ICU, Step Down ICU, Special Rooms). Add a ward, a room, and a bed. Seeded General Ward A already has room 101 with two vacant beds.
5. **Tariffs.** Apply a 10% increase to procedures. Copy hospital charges onto Demo TPA (or a new corporate/TPA).
6. **Taxes.** Add a tax category with HSN/SAC. GST is still charged only after the facility GSTIN is confirmed.
7. **Discounts.** The seeded "Facility ceiling" is the strictest active rule. A role limit can be tighter, but not looser than this ceiling.
8. **Payment modes.** Turn UPI off. Collecting a due by UPI then fails until it is turned back on.
9. **Templates.** Prescription and discharge templates are seeded. Add a certificate template.
10. **Geography.** India / Telangana / Hyderabad / Ameerpet is seeded. Add a country, state, city, and area.
11. **Referrals.** City Clinic is seeded at 10% commission. Add another referral doctor.

A doctor login can open clinical screens but cannot change masters.
