"""Web lead triage plumbing: find unposted web-form leads, validate Claude's
assessment, and post it to #webform in a fixed format.

Division of labour (same as the rest of lib/): Claude decides the *judgement*
(spam verdict, research, offering match, scores) and writes it as JSON; this module
owns the *facts and format*. In particular the lead's own submission and the
approve link are taken from Zoho here, never from Claude's text, so the reviewer
always sees exactly what the person typed.

Dedupe: a lead counts as handled once a #webform message contains its Zoho lead ID.
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
from zoneinfo import ZoneInfo

from lib.zoho_client import (ZohoClient, approval_url, filter_web_form, lead_triage_config,
                             load_leads_files)

VERDICTS = {"Lead": "🟢", "Not sure": "🟡", "Spam": "🔴"}
FITS = ("High", "Partial", "None")
LINKEDIN_CONFIDENCE = ("Confirmed", "Likely", "Not found")
OFFERINGS = ("Identify", "Monetize", "Enrich", "Augment", "Activate", "Expand", "Sync", "Optimize")
# A posted lead carries its Zoho link and a plain "Zoho lead ID: <id>" (the plain ID
# survives however a reader renders links).
LEAD_ID_RE = re.compile(r"(?:/tab/Leads/|Zoho lead ID:\W*)(\d{12,})")
# Each post also shows when the lead came in. The newest one in #webform is the
# "last lead pulled": the next run pulls everything submitted after it.
RECEIVED_RE = re.compile(r"Received:\W*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) ET")
ET = ZoneInfo("America/New_York")


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
        ids.update(LEAD_ID_RE.findall(msg.get("text", "")))
    return ids


def posted_lead_ids_in_text(text: str) -> set[str]:
    """Same, from #webform history saved as text (e.g. the Slack connector's read_channel output)."""
    return set(LEAD_ID_RE.findall(text))


def received_label(created_time: str) -> str:
    """'2026-10-28 10:26 ET (Wed)': when the lead came in, in US Eastern time."""
    t = datetime.fromisoformat(created_time).astimezone(ET)
    return f"{t:%Y-%m-%d %H:%M} ET ({t:%a})"


def last_received_in_text(text: str) -> datetime | None:
    """Submission time of the newest lead already posted in #webform, if any post shows one."""
    times = [datetime.strptime(m, "%Y-%m-%d %H:%M").replace(tzinfo=ET) for m in RECEIVED_RE.findall(text)]
    return max(times) if times else None


def pull_since(posted_text: str, now: datetime | None = None) -> datetime:
    """How far back to pull from Zoho: from the last lead posted, and never less than the
    lookback window, so a lead that failed to post is retried. (The go-live cutoff is
    applied on top by filter_web_form.)"""
    now = now or datetime.now(timezone.utc)
    window = now - timedelta(days=lead_triage_config()["zoho"].get("lookback_days", 7))
    last = last_received_in_text(posted_text)
    return min(last, window) if last else window


def pending_from_files(leads_files, posted_text_file: str | Path, now: datetime | None = None) -> list[dict]:
    """pending_leads() for connector runs: Zoho pages and #webform history saved to files."""
    posted = Path(posted_text_file).read_text(encoding="utf-8")
    done = posted_lead_ids_in_text(posted)
    leads = filter_web_form(load_leads_files(leads_files), now=now, since=pull_since(posted, now))
    return sorted((lead for lead in leads if lead["id"] not in done), key=lambda lead: lead["Created_Time"])


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
        "received": received_label(lead["Created_Time"]),
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
#
# Two output styles, same content:
#   "mrkdwn"   — Slack's own markup, for posting through the Slack API (lib.slack_client)
#   "markdown" — standard markdown, for posting through the claude.ai Slack connector,
#                which converts markdown itself

@dataclass(frozen=True)
class _Style:
    name: str

    def bold(self, s: str) -> str:
        return f"*{s}*" if self.name == "mrkdwn" else f"**{s}**"

    def italic(self, s: str) -> str:
        return f"_{s}_"

    def link(self, url: str, label: str) -> str:
        return f"<{url}|{label}>" if self.name == "mrkdwn" else f"[{label}]({url})"

    def esc(self, text: str | None) -> str:
        """Neutralise text a website visitor typed, so it can't @channel or fake a link."""
        text = text or ""
        if self.name == "mrkdwn":
            return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace("<", "‹").replace(">", "›").replace("[", "⁅").replace("]", "⁆")
        return re.sub(r"@(channel|here|everyone)\b", "@​\\1", text)

    def submission(self, text: str) -> str:
        """The lead's message, verbatim: a quote (mrkdwn) or a code block (markdown, renders nothing)."""
        if self.name == "mrkdwn":
            return "\n".join(f">{line}" if line else ">" for line in self.esc(text).splitlines()) or ">(empty)"
        return "```\n" + (text or "(empty)").replace("```", "ʼʼʼ") + "\n```"


