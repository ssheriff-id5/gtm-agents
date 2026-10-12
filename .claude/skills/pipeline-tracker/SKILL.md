---
name: pipeline-tracker
description: Refresh the Pipeline Tracker (Next 90 Days) Google Sheet from the CRM. Owned by Rick. NOT YET PORTED (Phase 2), so don't run it against any sheet yet.
---

# Pipeline Tracker (Next 90 Days)

> **Status: NOT YET PORTED (Phase 2).** If you've been asked to run this, stop. Log `Blocked on human` via the `job-contract` skill with the summary "Pipeline Tracker skill not yet ported to the repo".

## Porting checklist (REVOPS_AI_TEAM_HANDOFF.md §9)
1. Copy the existing claude.ai skill instructions into this file.
2. Replace claude.ai connector calls with repo credentials: Google service account (`GOOGLE_SA_JSON`) via `lib/sheets_client.py`, and read-only CRM API access. Confirm which CRM the current skill pulls from.
3. Wrap it in the job contract: `finish-run` at the end, `input-request` for missing close dates or commentary.
4. Colour-code manual-input columns with `SheetsClient.mark_manual_columns()`.
5. Point it at the **test sheet** only. Run it several times and collect feedback before moving to the live sheet (Phase 5).

## To fill in when porting
- Test sheet ID / live sheet ID
- CRM object, filters ("next 90 days" = expected close date within today + 90?), columns
- Which columns are manual input
- Which gaps trigger an Input Request, and who gets asked (deal owner? Satiesh?)
