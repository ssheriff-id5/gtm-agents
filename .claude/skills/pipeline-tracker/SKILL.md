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

## Required columns (decided): owner columns read through the Account
No owner fields on Deals. The Account is the only source of truth, and the report reads it through the
Deal's `Account_Name` lookup. These are automated CRM columns: no colour-coding, never hand-edited.
Place them after Deal Owner, in this order:

| Sheet column      | COQL field on Deals                          |
|-------------------|----------------------------------------------|
| Deal Owner        | `Owner`                                      |
| Technical Owner   | `Account_Name.Technical_Account_Owner`       |
| Partnership Owner | `Account_Name.Additional_Commercial_Owner`   |
| Sales Engineer    | `Account_Name.Sales_Engineer`                |

```sql
select Deal_Name, Stage, Closing_Date, Owner, Account_Name,
       Account_Name.Technical_Account_Owner,
       Account_Name.Additional_Commercial_Owner,
       Account_Name.Sales_Engineer
from Deals
where Closing_Date between '<today>' and '<today+90>'
  and Stage not in ('Closed won','Closed Lost','Closed won - Canceled','Closed won - Did Not Renew')
limit 200   -- page with offset if more_records = true
```
(Tested 2026-11-06, read-only. COQL rejects `not like` on Stage, so list the closed stages explicitly.)

- Write the user's **name**, not the ID. Some lookups come back with `name: null` (seen for user ids
  `162380000075776001` and `162380000016377001`, probably deactivated users). Resolve the name via the
  Zoho Users API. If it still can't be resolved, write `Unknown user (<id>)`. Never leave a value that
  exists looking blank.
- Blank on the Account → blank cell. Don't fill it from anywhere else and don't raise an Input Request
  per blank. Report the count of open deals missing each owner in the Slack thread instead.
- Values always reflect the Account **today**. Closed/historical deals show the current owner, not
  the owner at close. That's fine for a forward-looking 90-day report.

## To fill in when porting
- Test sheet ID / live sheet ID
- CRM object, filters ("next 90 days" = expected close date within today + 90?), columns
- Which columns are manual input
- Which gaps trigger an Input Request, and who gets asked (deal owner? Satiesh?)
