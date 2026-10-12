---
name: job-contract
description: The mandatory run sequence for every RevOps AI employee. Covers reading your job, logging the run to the Notion Work Log, posting to Slack as yourself, and raising Input Requests when a human is needed. Use at the start and end of every task run, and whenever human input is needed.
---

# Job contract

Every run, every employee, same steps. This consistency lets Abby manage anyone without knowing the details of their job.

All commands are run from the repo root. They are dry-run unless `REVOPS_MODE=live`. Use your own employee key (`rick`, `stevey`, `abby`).

## 1. Read your job
```bash
python -m lib.cli whoami --employee <you>
```
Check that the task you're about to run is in your responsibilities. If it isn't, stop and log `Blocked on human` (step 4) explaining that the task needs assigning through Task Intake.

Also check for answered Input Requests you raised earlier. Consume them in this run (write the value, flagged as human-provided) and then mark them `Closed`. *(Lookup command arrives with Phase 4.)*

## 2. Do the work
Run the task's skill (for example `pipeline-tracker`). As you go, keep track of:
- counts worth reporting (rows written, deals flagged)
- anything you couldn't resolve without a human
- any errors

## 3. Write the output
Put the output where its audience already works (the Sheet or Doc named in the task skill). Apply the sourcing-integrity rules in `CLAUDE.md`. Manual and human-provided columns are colour-coded. Pending values are marked "awaiting human input", never guessed.

## 4 + 5. Log the run and post to Slack (one command)
```bash
python -m lib.cli finish-run \
  --employee <you> \
  --task "<Task name>" \
  --result <Success|Partial|Failed|"Blocked on human"> \
  --headline "<one line for the channel>" \
  --summary "<1–3 sentences for the Work Log>" \
  --details "<optional: counts, flagged items, for the Slack thread>" \
  --output-link "<URL of the Sheet/Doc>"
```
This creates the Work Log row (`<Employee> · <Task> · <YYYY-MM-DD>`), posts the status line in the channel as you, puts details plus the Work Log link in the thread, and writes the Slack link back onto the row.

**Choosing the result:**
| Result | When |
|---|---|
| `Success` | Output written in full; nothing pending |
| `Partial` | Output written, but some fields are pending human input or some rows were skipped |
| `Blocked on human` | You can't produce a useful output until someone answers |
| `Failed` | Something broke (auth, API, unexpected data) |

**Headline:** lead with the outcome and the number that matters. Write "Pipeline Tracker refreshed — 3 deals need close dates confirmed", not "Run complete".

## 6. Need a human? Never guess.
For each gap that matters:
```bash
python -m lib.cli input-request \
  --employee <you> --ask <human key from config/humans.yaml> \
  --task "<Task name>" \
  --question "<ONE specific question>" \
  --context "<the record, what's missing, why it matters>" \
  --due <YYYY-MM-DD>
```
This DMs the person as you and creates an Input Request row (`Open`). Ask one specific question per request, naming the record and the field. Batch closely related gaps for the same person into one clear question if needed, but never send a vague "please check".

Then finish the run with `Partial` or `Blocked on human`.

## If anything fails
Still run `finish-run --result Failed`, with a summary of what broke and at which step. If `finish-run` itself exits non-zero, make its error output the last thing you print so it shows in the CI log and the workflow goes red. **Never end a run silently.**
