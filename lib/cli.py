"""Command-line entry point the AI employees call from their skills.

    python -m lib.cli roster
    python -m lib.cli whoami --employee rick
    python -m lib.cli finish-run --employee rick --task "Pipeline Tracker" --result Success \
        --headline "Pipeline Tracker refreshed — 3 deals need close dates confirmed" \
        --summary "..." [--details "..."] [--output-link URL]
    python -m lib.cli input-request --employee rick --ask satiesh --task "Pipeline Tracker" \
        --question "..." --context "..." --due 2026-10-15
    python -m lib.cli smoke-test --employee rick
    python -m lib.cli leads-pending [--ids-file out/leads/pending.txt] [--json-file out/leads/pending.json]
    python -m lib.cli leads-since --posted-text out/leads/webform.txt
    python -m lib.cli leads-pending --zoho-json out/leads/zoho-1.json [...] --posted-text out/leads/webform.txt
    python -m lib.cli lead-post --assessment out/leads/<lead_id>.json
    python -m lib.cli lead-render --assessment out/leads/<lead_id>.json --zoho-json out/leads/zoho.json
    python -m lib.cli leads-verify --ids-file out/leads/pending.txt
    python -m lib.cli lead-triage-failed --detail "..." [--run-url URL]

Dry-run by default; set REVOPS_MODE=live to hit real APIs. Exit code is non-zero
if any step of the contract failed, so a CI run turns red instead of hiding it.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from lib import config, dryrun, lead_triage
from lib.job_contract import RunReport, finish_run, raise_input_request
from lib.notion_client import NotionClient, WORK_LOG_RESULTS


def _banner() -> None:
    mode = "DRY RUN — nothing is sent" if config.is_dry_run() else "LIVE"
    print(f"== RevOps AI Team · mode: {mode} ==", file=sys.stderr)


def _print_report(report: RunReport) -> int:
    if config.is_dry_run():
        print("\n== Preview (what humans would see) ==\n" + dryrun.render_preview())
    print("\n== Result ==")
    print(json.dumps({k: v for k, v in report.__dict__.items()}, indent=2))
    return 0 if report.ok else 1


def cmd_roster(_args) -> int:
    for row in NotionClient().get_roster():
        print(json.dumps(row, ensure_ascii=False))
    return 0


def cmd_whoami(args) -> int:
    """Step 1 of the job contract: read your own job (config + Notion roster row)."""
    emp = config.get_employee(args.employee)
    row = NotionClient().get_employee_row(emp.notion_page_id)
    print(json.dumps({"config": emp.__dict__, "notion_roster_row": row}, indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_finish_run(args) -> int:
    return _print_report(finish_run(
        employee=args.employee, task=args.task, result=args.result, headline=args.headline,
        summary=args.summary, details=args.details, output_link=args.output_link,
        run_date=date.fromisoformat(args.run_date) if args.run_date else None))


def cmd_input_request(args) -> int:
    return _print_report(raise_input_request(
        employee=args.employee, ask=args.ask, task=args.task, question=args.question,
        context=args.context, due=date.fromisoformat(args.due)))


def cmd_smoke_test(args) -> int:
    """Phase 1 'done when': a dummy run logs a Work Log row and posts to Slack as the employee."""
    emp = config.get_employee(args.employee)
    return _print_report(finish_run(
        employee=emp.key, task="Job contract smoke test", result="Success",
        headline=f"Job contract smoke test passed — {emp.display_name} can log to Notion and post to Slack",
        summary=(f"Dummy run to prove the plumbing. {emp.display_name} wrote this Work Log row and "
                 "posted this message under their own name. No real data was touched."),
        details="• Notion Work Log: row created\n• Slack: main post + thread\n• Cross-link: Slack link back-filled",
        output_link=None))


def cmd_leads_pending(args) -> int:
    """Web-form leads not yet posted to #webform, as briefs for Claude to research."""
    if not args.zoho_json:
        _banner()
    if bool(args.zoho_json) != bool(args.posted_text):
        raise config.ConfigError("--zoho-json and --posted-text go together")
    leads = (lead_triage.pending_from_files(args.zoho_json, args.posted_text) if args.zoho_json
             else lead_triage.pending_leads())
    briefs = [lead_triage.lead_brief(lead) for lead in leads]
    print(json.dumps(briefs, indent=2, ensure_ascii=False))
    if args.ids_file:
        Path(args.ids_file).parent.mkdir(parents=True, exist_ok=True)
        Path(args.ids_file).write_text("".join(f"{b['lead_id']}\n" for b in briefs), encoding="utf-8")
    if args.json_file:
        Path(args.json_file).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_file).write_text(json.dumps(briefs, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(briefs)} pending lead(s)", file=sys.stderr)
    return 0


def cmd_lead_post(args) -> int:
    try:
        assessment = lead_triage.load_assessment(args.assessment)
    except lead_triage.AssessmentError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    brief = lead_triage.lead_brief(lead_triage.find_lead(assessment["lead_id"]))
    report = lead_triage.post_assessment(brief, assessment)
    if config.is_dry_run():
        print("\n== Preview (what #webform would see) ==\n" + dryrun.render_preview())
    print(json.dumps(report.__dict__, indent=2))
    for err in report.errors:
        print(f"ERROR: {err}", file=sys.stderr)
    return 0 if report.ok else 1


def cmd_leads_since(args) -> int:
    """How far back this run must pull from Zoho (ISO time), from the last lead posted in #webform."""
    posted = Path(args.posted_text).read_text(encoding="utf-8")
    last = lead_triage.last_received_in_text(posted)
    print(json.dumps({"pull_since": lead_triage.pull_since(posted).isoformat(timespec="seconds"),
                      "last_lead_posted": last.isoformat() if last else None}))
    return 0


def cmd_lead_render(args) -> int:
    """Format a lead's #webform post (for sending through the Slack connector)."""
    try:
        assessment = lead_triage.load_assessment(args.assessment)
        brief = lead_triage.lead_brief(lead_triage.find_lead(assessment["lead_id"], leads_file=args.zoho_json))
        print(json.dumps(lead_triage.render(brief, assessment, args.style), indent=2, ensure_ascii=False))
    except lead_triage.AssessmentError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_leads_verify(args) -> int:
    """Fail if any lead from the pending list didn't make it to #webform (no silent skips)."""
    wanted = [line.strip() for line in Path(args.ids_file).read_text().splitlines() if line.strip()]
    if config.is_dry_run():
        print(f"Dry run: skipping verification of {len(wanted)} lead(s) (nothing was really posted)")
        return 0
    missing = sorted(set(wanted) - lead_triage.posted_lead_ids(lead_triage.slack_client()))
    if missing:
        print(f"ERROR: {len(missing)} lead(s) were not posted: {', '.join(missing)}", file=sys.stderr)
        return 1
    print(f"All {len(wanted)} lead(s) posted")
    return 0


def cmd_lead_triage_failed(args) -> int:
    lead_triage.post_failure(args.detail, args.run_url)
    if config.is_dry_run():
        print("\n== Preview ==\n" + dryrun.render_preview())
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m lib.cli", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quiet", action="store_true", help="Dry-run: hide raw API payloads, keep the preview")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("roster", help="List the Team Roster").set_defaults(fn=cmd_roster)

    p = sub.add_parser("whoami", help="Show an employee's config + roster row")
    p.add_argument("--employee", required=True)
    p.set_defaults(fn=cmd_whoami)

    p = sub.add_parser("finish-run", help="Log the run to Notion and post to Slack")
    p.add_argument("--employee", required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--result", required=True, choices=WORK_LOG_RESULTS)
    p.add_argument("--headline", required=True, help="One line for the main Slack post")
    p.add_argument("--summary", required=True, help="1–3 sentences for the Work Log")
    p.add_argument("--details", help="Extra detail for the Slack thread")
    p.add_argument("--output-link")
    p.add_argument("--run-date", help="YYYY-MM-DD (default: today in team timezone)")
    p.set_defaults(fn=cmd_finish_run)

    p = sub.add_parser("input-request", help="DM a human a specific question and log it")
    p.add_argument("--employee", required=True)
    p.add_argument("--ask", required=True, help="Key in config/humans.yaml")
    p.add_argument("--task", required=True)
    p.add_argument("--question", required=True)
    p.add_argument("--context", required=True)
    p.add_argument("--due", required=True, help="YYYY-MM-DD")
    p.set_defaults(fn=cmd_input_request)

    p = sub.add_parser("smoke-test", help="Phase 1 dummy run")
    p.add_argument("--employee", required=True)
    p.set_defaults(fn=cmd_smoke_test)

    p = sub.add_parser("leads-pending", help="Web-form leads not yet posted to #webform (JSON)")
    p.add_argument("--ids-file", help="Also write the pending lead IDs here, one per line")
    p.add_argument("--json-file", help="Also write the briefs JSON here")
    p.add_argument("--zoho-json", nargs="+", help="Connector mode: Zoho Leads response(s) saved to file(s)")
    p.add_argument("--posted-text", help="Connector mode: recent #webform history saved to a file")
    p.set_defaults(fn=cmd_leads_pending, banner=False)  # banner only when it calls the APIs

    p = sub.add_parser("lead-post", help="Validate a lead assessment and post it to #webform")
    p.add_argument("--assessment", required=True, help="Path to the assessment JSON")
    p.set_defaults(fn=cmd_lead_post)

    p = sub.add_parser("leads-since", help="From #webform history: how far back to pull leads from Zoho")
    p.add_argument("--posted-text", required=True)
    p.set_defaults(fn=cmd_leads_since, banner=False)

    p = sub.add_parser("lead-render", help="Validate an assessment and print the #webform post text")
    p.add_argument("--assessment", required=True)
    p.add_argument("--zoho-json", nargs="+", required=True, help="The same Zoho Leads file(s) used for leads-pending")
    p.add_argument("--style", choices=("markdown", "mrkdwn"), default="markdown")
    p.set_defaults(fn=cmd_lead_render, banner=False)  # sends nothing, in any mode

    p = sub.add_parser("leads-verify", help="Fail if any of the given leads isn't in #webform")
    p.add_argument("--ids-file", required=True)
    p.set_defaults(fn=cmd_leads_verify)

    p = sub.add_parser("lead-triage-failed", help="Post a failure notice to #webform")
    p.add_argument("--detail", required=True)
    p.add_argument("--run-url")
    p.set_defaults(fn=cmd_lead_triage_failed)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dryrun.QUIET = args.quiet
    if getattr(args, "banner", True):
        _banner()
    try:
        return args.fn(args)
    except config.ConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
