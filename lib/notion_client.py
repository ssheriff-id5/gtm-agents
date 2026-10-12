"""Notion control-plane client: Team Roster, Work Log, Input Requests.

Talks to the Notion REST API directly (no SDK) using the data-source-aware API
version pinned in config/notion.yaml. Property *names* come from config, so a
rename in Notion is a one-line config change.

Property builders (``_title``, ``_text``, ...) are pure functions so the exact
payloads can be unit-tested and shown in dry-run.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import requests

from lib import config, dryrun

API = "https://api.notion.com/v1"
RICH_TEXT_CHUNK = 2000  # Notion's per-text-object limit

WORK_LOG_RESULTS = ("Success", "Partial", "Failed", "Blocked on human")
INPUT_REQUEST_STATUSES = ("Open", "Answered", "Overdue", "Escalated", "Closed")


# ---------- property builders -------------------------------------------------

def _chunks(text: str) -> list[dict]:
    text = text or ""
    return [{"type": "text", "text": {"content": text[i:i + RICH_TEXT_CHUNK]}}
            for i in range(0, len(text), RICH_TEXT_CHUNK)]


def _title(text: str) -> dict:
    return {"title": _chunks(text)}


def _text(text: str) -> dict:
    return {"rich_text": _chunks(text)}


def _select(name: str) -> dict:
    return {"select": {"name": name}}


def _date(d: date | str) -> dict:
    return {"date": {"start": d.isoformat() if isinstance(d, date) else d}}


def _url(u: str | None) -> dict:
    return {"url": u or None}


def _relation(*page_ids: str) -> dict:
    return {"relation": [{"id": pid} for pid in page_ids]}


def _people(*user_ids: str) -> dict:
    return {"people": [{"object": "user", "id": uid} for uid in user_ids if uid]}


def _checkbox(value: bool) -> dict:
    return {"checkbox": bool(value)}


def plain_text(prop: dict | None) -> str:
    """Flatten a Notion title/rich_text/select/url/... property value to a string."""
    if not prop:
        return ""
    kind = prop.get("type")
    value = prop.get(kind)
    if kind in ("title", "rich_text"):
        return "".join(part.get("plain_text") or part.get("text", {}).get("content", "") for part in value or [])
    if kind == "select":
        return (value or {}).get("name", "")
    if kind == "multi_select":
        return ", ".join(o["name"] for o in value or [])
    if kind == "date":
        return (value or {}).get("start", "")
    if kind in ("url", "email", "phone_number"):
        return value or ""
    if kind == "checkbox":
        return "Yes" if value else "No"
    if kind == "people":
        return ", ".join(p.get("name") or p.get("id", "") for p in value or [])
    if kind == "relation":
        return ", ".join(r["id"] for r in value or [])
    return str(value)


def work_log_title(employee_name: str, task: str, run_date: date) -> str:
    return f"{employee_name} · {task} · {run_date.isoformat()}"


# ---------- client ------------------------------------------------------------

class NotionClient:
    def __init__(self, dry_run: bool | None = None, token: str | None = None):
        self.dry_run = config.is_dry_run() if dry_run is None else dry_run
        self.cfg = config.notion_config()
        self.token = None if self.dry_run else (token or config.require_env("NOTION_TOKEN"))
        self.session = requests.Session()

    # -- plumbing --

    def _db(self, key: str) -> dict:
        return self.cfg["databases"][key]

    def _prop(self, db: str, key: str) -> str:
        return self._db(db)["properties"][key]

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        if self.dry_run:
            dryrun.record("Notion", method, path, payload)
            if method == "POST" and path == "/pages":
                pid = dryrun.fake_id("page")
                return {"id": pid, "url": f"https://www.notion.so/{pid}", "properties": payload["properties"]}
            if method == "PATCH" and path.startswith("/pages/"):
                pid = path.split("/")[2]
                return {"id": pid, "url": f"https://www.notion.so/{pid}"}
            return {"results": [], "has_more": False}
        resp = self.session.request(
            method, API + path, json=payload, timeout=30,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": self.cfg["api_version"],
                "Content-Type": "application/json",
            },
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Notion {method} {path} failed [{resp.status_code}]: {resp.text[:500]}")
        return resp.json()

    def _create_page(self, db: str, properties: dict) -> dict:
        return self._request("POST", "/pages", {
            "parent": {"type": "data_source_id", "data_source_id": self._db(db)["data_source_id"]},
            "properties": properties,
        })

    def _update_page(self, page_id: str, properties: dict) -> dict:
        return self._request("PATCH", f"/pages/{page_id}", {"properties": properties})

    def _query(self, db: str, filter_: dict | None = None, sorts: list | None = None) -> list[dict]:
        path = f"/data_sources/{self._db(db)['data_source_id']}/query"
        results, cursor = [], None
        while True:
            body: dict[str, Any] = {"page_size": 100}
            if filter_:
                body["filter"] = filter_
            if sorts:
                body["sorts"] = sorts
            if cursor:
                body["start_cursor"] = cursor
            data = self._request("POST", path, body)
            results.extend(data.get("results", []))
            if not data.get("has_more"):
                return results
            cursor = data.get("next_cursor")

    # -- Team Roster --

    def get_roster(self) -> list[dict]:
        """Return roster rows as flat dicts keyed by the Notion property name."""
        if self.dry_run:
            # Synthesise from config so `roster` works with no credentials.
            return [{
                "id": e.notion_page_id, "Name": e.display_name, "Title": e.title, "Level": e.level,
                "Schedule": e.schedule_description, "Status": "(dry-run: not read from Notion)",
            } for e in config.all_employees()]
        return [self._flatten(p) for p in self._query("team_roster")]

    def get_employee_row(self, page_id: str) -> dict:
        if self.dry_run:
            return next((r for r in self.get_roster() if r["id"] == page_id), {"id": page_id})
        return self._flatten(self._request("GET", f"/pages/{page_id}"))

    @staticmethod
    def _flatten(page: dict) -> dict:
        row = {"id": page["id"], "url": page.get("url")}
        row.update({name: plain_text(value) for name, value in page.get("properties", {}).items()})
        return row

    # -- Work Log --

    def work_log_properties(self, *, employee_name: str, employee_page_id: str, task: str,
                            run_date: date, result: str, summary: str,
                            output_link: str | None = None, slack_link: str | None = None) -> dict:
        if result not in WORK_LOG_RESULTS:
            raise ValueError(f"result must be one of {WORK_LOG_RESULTS}, got {result!r}")
        p = lambda k: self._prop("work_log", k)  # noqa: E731
        props = {
            p("run"): _title(work_log_title(employee_name, task, run_date)),
            p("employee"): _relation(employee_page_id),
            p("task"): _text(task),
            p("run_date"): _date(run_date),
            p("result"): _select(result),
            p("summary"): _text(summary),
            p("output_link"): _url(output_link),
        }
        if slack_link:
            props[p("slack_link")] = _url(slack_link)
        return props

    def create_work_log(self, **kwargs) -> dict:
        return self._create_page("work_log", self.work_log_properties(**kwargs))

    def update_work_log(self, page_id: str, *, slack_link: str | None = None,
                        reviewed: bool | None = None) -> dict:
        props = {}
        if slack_link is not None:
            props[self._prop("work_log", "slack_link")] = _url(slack_link)
        if reviewed is not None:
            props[self._prop("work_log", "reviewed")] = _checkbox(reviewed)
        return self._update_page(page_id, props)

    def query_work_log(self, run_date: date) -> list[dict]:
        return [self._flatten(p) for p in self._query(
            "work_log", {"property": self._prop("work_log", "run_date"), "date": {"equals": run_date.isoformat()}})]

    # -- Input Requests --

    def create_input_request(self, *, question: str, asked_by_page_id: str,
                             asked_to_notion_user_id: str | None, context: str,
                             due: date, slack_thread: str | None = None) -> dict:
        p = lambda k: self._prop("input_requests", k)  # noqa: E731
        props = {
            p("question"): _title(question),
            p("asked_by"): _relation(asked_by_page_id),
            p("context"): _text(context),
            p("due"): _date(due),
            p("status"): _select("Open"),
        }
        if asked_to_notion_user_id:
            props[p("asked_to")] = _people(asked_to_notion_user_id)
        if slack_thread:
            props[p("slack_thread")] = _url(slack_thread)
        return self._create_page("input_requests", props)

    def update_input_request(self, page_id: str, *, status: str | None = None,
                             answer: str | None = None, slack_thread: str | None = None) -> dict:
        p = lambda k: self._prop("input_requests", k)  # noqa: E731
        props = {}
        if status is not None:
            if status not in INPUT_REQUEST_STATUSES:
                raise ValueError(f"status must be one of {INPUT_REQUEST_STATUSES}, got {status!r}")
            props[p("status")] = _select(status)
        if answer is not None:
            props[p("answer")] = _text(answer)
        if slack_thread is not None:
            props[p("slack_thread")] = _url(slack_thread)
        return self._update_page(page_id, props)

    def query_input_requests(self, statuses: tuple[str, ...] = ("Open", "Overdue"),
                             asked_by_page_id: str | None = None) -> list[dict]:
        p = lambda k: self._prop("input_requests", k)  # noqa: E731
        clauses: list[dict] = [{"or": [{"property": p("status"), "select": {"equals": s}} for s in statuses]}]
        if asked_by_page_id:
            clauses.append({"property": p("asked_by"), "relation": {"contains": asked_by_page_id}})
        return [self._flatten(x) for x in self._query("input_requests", {"and": clauses})]
