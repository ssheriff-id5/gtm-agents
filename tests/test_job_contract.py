import os
import unittest
from datetime import date
from unittest import mock

os.environ.pop("REVOPS_MODE", None)  # tests always run dry

from lib import config, dryrun  # noqa: E402
from lib.job_contract import finish_run, raise_input_request  # noqa: E402
from lib.notion_client import NotionClient, _chunks, work_log_title  # noqa: E402
from lib.slack_client import SlackClient, status_line  # noqa: E402

dryrun.QUIET = True


class ConfigTests(unittest.TestCase):
    def test_default_mode_is_dry_run(self):
        self.assertTrue(config.is_dry_run())

    def test_live_mode_without_token_is_a_hard_error(self):
        with mock.patch.dict(os.environ, {"REVOPS_MODE": "live", "NOTION_TOKEN": ""}):
            with self.assertRaises(config.ConfigError):
                NotionClient()

    def test_all_employees_load(self):
        self.assertEqual({e.key for e in config.all_employees()}, {"abby", "rick", "stevey"})


class NotionPayloadTests(unittest.TestCase):
    def test_work_log_properties_match_schema(self):
        props = NotionClient(dry_run=True).work_log_properties(
            employee_name="Rick", employee_page_id="pid", task="Pipeline Tracker",
            run_date=date(2026, 10, 12), result="Partial", summary="s", output_link="https://x")
        self.assertEqual(props["Run"]["title"][0]["text"]["content"], "Rick · Pipeline Tracker · 2026-10-12")
        self.assertEqual(props["Employee"], {"relation": [{"id": "pid"}]})
        self.assertEqual(props["Result"], {"select": {"name": "Partial"}})
        self.assertEqual(props["Run Date"], {"date": {"start": "2026-10-12"}})
        self.assertNotIn("Slack Link", props)

    def test_invalid_result_rejected(self):
        with self.assertRaises(ValueError):
            NotionClient(dry_run=True).work_log_properties(
                employee_name="Rick", employee_page_id="p", task="t", run_date=date.today(),
                result="Done", summary="s")

    def test_long_text_is_chunked(self):
        self.assertEqual(len(_chunks("x" * 4500)), 3)
        self.assertEqual(_chunks(""), [])

    def test_title_convention(self):
        self.assertEqual(work_log_title("Abby", "Daily review", date(2026, 1, 2)), "Abby · Daily review · 2026-01-02")


class SlackFormatTests(unittest.TestCase):
    def test_status_line(self):
        self.assertEqual(status_line("Success", "Done", "https://s"), "✅ Done <https://s|Open>")
        self.assertTrue(status_line("Blocked on human", "x").startswith("⏳"))


class FinishRunTests(unittest.TestCase):
    def setUp(self):
        dryrun.JOURNAL.clear()

    def test_dry_run_logs_posts_and_crosslinks(self):
        report = finish_run(employee="rick", task="Smoke", result="Success", headline="ok", summary="s",
                            notion=NotionClient(dry_run=True), slack=SlackClient(dry_run=True))
        self.assertTrue(report.ok, report.errors)
        calls = [(e["service"], e["endpoint"]) for e in dryrun.JOURNAL]
        self.assertEqual(calls[0], ("Notion", "/pages"))
        posts = [e for e in dryrun.JOURNAL if e["endpoint"] == "chat.postMessage"]
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0]["payload"]["username"], "Rick (AI Jr RevOps)")
        self.assertIn("thread_ts", posts[1]["payload"])
        self.assertEqual(calls[-1][0], "Notion")
        self.assertIn("Slack Link", dryrun.JOURNAL[-1]["payload"]["properties"])

    def test_notion_failure_still_posts_to_slack(self):
        notion = NotionClient(dry_run=True)
        notion.create_work_log = mock.Mock(side_effect=RuntimeError("notion down"))
        report = finish_run(employee="rick", task="T", result="Failed", headline="broke", summary="s",
                            notion=notion, slack=SlackClient(dry_run=True))
        self.assertFalse(report.ok)
        self.assertIsNotNone(report.slack_permalink)
        thread = [e for e in dryrun.JOURNAL if e["payload"].get("thread_ts")][0]
        self.assertIn("Could not write the Work Log", thread["payload"]["text"])

    def test_slack_failure_still_logs(self):
        slack = SlackClient(dry_run=True)
        slack.post_as = mock.Mock(side_effect=RuntimeError("slack down"))
        report = finish_run(employee="rick", task="T", result="Success", headline="h", summary="s",
                            notion=NotionClient(dry_run=True), slack=slack)
        self.assertIsNotNone(report.work_log_id)
        self.assertEqual(len(report.errors), 1)


class InputRequestTests(unittest.TestCase):
    def setUp(self):
        dryrun.JOURNAL.clear()

    def test_dm_then_row_with_thread_link(self):
        report = raise_input_request(employee="rick", ask="satiesh", task="Pipeline Tracker",
                                     question="Close month for Acme?", context="No close date",
                                     due=date(2026, 10, 15), notion=NotionClient(dry_run=True),
                                     slack=SlackClient(dry_run=True))
        self.assertTrue(report.ok, report.errors)
        row = [e for e in dryrun.JOURNAL if e["endpoint"] == "/pages"][0]["payload"]["properties"]
        self.assertEqual(row["Status"], {"select": {"name": "Open"}})
        self.assertEqual(row["Slack Thread"]["url"], report.slack_permalink)
        dm = [e for e in dryrun.JOURNAL if e["endpoint"] == "chat.postMessage"][0]["payload"]["text"]
        self.assertIn("Rick here (AI Jr RevOps)", dm)
        self.assertIn("Thursday 15 Oct", dm)


if __name__ == "__main__":
    unittest.main()
