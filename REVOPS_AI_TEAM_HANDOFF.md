# RevOps AI Team — Handoff to Claude Code

**Owner:** Satiesh (Commercial / Revenue Operations)
**Status:** Design agreed, Notion control plane built, code not started
**Purpose of this doc:** This is the full context for Claude Code to scaffold and build the system. Drop it into the repo root and point Claude Code at it.

---

## 1. What we're building, and why

The revenue org needs recurring RevOps work (reports, data refreshes, hygiene checks) done automatically and visible to everyone. Today this work is done one report at a time. The first automated report is the **Pipeline Tracker (Next 90 Days)**. It runs as a scheduled Claude skill that overwrites a Google Sheet.

The goal is a **team of AI employees** modelled on a real RevOps team. Each employee owns specific work, reports to a manager, logs what they did, tells humans in Slack, and asks humans for input when they need it.

**Why model it as employees:** Satiesh wants to picture the system as a team. That framing also makes good engineering sense. It gives each piece clear ownership, a clear job description, and a clear escalation path. When a new task comes up, the question becomes "whose job is this?", which is easier to answer than "which script do we add?".

**Build philosophy:** Build slowly. Many tasks aren't known yet. Infrastructure comes first, then one employee at a time, then new work as it's discovered through Task Intake.

---

## 2. The team

| Name | Title | Reports to | Vertical | Status |
|---|---|---|---|---|
| **Abby** | AI RevOps Manager | Satiesh | Team oversight | Onboarding |
| **Rick** | AI Jr RevOps | Abby | Pipeline & forecasting (proposed) | Onboarding |
| **Stevey** | AI Jr RevOps | Abby | TBD (proposed: CRM data hygiene & ops reporting) | Onboarding |

### Abby: AI RevOps Manager
- **Does not produce reports herself.** She manages, reviews, chases, and summarises.
- Each run (daily, after Rick and Stevey are scheduled to finish), she does five things:
  1. She reads today's Work Log and flags any run that was expected but is missing, failed, or partial. "Expected" comes from each employee's Schedule in the Team Roster.
  2. She checks open Input Requests. She reads the Slack replies, writes answers back to Notion, and marks rows Answered.
  3. She marks overdue requests as Overdue, nudges the person once, and escalates to the human owner (Satiesh) if a request is still overdue after the nudge.
  4. She ticks "Reviewed by Abby" on the Work Log rows she has processed.
  5. She posts a **daily digest** to the team Slack channel covering what ran, what's blocked, and what needs a human.
- **Rationale:** a manager that runs on a schedule and reviews logs is predictable, cheap, and easy to debug. A manager that is always on and delegates live is harder to trust and harder to fix.

### Rick: AI Jr RevOps
- First assignment: **Pipeline Tracker (Next 90 Days).**
- Future work: other pipeline and forecast reporting.

### Stevey: AI Jr RevOps
- A placeholder until real work arrives through Task Intake.

---

## 3. The job contract (every junior, every run)

Every worker must follow the same sequence. This consistency is what lets Abby manage any employee without knowing the details of their job, and what lets new employees be added safely.

1. **Read the job.** Load the employee's own Team Roster row (responsibilities, schedule, tools) and the task config.
2. **Do the work.** Run the relevant skill.
3. **Write the output** where the audience already looks, such as a Google Sheet or Doc.
4. **Log the run** as a new Work Log row with: Employee, Task, Run Date, Result (`Success` / `Partial` / `Failed` / `Blocked on human`), a 1–3 sentence Summary, Output Link, and Slack Link.
5. **Post to Slack** under the employee's own name and avatar. The main message is a one-line status plus a link. Detail goes in the thread.
6. **If human input is needed:** never guess. Create an Input Request row, DM the person with a *specific* question, finish the run with that field marked pending, and log the result as `Partial` or `Blocked on human`.

**Failure behaviour:** if any step fails, the employee should still try to log a `Failed` row and post a failure message. Silent failure is the worst outcome, because Abby can only chase what she can see.

---

## 4. Tooling and where things live

