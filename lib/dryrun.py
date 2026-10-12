"""Shared dry-run recorder.

In dry-run mode every client prints the exact API request it *would* have sent
and records it in ``JOURNAL`` (handy in tests). Fake IDs/URLs are returned so the
rest of the run (e.g. back-filling a Slack link into a Work Log row) still executes.
"""
from __future__ import annotations

import json
import sys
import uuid

JOURNAL: list[dict] = []
QUIET = False


def fake_id(prefix: str) -> str:
    return f"dryrun-{prefix}-{uuid.uuid4().hex[:8]}"


def record(service: str, method: str, endpoint: str, payload: dict | None = None) -> None:
    entry = {"service": service, "method": method, "endpoint": endpoint, "payload": payload}
    JOURNAL.append(entry)
    if QUIET:
        return
    out = sys.stdout
    print(f"\n┌─ [DRY RUN] {service}: {method} {endpoint}", file=out)
    if payload is not None:
        for line in json.dumps(payload, indent=2, ensure_ascii=False).splitlines():
            print(f"│ {line}", file=out)
    print("└─", file=out)


def _flat(value: dict) -> str:
    kind = next(iter(value))
    v = value[kind]
    if kind in ("title", "rich_text"):
        return "".join(p["text"]["content"] for p in v)
    if kind == "select":
        return v["name"]
    if kind == "date":
        return v["start"]
    if kind == "relation":
        return ", ".join(r["id"] for r in v) + "  (→ Team Roster)"
    if kind == "people":
        return ", ".join(p["id"] for p in v)
    if kind == "checkbox":
        return "☑" if v else "☐"
    return "" if v is None else str(v)


def render_preview() -> str:
    """Human-readable view of what the journal would have done: Notion rows and Slack messages."""
    out: list[str] = []
    pages: dict[str, dict] = {}
    for i, e in enumerate(JOURNAL):
        if e["service"] == "Notion" and e["endpoint"] == "/pages":
            pages[f"#{i}"] = dict(e["payload"]["properties"])
        elif e["service"] == "Notion" and e["method"] == "PATCH" and pages:
            next(reversed(pages.values())).update(e["payload"]["properties"])
    for props in pages.values():
        out.append("Notion row")
        width = max(len(k) for k in props)
        out += [f"  {k.ljust(width)} │ {_flat(v)}" for k, v in props.items()]
        out.append("")
    for e in JOURNAL:
        if e["service"] == "Slack" and e["endpoint"] == "chat.postMessage":
            p = e["payload"]
            where = "  ↳ thread reply" if p.get("thread_ts") else f"{p['channel']}"
            out.append(f"Slack {where} — posted as \"{p.get('username')}\" {p.get('icon_emoji') or ''}")
            out += [f"  {line}" for line in p["text"].splitlines()]
            out.append("")
    return "\n".join(out).rstrip()
