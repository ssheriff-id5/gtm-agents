"""Web lead triage plumbing: find unposted web-form leads, validate Claude's
assessment, and post it to #webform in a fixed format.

Division of labour (same as the rest of lib/): Claude decides the *judgement*
(spam verdict, research, offering match, scores) and writes it as JSON; this module
owns the *facts and format*. In particular the lead's own submission and the
approve link are taken from Zoho here, never from Claude's text, so the reviewer
always sees exactly what the person typed.

Dedupe: a lead counts as handled once a #webform message contains its Zoho link.
Slack is the record, so there is no extra state store to keep in sync.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lib import config
from lib.slack_client import SlackClient
from lib.zoho_client import ZohoClient, approval_url, lead_triage_config

VERDICTS = {"Lead": "🟢", "Not sure": "🟡", "Spam": "🔴"}
FITS = ("High", "Partial", "None")
LINKEDIN_CONFIDENCE = ("Confirmed", "Likely", "Not found")
OFFERINGS = ("Identify", "Monetize", "Enrich", "Augment", "Activate", "Expand", "Sync", "Optimize")
LEAD_LINK_RE = re.compile(r"/tab/Leads/(\d+)")


class AssessmentError(ValueError):
    pass


@dataclass
class PostReport:
    lead_id: str
    permalink: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _slack_cfg() -> dict:
    return lead_triage_config()["slack"]


def slack_client() -> SlackClient:
    return SlackClient(token_env=_slack_cfg()["token_env"])


def posted_lead_ids(slack: SlackClient, now: datetime | None = None) -> set[str]:
    """Lead IDs already posted in #webform within the lookback window (+1 day of slack)."""
    now = now or datetime.now(timezone.utc)
    days = lead_triage_config()["zoho"].get("lookback_days", 7) + 1
    oldest = f"{(now - timedelta(days=days)).timestamp():.6f}"
    ids: set[str] = set()
    for msg in slack.channel_history(_slack_cfg()["channel"], oldest):
        ids.update(LEAD_LINK_RE.findall(msg.get("text", "")))
    return ids


def pending_leads(zoho: ZohoClient | None = None, slack: SlackClient | None = None) -> list[dict]:
    """Web-form leads not yet posted to #webform, oldest first."""
    zoho = zoho or ZohoClient()
    slack = slack or slack_client()
    done = posted_lead_ids(slack)
    leads = [lead for lead in zoho.web_form_leads() if lead["id"] not in done]
    return sorted(leads, key=lambda lead: lead["Created_Time"])


def lead_brief(lead: dict) -> dict:
    """What Claude gets to work from: the form fields, verbatim, plus the approve link."""
    return {
        "lead_id": lead["id"],
        "first_name": lead.get("First_Name"),
        "last_name": lead.get("Last_Name"),
        "email": lead.get("Email"),
        "company": lead.get("Company"),
        "company_types": lead.get("Company_Types") or [],
        "title": lead.get("Designation"),
        "website": lead.get("Website"),
        "city": lead.get("City"),
        "country": lead.get("Primary_Country"),
        "lead_source": lead.get("Lead_Source"),
        "message": (lead.get("Description") or "").replace("\r\n", "\n").strip(),
        "created_time": lead.get("Created_Time"),
        "approve_url": approval_url(lead["id"]),
    }


# -- assessment ---------------------------------------------------------------

def validate_assessment(a: dict) -> dict:
    """Check the JSON Claude wrote. Raises AssessmentError listing every problem."""
    problems: list[str] = []

    def need(key: str, kind: type | tuple, where: dict = a, label: str = "") -> None:
        if not isinstance(where.get(key), kind) or where.get(key) in ("", []):
            problems.append(f"{label}{key} is missing or not a {getattr(kind, '__name__', kind)}")

    need("lead_id", str)
    if a.get("verdict") not in VERDICTS:
        problems.append(f"verdict must be one of {list(VERDICTS)}")
    need("verdict_reasons", list)
    need("take", str)
    score = a.get("score")
    if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 10:
        problems.append("score must be an integer 1–10")
    if a.get("verdict") == "Spam":
        if isinstance(score, int) and score > 2:
            problems.append("a Spam verdict can't score above 2")
    else:
        contact, company = a.get("contact"), a.get("company")
        if not isinstance(contact, dict):
            problems.append("contact is required unless verdict is Spam")
        else:
            if contact.get("linkedin_confidence") not in LINKEDIN_CONFIDENCE:
                problems.append(f"contact.linkedin_confidence must be one of {list(LINKEDIN_CONFIDENCE)}")
            elif contact["linkedin_confidence"] == "Not found" and contact.get("linkedin_url"):
                problems.append("contact.linkedin_url must be null when linkedin_confidence is 'Not found'")
            elif contact["linkedin_confidence"] != "Not found" and not contact.get("linkedin_url"):
                problems.append("contact.linkedin_url is required unless linkedin_confidence is 'Not found'")
        if not isinstance(company, dict):
            problems.append("company is required unless verdict is Spam")
        else:
            need("what_they_do", str, company, "company.")
        need("needs", str)
        if a.get("fit") not in FITS:
            problems.append(f"fit must be one of {list(FITS)}")
        need("fit_rationale", str)
        bad = [o for o in a.get("offerings") or [] if o not in OFFERINGS]
        if not isinstance(a.get("offerings"), list) or bad:
            problems.append(f"offerings must be a list drawn from {list(OFFERINGS)}" + (f" (got {bad})" if bad else ""))
        need("score_rationale", str)
    if problems:
        raise AssessmentError("Assessment is invalid:\n- " + "\n- ".join(problems))
    return a


