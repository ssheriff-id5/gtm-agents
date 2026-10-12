"""Command-line entry point the AI employees call from their skills.

    python -m lib.cli roster
    python -m lib.cli whoami --employee rick
    python -m lib.cli finish-run --employee rick --task "Pipeline Tracker" --result Success \
        --headline "Pipeline Tracker refreshed — 3 deals need close dates confirmed" \
        --summary "..." [--details "..."] [--output-link URL]
    python -m lib.cli input-request --employee rick --ask satiesh --task "Pipeline Tracker" \
        --question "..." --context "..." --due 2026-10-15
    python -m lib.cli smoke-test --employee rick

Dry-run by default; set REVOPS_MODE=live to hit real APIs. Exit code is non-zero
if any step of the contract failed, so a CI run turns red instead of hiding it.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from lib import config, dryrun
from lib.job_contract import RunReport, finish_run, raise_input_request
from lib.notion_client import NotionClient, WORK_LOG_RESULTS


def _banner() -> None:
    mode = "DRY RUN — nothing is sent" if config.is_dry_run() else "LIVE"
    print(f"== RevOps AI Team · mode: {mode} ==")


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
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dryrun.QUIET = args.quiet
    _banner()
    try:
        return args.fn(args)
    except config.ConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
