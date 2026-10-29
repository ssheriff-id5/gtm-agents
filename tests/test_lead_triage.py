import copy
import os
import unittest
from datetime import datetime, timezone
from unittest import mock

os.environ.pop("REVOPS_MODE", None)  # tests always run dry

from lib import dryrun, lead_triage  # noqa: E402
from lib.slack_client import SlackClient  # noqa: E402
from lib.zoho_client import ZohoClient, approval_url  # noqa: E402

dryrun.QUIET = True

SPAM = {"lead_id": "900000000000000001", "verdict": "Spam", "score": 1,
        "verdict_reasons": ["Pitches digital signage software to ID5"],
        "take": "Vendor pitch, not a buyer."}

LEAD = {
    "lead_id": "900000000000000002", "verdict": "Lead", "score": 8,
    "verdict_reasons": ["Asks about universal IDs"], "take": "UK publisher with CTV apps; Identify fit.",
    "contact": {"linkedin_url": None, "linkedin_confidence": "Not found", "role": None,
                "tenure": None, "responsibilities": None},
    "company": {"what_they_do": "12 news sites and two CTV apps", "type": "Publisher"},
    "needs": "Safari and CTV addressability", "offerings": ["Identify", "Enrich"], "fit": "High",
    "fit_rationale": "Identify covers web and CTV.", "score_rationale": "High fit, contact unverified.",
    "sources": ["https://example.test/about"],
}


def brief(lead_id):
    return lead_triage.lead_brief(lead_triage.find_lead(lead_id, ZohoClient(dry_run=True)))


class ZohoTests(unittest.TestCase):
    def test_approval_url_matches_zoho_email_link(self):
        self.assertEqual(approval_url("162380000095421001"),
                         "https://crm.zoho.eu/crm/org20065454766/tab/Leads/162380000095421001")

    def test_only_recent_web_form_leads(self):
        ids = [lead["id"] for lead in ZohoClient(dry_run=True).web_form_leads(
            now=datetime(2099, 1, 2, tzinfo=timezone.utc))]
        self.assertEqual(ids, ["900000000000000001", "900000000000000002"])  # trade-show lead dropped
        self.assertEqual(ZohoClient(dry_run=True).web_form_leads(
            now=datetime(2099, 3, 1, tzinfo=timezone.utc)), [])  # outside lookback

    def test_live_without_creds_is_a_hard_error(self):
        from lib import config
        with mock.patch.dict(os.environ, {"REVOPS_MODE": "live", "ZOHO_CLIENT_ID": ""}):
            with self.assertRaises(config.ConfigError):
                ZohoClient()


class PendingTests(unittest.TestCase):
    def test_already_posted_leads_are_skipped(self):
        slack = SlackClient(dry_run=True)
        posted = [{"text": f"🔴 Spam … <{approval_url('900000000000000001')}|Review & approve in Zoho>"}]
        with mock.patch.object(slack, "channel_history", return_value=posted):
            pending = lead_triage.pending_leads(ZohoClient(dry_run=True), slack)
        self.assertEqual([lead["id"] for lead in pending], ["900000000000000002"])


class AssessmentTests(unittest.TestCase):
    def test_valid_assessments_pass(self):
        lead_triage.validate_assessment(copy.deepcopy(SPAM))
        lead_triage.validate_assessment(copy.deepcopy(LEAD))

    def assertInvalid(self, a, fragment):
        with self.assertRaises(lead_triage.AssessmentError) as ctx:
            lead_triage.validate_assessment(a)
        self.assertIn(fragment, str(ctx.exception))

    def test_rules(self):
        self.assertInvalid({**SPAM, "score": 11}, "score must be an integer")
        self.assertInvalid({**SPAM, "score": 7}, "Spam verdict can't score above 2")
        self.assertInvalid({**SPAM, "verdict": "Maybe"}, "verdict must be one of")
        self.assertInvalid({**LEAD, "fit": "Great"}, "fit must be one of")
        self.assertInvalid({**LEAD, "offerings": ["Magic"]}, "offerings must be a list")
        no_company = {k: v for k, v in LEAD.items() if k != "company"}
        self.assertInvalid(no_company, "company is required")

    def test_linkedin_never_guessed(self):
        a = copy.deepcopy(LEAD)
        a["contact"]["linkedin_url"] = "https://www.linkedin.com/in/someone"
        self.assertInvalid(a, "must be null when linkedin_confidence is 'Not found'")
        a["contact"]["linkedin_confidence"] = "Confirmed"
        a["contact"]["linkedin_url"] = None
        self.assertInvalid(a, "linkedin_url is required")


