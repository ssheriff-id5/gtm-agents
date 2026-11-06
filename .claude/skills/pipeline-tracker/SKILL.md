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

## Required columns (decided)
These are automated CRM columns: no colour-coding, never hand-edited in the sheet.
Place them after Deal Owner, in this order:

| Sheet column      | Zoho Deals field (API name) | Source of truth |
|-------------------|-----------------------------|-----------------|
| Deal Owner        | `Owner`                     | Deal            |
| Technical Owner   | `Technical_Owner`           | Account `Technical_Account_Owner` (synced, read-only on Deal) |
| Partnership Owner | `Partnership_Owner`         | Account `Additional_Commercial_Owner` (synced, read-only on Deal) |
| Sales Engineer    | `Sales_Engineer`            | Account `Sales_Engineer` (synced, read-only on Deal) |

- Write the user's **name** (`.name` of the lookup), not the ID.
- Blank in the CRM → leave the cell blank. Don't fill it from anywhere else. The sync runbook is `docs/zoho/deal-owner-sync.md`.
- If the Deal fields aren't live yet, read the same values via the Account lookup instead
  (COQL: `Account_Name.Technical_Account_Owner`, `Account_Name.Additional_Commercial_Owner`, `Account_Name.Sales_Engineer`).
  Same values, no duplication.
- Confirm the API names against Zoho before the first run (they're generated when the fields are created).

## To fill in when porting
- Test sheet ID / live sheet ID
- CRM object, filters ("next 90 days" = expected close date within today + 90?), columns
- Which columns are manual input
- Which gaps trigger an Input Request, and who gets asked (deal owner? Satiesh?)