def load_assessment(path: str | Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssessmentError(f"Can't read assessment {path}: {exc}") from exc
    return validate_assessment(data)


# -- formatting ---------------------------------------------------------------

def _esc(text: str | None) -> str:
    """Slack-escape text a website visitor typed, so it can't @channel or fake a link."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _quote(text: str) -> str:
    return "\n".join(f">{line}" if line else ">" for line in _esc(text).splitlines()) or ">(empty)"


def _who(brief: dict) -> str:
    name = " ".join(p for p in (brief["first_name"], brief["last_name"]) if p) or "(no name)"
    return _esc(f"{name} · {brief['email'] or 'no email'}")


def main_post(brief: dict, a: dict) -> str:
    """Channel message: verdict + score headline, our one-line take, the submission, the approve link."""
    where = _esc(", ".join(p for p in (brief["city"], brief["country"]) if p))
    types = _esc(", ".join(brief["company_types"])) or "no company type"
    company = _esc(brief["company"]) or "(no company)"
    head = f"{VERDICTS[a['verdict']]} *{a['verdict']} · {a['score']}/10* — *{company}*"
    head += f" ({where})" if where else ""
    lines = [
        head,
        f"{_who(brief)} · {types}",
        f"*Our take:* {a['take'].strip()}",
        "*What they wrote:*",
        _quote(brief["message"]),
        f"<{brief['approve_url']}|Review & approve in Zoho>",
    ]
    return "\n".join(lines)


def thread_post(brief: dict, a: dict) -> str:
    """Thread reply: the research behind the score."""
    out = ["*Why this verdict*"] + [f"• {r}" for r in a["verdict_reasons"]]
    if a["verdict"] != "Spam":
        c, co = a["contact"], a["company"]
        li = c.get("linkedin_url")
        li_text = "LinkedIn not found" if c["linkedin_confidence"] == "Not found" else \
            f"<{li}|LinkedIn> ({c['linkedin_confidence'].lower()} match)"
        out += ["", "*Contact*", f"• {li_text}"]
        for label, key in (("Role", "role"), ("Time in role", "tenure"), ("Responsibilities", "responsibilities")):
            out.append(f"• {label}: {c.get(key) or 'not found'}")
        out += ["", "*Company*", f"• {co['what_they_do']}"]
        for label, key in (("Website", "website"), ("Size", "size"), ("Type", "type")):
            if co.get(key):
                out.append(f"• {label}: {co[key]}")
        out += ["", "*What they need*", a["needs"],
                "", f"*Fit with ID5: {a['fit']}*" + (f" — {', '.join(a['offerings'])}" if a["offerings"] else ""),
                a["fit_rationale"],
                "", f"*Score {a['score']}/10*", a["score_rationale"]]
    sources = a.get("sources") or []
    if sources:
        out += ["", "*Sources:* " + " · ".join(f"<{u}|{i}>" for i, u in enumerate(sources, 1))]
    out += ["", "_Research and scores are Claude's assessment. The submission above is verbatim from Zoho._"]
    return "\n".join(out)


def post_assessment(brief: dict, a: dict, slack: SlackClient | None = None) -> PostReport:
    """Main post, then the research in its thread."""
    slack = slack or slack_client()
    report = PostReport(lead_id=brief["lead_id"])
    if a["lead_id"] != brief["lead_id"]:
        report.errors.append(f"assessment is for lead {a['lead_id']}, not {brief['lead_id']}")
        return report
    channel = _slack_cfg()["channel"]
    try:
        main = slack.post(channel, main_post(brief, a))
        report.permalink = main["permalink"]
    except Exception as exc:  # noqa: BLE001 — report, never swallow
        report.errors.append(f"Slack main post failed: {exc}")
        return report
    try:
        slack.post(main["channel"], thread_post(brief, a), thread_ts=main["ts"], with_permalink=False)
    except Exception as exc:  # noqa: BLE001
        report.errors.append(f"Slack thread reply failed (main post is up: {report.permalink}): {exc}")
    return report


def post_failure(detail: str, run_url: str | None = None, slack: SlackClient | None = None) -> None:
    """Make a broken run visible in #webform. Silent failure is the worst outcome."""
    slack = slack or slack_client()
    text = f"❌ Web lead triage failed — new leads may not have been posted. {detail.strip()}"
    if run_url:
        text += f" <{run_url}|Run log>"
    slack.post(_slack_cfg()["channel"], text, with_permalink=False)


def find_lead(lead_id: str, zoho: ZohoClient | None = None) -> dict:
    for lead in (zoho or ZohoClient()).web_form_leads():
        if lead["id"] == lead_id:
            return lead
    raise config.ConfigError(f"Lead {lead_id} is not a recent web-form lead in Zoho")