| Layer | Tool | Role |
|---|---|---|
| Control plane / "HR system" | **Notion** | Team Roster, Work Log, Input Requests, Task Intake. This is the shared memory every agent reads and writes, and it's human-readable for the team. |
| Outputs | **Google Sheets / Docs** | Deliverables live where their audience already works. |
| Notifications and conversation | **Slack** | Run summaries, Abby's digest, DMs to humans for input. |
| Source data | **CRM** (whatever the current Pipeline Tracker skill pulls from; confirm when porting) | Raw data. |

More tools will be added later. Every new tool must be declared in the Team Roster "Tools" field for the employee who uses it.

**Sourcing integrity (Satiesh's standing requirement):** outputs must clearly separate raw or automated data from human-entered or editorial input. In Sheets, manual-input columns are **colour-coded** so it's obvious they're human-entered. Input Request answers that get written into a report must be marked as human-provided, never blended silently into the automated data.

---

## 5. Notion control plane (already built)

Parent page: **RevOps AI Team**. This is currently a *private* page in Satiesh's workspace and needs to move to a shared teamspace before go-live.

- Page: https://app.notion.com/p/3f7334ab4b6a81d6b1d3e134aad76da4
- Page ID: `3f7334ab-4b6a-81d6-b1d3-e134aad76da4`

### 5.1 Team Roster
- DB: https://app.notion.com/p/ee18db340aa846f9bee1d78b7f185d13
- Data source: `collection://ec2c0903-399d-4357-a62c-acc389565ccf`
- Properties: `Name` (title), `Title`, `Level` (Manager / Junior), `Reports To`, `Vertical`, `Responsibilities`, `Tools` (multi-select: Google Sheets, Google Docs, Notion, Slack, CRM), `Schedule`, `Status` (Active / Onboarding / Paused), `Human Owner` (person)
- Employee page IDs:
  - Abby: `3f7334ab-4b6a-8145-bad2-ca9dacc25161`
  - Rick: `3f7334ab-4b6a-81e8-be22-cae100e1ce25`
  - Stevey: `3f7334ab-4b6a-81de-a8d3-ec135c9093b0`

### 5.2 Work Log
- DB: https://app.notion.com/p/56142807e40145918c1328471dc03639
- Data source: `collection://482250f2-0412-4142-bd65-b27d2a88159c`
- Properties: `Run` (title), `Employee` (relation → Team Roster), `Task`, `Run Date` (date), `Result` (Success / Partial / Failed / Blocked on human), `Summary`, `Output Link` (url), `Slack Link` (url), `Reviewed by Abby` (checkbox)
- Title convention: `<Employee> · <Task> · <YYYY-MM-DD>`

### 5.3 Input Requests
- DB: https://app.notion.com/p/f0d971a2ab6045babba8d5d193888fe8
- Data source: `collection://ac7f7de7-e665-4443-b3dc-1ce5b54f0004`
- Properties: `Question` (title), `Asked By` (relation → Team Roster), `Asked To` (person), `Context`, `Due` (date), `Status` (Open / Answered / Overdue / Escalated / Closed), `Answer`, `Slack Thread` (url)

### 5.4 Task Intake
- DB: https://app.notion.com/p/ea7f93419e964c948bf8f07e412d2a59
- Data source: `collection://4b8e657c-5d65-46ba-acdd-8d676090c5f8`
- Properties: `Task` (title), `Requested By` (person), `Description`, `Audience`, `Cadence` (Daily / Weekly / Monthly / Ad hoc), `Data Sources`, `Needs Human Input` (checkbox), `Assigned To` (relation → Team Roster), `Status` (New / Scoping / Building / Live / Declined)
- Suggested addition: a Notion **form view** on this DB so anyone in the revenue org can submit requests easily.

> These were created through the claude.ai Notion connector. The repo will need its own **Notion internal integration token**, and that integration must be **shared with the RevOps AI Team page** or it won't see the databases.

---

## 6. Proposed repo structure

```
revops-ai-team/
├── CLAUDE.md                     # Company handbook: mission, job contract, sourcing rules, tone
├── REVOPS_AI_TEAM_HANDOFF.md     # This file
├── .claude/
│   ├── agents/
│   │   ├── abby.md               # Manager subagent definition
│   │   ├── rick.md               # Junior subagent definition
│   │   └── stevey.md             # Junior subagent definition
│   └── skills/
│       ├── pipeline-tracker/     # Ported from the existing claude.ai skill (Rick)
│       │   └── SKILL.md
│       ├── job-contract/         # Shared: log run, post to Slack, raise input request
│       │   └── SKILL.md
│       └── manager-review/       # Abby's daily review + digest
│           └── SKILL.md
├── .mcp.json                     # MCP servers (Notion, etc.) if used instead of direct API
├── lib/                          # Small deterministic helpers (keep logic out of prompts where possible)
│   ├── notion_client.py          # create_work_log(), create_input_request(), get_roster(), ...
│   ├── slack_client.py           # post_as(employee, channel, text, thread_ts=None), dm(), read_replies()
│   └── sheets_client.py          # write range, apply manual-column colour coding
├── config/
│   ├── employees.yaml            # name → Notion page ID, Slack display name, avatar URL, schedule
│   └── notion.yaml               # DB / data source IDs from section 5
├── .github/workflows/
│   ├── rick-pipeline-tracker.yml # Scheduled run (cron)
│   ├── stevey.yml                # Added when Stevey gets work
│   └── abby-daily-review.yml     # Runs after the juniors
└── README.md                     # Setup, secrets, how to add a new employee
```

**Design notes:**
- **Subagents = employees.** Each `.claude/agents/<name>.md` holds the role, responsibilities, allowed tools, and the instruction to follow the job contract skill. Changing someone's job means editing their file, and Git keeps the history of every change.
- **Skills = SOPs.** Skills are reusable and assignable. If Rick goes on "leave", Stevey could pick up a skill.
- **Helpers in `lib/` for anything deterministic** (logging, posting, writing ranges). Prompts handle judgement, code handles plumbing. This is more reliable and cheaper to run.
- **Scheduling via GitHub Actions cron** running Claude Code headless (`claude -p ...`, or the official Claude Code GitHub Action). Runs don't depend on anyone's laptop or session being on. Abby's workflow is scheduled after the juniors' workflows.

---

## 7. Slack design

- **Channel:** `#revops-ai-team` (name TBD). It carries all run summaries and Abby's digest. If leadership wants only the rollup, add a second channel for Abby's digest alone.
- **Identity:** one Slack app with a bot token. Use `chat:write.customize` so each post shows the employee's own name and avatar ("Abby", "Rick", "Stevey"). This fixes the problem with the claude.ai connector, which posts as Satiesh.
- **Message format:**
  - Main post: `✅ Pipeline Tracker refreshed — 3 deals need close dates confirmed. <link>`
  - Thread: details, counts, anything flagged.
  - Status emoji: ✅ success, ⚠️ partial, ❌ failed, ⏳ blocked on human.
- **Abby's digest:** three short sections (Ran, Blocked, Needs a human), each item linking to its Work Log row or output.
- **Bot scopes (to confirm with the Slack admin):** `chat:write`, `chat:write.customize`, `im:write`, `im:history`, `users:read`, `users:read.email` (to map Notion people to Slack users), and `channels:history` if Abby reads threads in the team channel.

---

## 8. Human-in-the-loop flow

1. A junior hits a gap, for example a missing close date or a deal needing commentary.
2. It creates an Input Request (`Status = Open`, `Due` set, `Context` filled in).
3. It DMs the person as itself, with one specific question, the context, and the deadline.
   - Example: "Hi, Rick here (AI Jr RevOps). For the Pipeline Tracker: Acme renewal shows no close date. What's the expected close month? Reply here by Thursday."
4. It finishes its run with the field left pending, marked as awaiting human input in the output, and logs `Partial` or `Blocked on human`.
5. On her next run, Abby reads the DM replies, writes `Answer` to Notion, and sets `Status = Answered`.
6. The junior's next run consumes the answered requests and marks them `Closed`. The value is written to the output, flagged as human-provided.
7. If no reply arrives by the due date, Abby sets `Overdue` and sends one nudge. If there's still no reply, she sets `Escalated` and tags the Human Owner in the digest.

**Known limitation:** agents don't wait mid-run. Answers are picked up on the next scheduled run. That's fine for daily or weekly reports. If a task ever needs "ask, wait 2 hours, then finish", that's the point to add an intra-day check schedule for Abby, or reconsider an orchestration tool. Satiesh's earlier decision was to keep everything in Claude and not use n8n, and that still stands.

---

## 9. Existing asset to port: Pipeline Tracker (Next 90 Days)

- **Previously** built and refreshed manually by Matt Debonis. Satiesh has taken it over, and feedback on ownership and cadence is still pending.
- **Current state:** being built as a scheduled Claude skill (claude.ai) that **overwrites** a Google Sheet.
- **Rollout plan, kept as-is:** test sheet → daily runs after feedback from a few runs → move to the live sheet.
- **Requirement:** manual-input columns are colour-coded to show they're human-entered, not automated.
- **Porting tasks:**
  1. Copy the skill instructions into `.claude/skills/pipeline-tracker/SKILL.md`.
  2. Replace claude.ai connector calls with repo credentials (Google service account; CRM API access).
  3. Wrap the skill in the job contract (log, Slack, input requests).
  4. Assign it to Rick in the Team Roster and in `rick.md`.
  5. Re-run against the **test sheet** before touching the live sheet.

---

## 10. Credentials and setup checklist (for IT / admins)

| Item | Who | Notes |
|---|---|---|
| Anthropic API key | Satiesh / finance | Billed separately from claude.ai seats; store as a repo secret |
| GitHub repo (private) | Satiesh / IT | Owner plus at least one backup admin |
| Notion internal integration token | Notion admin | Share the integration with the RevOps AI Team page |
| Slack app + bot token | Slack admin | Scopes in section 7; install to workspace; invite bot to channel |
| Google service account (JSON key) | Google Workspace admin | Share the target Sheets/Docs with the service account email |
| CRM API credentials | CRM admin | Read-only is enough to start |
| Repo secrets | Satiesh | `ANTHROPIC_API_KEY`, `NOTION_TOKEN`, `SLACK_BOT_TOKEN`, `GOOGLE_SA_JSON`, CRM creds |

Principle: **least privilege.** Each credential gets only the access the employees actually need. Start read-only on the CRM.

---

## 11. Build phases

| Phase | Deliverable | Done when |
|---|---|---|
| 0 | Credentials + repo skeleton (section 6) | All secrets set; `CLAUDE.md` and the three agent files exist |
| 1 | `lib/` helpers + job-contract skill | A dummy run writes a Work Log row and posts to Slack as "Rick" |
| 2 | Port the Pipeline Tracker to Rick | Scheduled run on the **test sheet** logs + posts correctly for several runs |
| 3 | Abby's daily review + digest | Abby flags a deliberately skipped run and posts a digest |
| 4 | Human-input loop | A real DM → reply → answer lands in Notion → consumed next run |
| 5 | Pipeline Tracker to live sheet | After feedback from test runs |
| 6+ | New work via Task Intake | Assign to Rick or Stevey; consolidate when 3+ tasks share data sources and an owner |

**How to split work between employees:** split by data source, owner, and cadence, not by report name. Start with one task per assignment and group related tasks into a vertical once a pattern appears.

---

## 12. Open decisions

1. Final verticals for Rick and Stevey. Stevey has no work yet.
2. Slack channel name, and whether leadership gets a separate digest-only channel.
3. Avatars and display names for the three bots.
4. Run times: when the juniors run, and when Abby runs after them.
5. Who besides Satiesh is a Human Owner or escalation point.
6. Pipeline Tracker cadence and ownership. This is waiting on feedback.
7. Moving the Notion page from private to a shared teamspace, and who can edit vs view.
8. Repo owner and backup admin.

---

## 13. Kickoff prompt for Claude Code

> Read `REVOPS_AI_TEAM_HANDOFF.md`. Scaffold the repo exactly as in section 6. Write `CLAUDE.md` as the team handbook: mission, job contract (section 3), sourcing-integrity rules (section 4), Slack format (section 7) and human-input flow (section 8). Create `.claude/agents/abby.md`, `rick.md`, `stevey.md` from section 2. Put the Notion IDs from section 5 into `config/notion.yaml`. Build `lib/notion_client.py` and `lib/slack_client.py` with a dry-run mode so I can test without credentials. Don't port the Pipeline Tracker yet; stop after Phase 1 and show me a dry-run Work Log entry and Slack message for Rick. Explain your design choices as you go.
