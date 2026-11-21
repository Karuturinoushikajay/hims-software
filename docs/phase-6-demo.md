# Phase 6 demo — Laboratory (LIS)

Sign in as `labtech` (password from `DEMO_SEED_PASSWORD`, demo default `ChangeMeDemo!2026`) and open **Laboratory**.

1. As receptionist, register a patient and copy the patient UUID.
2. **Register.** Choose Complete blood count (CBC) or the Hemogram package. A lab number and barcodes are assigned and a bill is posted.
3. **Worklist.** Filter Hematology if needed. Select the row → **Collect**, then **Receive**.
4. **Results.** Enter Hemoglobin `6.5` and WBC `7.0` for CBC — critical flag appears. Reagent CBC Diluent decreases by 2 mL.
5. **Verify** as labtech. Sign in as `pathologist`, **Authorize**, then **Dispatch**. Open the PDF report link.
6. Register a second CBC for the same patient with Hemoglobin `10.0` after a prior normal result — delta check flags the swing.
7. **Reagents.** Dump stock for breakage/loss. **Alerts** lists critical items.

Doctor accounts can view reports but cannot register lab orders. Analyzer / QC charts are deferred.
