"""Slack client: post as an AI employee, DM humans, read replies.

One Slack app / bot token for the whole team. ``chat:write.customize`` lets each
post carry the employee's own ``username`` and avatar, so messages read as
"Rick", not as the bot or as Satiesh.
"""
from __future__ import annotations

import time

import requests

from lib import config, dryrun
from lib.config import Employee

API = "https://slack.com/api"

STATUS_EMOJI = {
    "Success": "✅",
    "Partial": "⚠️",
    "Failed": "❌",
    "Blocked on human": "⏳",
}


def status_line(result: str, headline: str, link: str | None = None, link_label: str = "Open") -> str:
    """Main-post format from the handbook: '<emoji> <headline> <link>' — one line."""
    emoji = STATUS_EMOJI.get(result, "ℹ️")
    line = f"{emoji} {headline.strip()}"
    if link:
        line += f" <{link}|{link_label}>"
    return line


class SlackError(RuntimeError):
    pass


class SlackClient:
    def __init__(self, dry_run: bool | None = None, token: str | None = None):
        self.dry_run = config.is_dry_run() if dry_run is None else dry_run
        self.token = None if self.dry_run else (token or config.require_env("SLACK_BOT_TOKEN"))
        self.session = requests.Session()

    # -- plumbing --

    def _call(self, method: str, payload: dict, http: str = "POST") -> dict:
        if self.dry_run:
            dryrun.record("Slack", http, method, payload)
            return self._fake_response(method, payload)
        kwargs = {"json": payload} if http == "POST" else {"params": payload}
        resp = self.session.request(http, f"{API}/{method}", timeout=30,
                                    headers={"Authorization": f"Bearer {self.token}"}, **kwargs)
        data = resp.json()
        if not data.get("ok"):
            raise SlackError(f"Slack {method} failed: {data.get('error')} {data.get('response_metadata', '')}")
        return data

    @staticmethod
    def _fake_response(method: str, payload: dict) -> dict:
        ts = f"{time.time():.6f}"
        channel = payload.get("channel", "D0DRYRUN")
        if method == "chat.postMessage":
            return {"ok": True, "channel": channel, "ts": ts}
        if method == "chat.getPermalink":
            return {"ok": True, "permalink":
                    f"https://example.slack.com/archives/{channel.lstrip('#')}/p{payload['message_ts'].replace('.', '')}"}
        if method == "users.lookupByEmail":
            return {"ok": True, "user": {"id": "U0DRYRUN"}}
        if method == "conversations.open":
            return {"ok": True, "channel": {"id": "D0DRYRUN"}}
        return {"ok": True, "messages": []}

    def _identity(self, employee: Employee) -> dict:
        ident = {"username": employee.slack_username}
        if employee.icon_url:
            ident["icon_url"] = employee.icon_url
        elif employee.icon_emoji:
            ident["icon_emoji"] = employee.icon_emoji
        return ident

    # -- public API --

    def post_as(self, employee: Employee, channel: str, text: str, thread_ts: str | None = None,
                with_permalink: bool = True) -> dict:
        """Post as ``employee``. Returns {'channel', 'ts', 'permalink'}."""
        payload = {"channel": channel, "text": text, "unfurl_links": False, **self._identity(employee)}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        data = self._call("chat.postMessage", payload)
        return {"channel": data["channel"], "ts": data["ts"],
                "permalink": self.permalink(data["channel"], data["ts"]) if with_permalink else None}

    def permalink(self, channel: str, ts: str) -> str:
        return self._call("chat.getPermalink", {"channel": channel, "message_ts": ts}, http="GET")["permalink"]

    def user_id_for(self, human_key: str) -> str:
        human = config.humans().get(human_key)
        if not human:
            raise config.ConfigError(f"Unknown human '{human_key}' — add them to config/humans.yaml")
        if human.get("slack_user_id"):
            return human["slack_user_id"]
        if not human.get("email"):
            if self.dry_run:
                return "U0DRYRUN"
            raise config.ConfigError(f"config/humans.yaml: '{human_key}' needs an email or slack_user_id")
        return self._call("users.lookupByEmail", {"email": human["email"]}, http="GET")["user"]["id"]

    def dm(self, employee: Employee, human_key: str, text: str) -> dict:
        """DM a human as ``employee``. Returns {'channel', 'ts', 'permalink'}."""
        user_id = self.user_id_for(human_key)
        channel = self._call("conversations.open", {"users": user_id})["channel"]["id"]
        return self.post_as(employee, channel, text)

    def read_replies(self, channel: str, ts: str) -> list[dict]:
        """Replies in the thread under ``ts`` (excludes the parent message)."""
        msgs = self._call("conversations.replies", {"channel": channel, "ts": ts}, http="GET").get("messages", [])
        return [m for m in msgs if m.get("ts") != ts]

    def read_dm_since(self, channel: str, oldest_ts: str) -> list[dict]:
        """Top-level DM messages after ``oldest_ts`` — humans often reply outside the thread."""
        return self._call("conversations.history",
                          {"channel": channel, "oldest": oldest_ts, "inclusive": False}, http="GET").get("messages", [])
