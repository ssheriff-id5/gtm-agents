"""Zoho CRM client: read-only access to web-form leads.

Uses a Zoho OAuth "self client" refresh token (ZOHO_CLIENT_ID / ZOHO_CLIENT_SECRET /
ZOHO_REFRESH_TOKEN) with scope ``ZohoCRM.modules.leads.READ``. Leads that are still
waiting for approval are returned by the normal Leads API, so nothing here depends
on anyone's mailbox.

In dry-run the client returns the fixture leads in ``tests/fixtures/web_leads.json``.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import requests

from lib import config, dryrun

LEAD_FIELDS = ("First_Name", "Last_Name", "Email", "Company", "Company_Types", "City",
               "Primary_Country", "Lead_Source", "Description", "Designation", "Website",
               "Created_Time", "Owner")
FIXTURE = config.REPO_ROOT / "tests" / "fixtures" / "web_leads.json"


class ZohoError(RuntimeError):
    pass


def lead_triage_config() -> dict:
    return config._load("lead_triage.yaml")


def approval_url(lead_id: str) -> str:
    """The link Zoho's 'Web to Lead Notification' email uses for 'waiting for your approval'."""
    z = lead_triage_config()["zoho"]
    return f"{z['web_url']}/crm/{z['org_domain']}/tab/Leads/{lead_id}"


class ZohoClient:
    def __init__(self, dry_run: bool | None = None):
        self.dry_run = config.is_dry_run() if dry_run is None else dry_run
        self.cfg = lead_triage_config()["zoho"]
        self.session = requests.Session()
        self._access_token: str | None = None
        if not self.dry_run:
            self.client_id = config.require_env("ZOHO_CLIENT_ID")
            self.client_secret = config.require_env("ZOHO_CLIENT_SECRET")
            self.refresh_token = config.require_env("ZOHO_REFRESH_TOKEN")

    def _token(self) -> str:
        if self._access_token is None:
            resp = self.session.post(f"{self.cfg['accounts_url']}/oauth/v2/token", timeout=30, data={
                "grant_type": "refresh_token", "client_id": self.client_id,
                "client_secret": self.client_secret, "refresh_token": self.refresh_token})
            data = resp.json()
            if "access_token" not in data:
                raise ZohoError(f"Zoho token refresh failed: {data.get('error', resp.status_code)}")
            self._access_token = data["access_token"]
        return self._access_token

    def recent_leads(self, per_page: int = 100) -> list[dict]:
        """Newest leads first (one page is plenty: web-form volume is a handful a day)."""
        params = {"fields": ",".join(LEAD_FIELDS), "sort_by": "Created_Time",
                  "sort_order": "desc", "per_page": per_page}
        if self.dry_run:
            dryrun.record("Zoho", "GET", "/Leads", params)
            return json.loads(FIXTURE.read_text(encoding="utf-8"))
        resp = self.session.get(f"{self.cfg['api_url']}/Leads", params=params, timeout=30,
                                headers={"Authorization": f"Zoho-oauthtoken {self._token()}"})
        if resp.status_code == 204:  # Zoho's "no records"
            return []
        data = resp.json()
        if resp.status_code != 200:
            raise ZohoError(f"Zoho GET /Leads failed: {resp.status_code} {data.get('code')} {data.get('message')}")
        return data.get("data", [])

    def web_form_leads(self, now: datetime | None = None) -> list[dict]:
        """Leads from the configured web-form sources, created within the lookback window."""
        now = now or datetime.now(timezone.utc)
        since = now - timedelta(days=self.cfg.get("lookback_days", 7))
        sources = set(self.cfg["lead_sources"])
        return [lead for lead in self.recent_leads()
                if lead.get("Lead_Source") in sources
                and datetime.fromisoformat(lead["Created_Time"]) >= since]
