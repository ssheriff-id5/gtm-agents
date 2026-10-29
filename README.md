# RevOps AI Team

A small team of AI employees that do recurring RevOps work. Each one logs every run to Notion, reports in Slack under its own name, and asks humans when it needs input.

| | |
|---|---|
| Handbook (read by every agent) | [`CLAUDE.md`](CLAUDE.md) |
| Full design / handoff | [`REVOPS_AI_TEAM_HANDOFF.md`](REVOPS_AI_TEAM_HANDOFF.md) |
| Employees | [`.claude/agents/`](.claude/agents): Abby (manager), Rick, Stevey |
| SOPs | [`.claude/skills/`](.claude/skills): `job-contract`, `manager-review` (draft), `pipeline-tracker` (not yet ported), `web-lead-triage` |
| Plumbing | [`lib/`](lib): Notion, Slack, Sheets, Zoho clients + `lib.cli` |
| IDs and identities | [`config/`](config) |

**Build status:** Phase 1 (helpers and job contract) is done in dry-run. Next comes Phase 0's credentials, then Phase 2 (port the Pipeline Tracker to Rick).

## Try it (no credentials needed)

```bash
pip install -r requirements.txt
python -m lib.cli --quiet smoke-test --employee rick       # dummy run: Work Log row + Slack post as Rick
python -m lib.cli input-request --employee rick --ask satiesh --task "Pipeline Tracker" \
  --question "Acme renewal shows no close date. What's the expected close month?" \
  --context "Deal: Acme renewal" --due 2026-10-15
python -m lib.cli whoami --employee rick
python -m unittest discover -s tests
```

Everything is **dry-run by default**. Each command prints the exact Notion/Slack API payloads plus a preview of what humans would see. Drop `--quiet` to see the raw payloads.

## Going live

1. **Secrets** (repo → Settings → Secrets and variables → Actions):
   - Secrets: `NOTION_TOKEN`, `SLACK_BOT_TOKEN` (later: `ANTHROPIC_API_KEY`, `GOOGLE_SA_JSON`, CRM creds)
   - Variable: `SLACK_CHANNEL_ID` (the `C0…` ID of `#revops-ai-team`)
2. **Notion:** create an internal integration and share the **RevOps AI Team** page with it (page menu → Connections), or it won't see the databases.
3. **Slack app** scopes: `chat:write`, `chat:write.customize`, `im:write`, `im:history`, `users:read`, `users:read.email` (+ `channels:history` for Abby). Install it to the workspace and invite the bot to the channel.
4. **People:** fill in `config/humans.yaml` (Notion user ID + email for Satiesh and anyone else who answers questions).
5. **Test it:** Actions → *Rick · Pipeline Tracker* → Run workflow → `mode: live`. You should get a Work Log row and a post from "Rick" in the channel. That's Phase 1's "done when".

Locally: `REVOPS_MODE=live NOTION_TOKEN=… SLACK_BOT_TOKEN=… SLACK_CHANNEL_ID=… python -m lib.cli smoke-test --employee rick`.

## Web lead triage (#webform)

Website "Contact Us" leads go from Zoho into a Claude assessment, then a post in `#webform` **from Satiesh's Slack account**. The team reviews the post there. Satiesh then approves the lead in Zoho and assigns it. This isn't an AI-employee task: there's no persona and no Work Log row. The Slack post is the record, and it's also how the pipeline knows which leads are already done.

- SOP: [`.claude/skills/web-lead-triage/`](.claude/skills/web-lead-triage) (spam check, research, offering match, 1–10 score). The offerings reference is `offerings.md`.
- Plumbing: `lib/zoho_client.py` (read-only), `lib/lead_triage.py`, config `config/lead_triage.yaml`.
- **How it runs now:** an hourly Claude scheduled task (claude.ai) using the connected **Zoho CRM**, **Slack** and **Clay** connectors, like the other scheduled reports. No API keys needed. `lib.cli` only filters, dedupes, validates and formats (`leads-pending --zoho-json … --posted-text …`, `lead-render`).
- The lead's message and the approve link are inserted by code straight from Zoho, never retyped by Claude. Each post carries `Zoho lead ID: <id>`, which is how later runs know it's done. Leads from before the go-live cutoff (`not_before` in the config) are never posted. If leads can't be posted, a ❌ note goes to `#webform` and they're retried next run.
- Use Zoho `getRecords`, not COQL: COQL leaves out leads still waiting for approval.

**Later (optional): headless GitHub Actions run** (`.github/workflows/web-lead-triage.yml`, cron off). It doesn't depend on anyone's claude.ai connectors, but it needs these secrets:
1. **Zoho:** go to [api-console.zoho.eu](https://api-console.zoho.eu) → Self Client, scope `ZohoCRM.modules.leads.READ`, ideally as a Zoho integration user. Add `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET` and `ZOHO_REFRESH_TOKEN`.
2. **Slack:** a user token (`chat:write`, `channels:history`) installed as Satiesh, added as `SLACK_USER_TOKEN`.
3. Add `ANTHROPIC_API_KEY`.

Try it locally: `python -m lib.cli leads-pending` (prints fixture leads in dry-run).

## Adding a new employee

1. Add a row to the **Team Roster** in Notion and copy its page ID.
2. Add an entry to `config/employees.yaml` (key, display name, Notion page ID, Slack username and icon, schedule).
3. Create `.claude/agents/<name>.md` using `rick.md` as a template: role, responsibilities, tools, "follow the job-contract skill".
4. Add `.github/workflows/<name>-<task>.yml`. If they're on a schedule, make sure Abby's run comes after theirs.
5. Run `python -m lib.cli smoke-test --employee <name>` (dry-run, then live).

## Adding new work

New requests go into **Task Intake** in Notion. Once a task is scoped, write its skill in `.claude/skills/<task>/SKILL.md`, add it to the owning employee's agent file and Roster row, and schedule it. Split work by data source, owner and cadence, not by report name.

## Design choices

- **Code handles plumbing, prompts handle judgement.** Agents never hand-build API calls. They decide the result, headline, summary and questions, then call `python -m lib.cli`. Logging and posting therefore look identical across employees and runs, and they can be unit-tested.
- **`finish-run` is one command for steps 4–5.** It writes the Work Log row first (so the Slack thread can link to it), then posts, then writes the Slack permalink back onto the row. Every step is attempted even if an earlier one fails, and errors produce a non-zero exit, so a broken run turns the workflow red instead of vanishing.
- **`input-request` DMs first, then creates the row**, so the row stores the DM permalink Abby will read replies from. If the DM fails, the row is still created.
- **Dry-run unless `REVOPS_MODE=live`.** In live mode a missing token is a hard error, never a quiet fallback to dry-run.
- **Direct REST, not MCP, for Notion and Slack.** Runs are headless in CI, and plain HTTP with an integration token is simpler and more predictable there. `.mcp.json` is present but empty, ready if an MCP server is useful later (for example a CRM).
- **Notion API `2025-09-03`** (data-source aware). Rows are created under the `collection://` data source IDs from the handoff, and property names/types were verified against the live databases.
- **Config split:** `notion.yaml` holds the control plane's IDs and property names, `employees.yaml` holds who the agents are, and `humans.yaml` holds who they talk to. Renaming a Notion column is a one-line config change.
- **Minimal dependencies:** `requests` and `PyYAML` only. Tests use stdlib `unittest`.
