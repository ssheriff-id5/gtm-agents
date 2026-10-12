---
name: manager-review
description: Abby's daily manager review. Checks the Work Log against expected runs, chases and escalates Input Requests, marks rows reviewed and posts the daily digest to Slack. Use only when running as Abby.
---

# Manager review (Abby, daily)

> **Status: DRAFT (Phase 3).** The steps below are agreed. The `lib.cli` commands for querying the Work Log and Input Requests are not wired up yet. `lib/notion_client.py` already has `query_work_log()`, `query_input_requests()`, `update_work_log(reviewed=...)` and `update_input_request()`. Phase 3 adds CLI commands on top of them and a deliberate missed-run test.

## Steps
1. **Expected vs actual.** For each employee in `config/employees.yaml` with a schedule that should have fired today, check for today's Work Log row. Missing → flag. `Failed` or `Partial` → flag.
2. **Open Input Requests.** For each `Open` request, read the replies in its Slack DM. If the answer is clear, copy it verbatim into `Answer` and set `Answered`. If it's ambiguous, leave it `Open` and post a follow-up in the same thread.
3. **Overdue.** If `Due` has passed with no answer, set `Overdue` and send one nudge. If the request is already `Overdue` and still unanswered, set `Escalated` and include it in "Needs a human" with the Human Owner tagged.
4. **Mark reviewed.** Tick "Reviewed by Abby" on every row processed.
5. **Digest.** Post to the team channel as Abby:
   ```
   📋 RevOps AI Team — daily digest <date>
   *Ran:* ✅ Rick · Pipeline Tracker <link> ...
   *Blocked:* ⏳ ...
   *Needs a human:* @Satiesh — ...
   ```
   Keep each section short, and link every item. If everything is fine, say so in one line.
6. **Log your own run** with `finish-run --employee abby --task "Daily review"`.
