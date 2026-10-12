"""The job contract, as code.

Agents decide *what* happened (result, headline, summary); this module does the
plumbing the same way every time: log to Notion, post to Slack, cross-link them.

Every step is attempted even if an earlier one fails, and every failure is
reported back. A run must never disappear silently — Abby can only chase what
she can see.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from lib import config
from lib.notion_client import NotionClient, WORK_LOG_RESULTS
from lib.slack_client import SlackClient, status_line


@dataclass
class RunReport:
    work_log_id: str | None = None
    work_log_url: str | None = None
    slack_permalink: str | None = None
    input_request_url: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def finish_run(*, employee: str, task: str, result: str, headline: str, summary: str,
               details: str | None = None, output_link: str | None = None,
               run_date: date | None = None,
               notion: NotionClient | None = None, slack: SlackClient | None = None) -> RunReport:
    """Steps 4–5 of the job contract: log the run, then post it to Slack.

    Order: Work Log row first (so the thread can link to it) → Slack main post +
    thread → back-fill the Slack link onto the Work Log row.
    """
    if result not in WORK_LOG_RESULTS:
        raise ValueError(f"result must be one of {WORK_LOG_RESULTS}")
    emp = config.get_employee(employee)
    run_date = run_date or config.today()
    notion = notion or NotionClient()
    slack = slack or SlackClient()
    report = RunReport()

    # 1. Work Log
    try:
        page = notion.create_work_log(
            employee_name=emp.display_name, employee_page_id=emp.notion_page_id, task=task,
            run_date=run_date, result=result, summary=summary, output_link=output_link)
        report.work_log_id, report.work_log_url = page["id"], page.get("url")
    except Exception as exc:  # noqa: BLE001 — must keep going to Slack
        report.errors.append(f"Work Log write failed: {exc}")

    # 2. Slack: one-line status in channel, detail in thread
    try:
        channel = config.slack_channel()
        main = slack.post_as(emp, channel, status_line(result, headline, output_link))
        report.slack_permalink = main["permalink"]
        thread_lines = [f"*{task}* — {result}", summary]
        if details:
            thread_lines += ["", details]
        if report.work_log_url:
            thread_lines.append(f"\nWork Log: <{report.work_log_url}|{emp.display_name} · {task} · {run_date}>")
        else:
            thread_lines.append("\n:warning: Could not write the Work Log row for this run — Abby, please check.")
        slack.post_as(emp, main["channel"], "\n".join(thread_lines), thread_ts=main["ts"], with_permalink=False)
    except Exception as exc:  # noqa: BLE001
        report.errors.append(f"Slack post failed: {exc}")

    # 3. Cross-link
    if report.work_log_id and report.slack_permalink:
        try:
            notion.update_work_log(report.work_log_id, slack_link=report.slack_permalink)
        except Exception as exc:  # noqa: BLE001
            report.errors.append(f"Back-filling Slack link failed: {exc}")

    return report


def raise_input_request(*, employee: str, ask: str, task: str, question: str, context: str,
                        due: date, notion: NotionClient | None = None,
                        slack: SlackClient | None = None) -> RunReport:
    """Step 6 of the job contract: DM a human one specific question and log it.

    ``ask`` is a key in config/humans.yaml. The DM goes first so its permalink
    can be stored on the Input Request (Abby reads replies from there). If the DM
    fails the row is still created, so the request is never lost.
    """
    emp = config.get_employee(employee)
    human = config.humans().get(ask)
    if human is None:
        raise config.ConfigError(f"Unknown human '{ask}' — add them to config/humans.yaml")
    notion = notion or NotionClient()
    slack = slack or SlackClient()
    report = RunReport()

    text = (f"Hi {human.get('name', '')}, {emp.display_name} here ({emp.title}). "
            f"For the {task}: {question}\n"
            f"_Context:_ {context}\n"
            f"Please reply in this thread by {due.strftime('%A %-d %b')}. "
            f"Your answer will be marked as human-provided in the output.")
    thread = None
    try:
        thread = slack.dm(emp, ask, text)["permalink"]
        report.slack_permalink = thread
    except Exception as exc:  # noqa: BLE001
        report.errors.append(f"Slack DM failed: {exc}")

    try:
        page = notion.create_input_request(
            question=question, asked_by_page_id=emp.notion_page_id,
            asked_to_notion_user_id=human.get("notion_user_id"),
            context=f"[{task}] {context}", due=due, slack_thread=thread)
        report.input_request_url = page.get("url")
    except Exception as exc:  # noqa: BLE001
        report.errors.append(f"Input Request write failed: {exc}")
    return report