STYLES = {"mrkdwn": _Style("mrkdwn"), "markdown": _Style("markdown")}


def _who(brief: dict, st: _Style) -> str:
    name = " ".join(p for p in (brief["first_name"], brief["last_name"]) if p) or "(no name)"
    return st.esc(f"{name} · {brief['email'] or 'no email'}")


def main_post(brief: dict, a: dict, style: str = "mrkdwn") -> str:
    """Channel message: verdict + score headline, our one-line take, the submission, the approve link."""
    st = STYLES[style]
    where = st.esc(", ".join(p for p in (brief["city"], brief["country"]) if p))
    types = st.esc(", ".join(brief["company_types"])) or "no company type"
    company = st.esc(brief["company"]) or "(no company)"
    verdict = f"{a['verdict']} · {a['score']}/10"
    head = f"{VERDICTS[a['verdict']]} {st.bold(verdict)} — {st.bold(company)}"
    head += f" ({where})" if where else ""
    lines = [
        head,
        f"{_who(brief, st)} · {types}",
        f"🕒 Received: {brief['received']}",
        f"{st.bold('Our take:')} {a['take'].strip()}",
        st.bold("What they wrote:"),
        st.submission(brief["message"]),
        f"{st.link(brief['approve_url'], 'Review & approve in Zoho')} · Zoho lead ID: {brief['lead_id']}",
    ]
    return "\n".join(lines)


def thread_post(brief: dict, a: dict, style: str = "mrkdwn") -> str:
    """Thread reply: the research behind the score."""
    st = STYLES[style]
    out = [st.bold("Why this verdict")] + [f"• {r}" for r in a["verdict_reasons"]]
    if a["verdict"] != "Spam":
        c, co = a["contact"], a["company"]
        li_text = "LinkedIn not found" if c["linkedin_confidence"] == "Not found" else \
            f"{st.link(c['linkedin_url'], 'LinkedIn')} ({c['linkedin_confidence'].lower()} match)"
        out += ["", st.bold("Contact"), f"• {li_text}"]
        for label, key in (("Role", "role"), ("Time in role", "tenure"), ("Responsibilities", "responsibilities")):
            out.append(f"• {label}: {c.get(key) or 'not found'}")
        out += ["", st.bold("Company"), f"• {co['what_they_do']}"]
        for label, key in (("Website", "website"), ("Size", "size"), ("Type", "type")):
            if co.get(key):
                out.append(f"• {label}: {co[key]}")
        fit = st.bold(f"Fit with ID5: {a['fit']}") + (f" — {', '.join(a['offerings'])}" if a["offerings"] else "")
        out += ["", st.bold("What they need"), a["needs"],
                "", fit, a["fit_rationale"],
                "", st.bold(f"Score {a['score']}/10"), a["score_rationale"]]
    sources = a.get("sources") or []
    if sources:
        out += ["", st.bold("Sources:") + " " + " · ".join(st.link(u, str(i)) for i, u in enumerate(sources, 1))]
    out += ["", st.italic("Research and scores are Claude's assessment. The submission above is verbatim from Zoho.")]
    return "\n".join(out)


def render(brief: dict, a: dict, style: str = "markdown") -> dict:
    """Both messages, for posting through the Slack connector."""
    if a["lead_id"] != brief["lead_id"]:
        raise AssessmentError(f"assessment is for lead {a['lead_id']}, not {brief['lead_id']}")
    return {"channel": _slack_cfg()["channel"], "lead_id": brief["lead_id"],
            "main": main_post(brief, a, style), "thread": thread_post(brief, a, style)}


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


def find_lead(lead_id: str, zoho: ZohoClient | None = None, leads_file: str | Path | None = None) -> dict:
    leads = load_leads_files(leads_file) if leads_file else (zoho or ZohoClient()).web_form_leads()
    for lead in leads:
        if lead["id"] == lead_id:
            return lead
    raise config.ConfigError(f"Lead {lead_id} is not a recent web-form lead in Zoho")