class PostTests(unittest.TestCase):
    def setUp(self):
        dryrun.JOURNAL.clear()

    def test_post_has_verbatim_message_and_approve_link(self):
        b = brief("900000000000000002")
        report = lead_triage.post_assessment(b, LEAD, SlackClient(dry_run=True))
        self.assertTrue(report.ok, report.errors)
        main, thread = [e["payload"] for e in dryrun.JOURNAL if e["endpoint"] == "chat.postMessage"]
        self.assertEqual(main["channel"], "C0CCE3370AD")
        self.assertNotIn("username", main)  # posts as the token owner (Satiesh), not a persona
        self.assertTrue(main["text"].startswith("🟢 *Lead · 8/10* — *Example News Group* (London, United Kingdom)"))
        self.assertIn(">Hi, we run 12 news sites", main["text"])
        self.assertIn(f"<{approval_url('900000000000000002')}|Review & approve in Zoho>", main["text"])
        self.assertIn("thread_ts", thread)
        self.assertIn("LinkedIn not found", thread["text"])
        self.assertIn("*Fit with ID5: High* — Identify, Enrich", thread["text"])

    def test_spam_thread_is_short(self):
        lead_triage.post_assessment(brief("900000000000000001"), SPAM, SlackClient(dry_run=True))
        thread = [e["payload"] for e in dryrun.JOURNAL if e["endpoint"] == "chat.postMessage"][1]
        self.assertNotIn("*Contact*", thread["text"])

    def test_visitor_text_cannot_ping_or_fake_links(self):
        b = brief("900000000000000002")
        b["message"] = "<!channel> click <https://evil.test|Approve>"
        text = lead_triage.main_post(b, LEAD)
        self.assertNotIn("<!channel>", text)
        self.assertIn("&lt;!channel&gt;", text)

    def test_mismatched_lead_id_refused(self):
        b = brief("900000000000000001")
        dryrun.JOURNAL.clear()
        report = lead_triage.post_assessment(b, LEAD, SlackClient(dry_run=True))
        self.assertFalse(report.ok)
        self.assertEqual(dryrun.JOURNAL, [])  # nothing posted


class ConnectorModeTests(unittest.TestCase):
    """Scheduled runs read Zoho and #webform through the claude.ai connectors and save them to files."""

    def setUp(self):
        import json
        import tempfile
        from lib.zoho_client import FIXTURE
        self.dir = tempfile.mkdtemp()
        self.zoho = os.path.join(self.dir, "zoho.json")
        with open(self.zoho, "w") as fh:  # the connector wraps records as {"status":..,"data":{"data":[..]}}
            json.dump({"status": "success", "data": {"data": json.loads(FIXTURE.read_text())}}, fh)
        self.posted = os.path.join(self.dir, "webform.txt")

    def _pending(self, history: str):
        with open(self.posted, "w") as fh:
            fh.write(history)
        return [lead["id"] for lead in lead_triage.pending_from_files(self.zoho, self.posted)]

    def test_dedupe_on_plain_lead_id(self):
        self.assertEqual(self._pending("Satiesh joined the channel"),
                         ["900000000000000002", "900000000000000001"])
        # links may be rendered as plain labels; the plain "Zoho lead ID" still dedupes
        self.assertEqual(self._pending("Review & approve in Zoho · Zoho lead ID: 900000000000000002"),
                         ["900000000000000001"])

    def test_render_markdown_for_connector(self):
        b = lead_triage.lead_brief(lead_triage.find_lead("900000000000000002", leads_file=self.zoho))
        out = lead_triage.render(b, LEAD, "markdown")
        self.assertEqual(out["channel"], "C0CCE3370AD")
        self.assertTrue(out["main"].startswith("🟢 **Lead · 8/10** — **Example News Group**"))
        self.assertIn("```\nHi, we run 12 news sites", out["main"])
        self.assertIn(f"[Review & approve in Zoho]({approval_url('900000000000000002')}) · "
                      "Zoho lead ID: 900000000000000002", out["main"])
        self.assertEqual(lead_triage.posted_lead_ids_in_text(out["main"]), {"900000000000000002"})

    def test_markdown_neutralises_visitor_text(self):
        b = lead_triage.lead_brief(lead_triage.find_lead("900000000000000002", leads_file=self.zoho))
        b["company"] = "@channel [Approve](https://evil.test)"
        b["message"] = "```\n@here"
        main = lead_triage.main_post(b, LEAD, "markdown")
        self.assertNotIn("[Approve](https://evil.test)", main)
        self.assertNotIn("@channel", main)
        self.assertEqual(main.count("```"), 2)  # visitor can't close the code block


if __name__ == "__main__":
    unittest.main()
