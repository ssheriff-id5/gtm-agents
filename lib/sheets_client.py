"""Google Sheets client — interface only until Phase 2 (Pipeline Tracker port).

The two jobs it will own:
  * ``write_range`` — overwrite a tab with automated data.
  * ``mark_manual_columns`` — colour-code human-entered columns (sourcing-integrity rule).

Dry-run works today so the job contract can be exercised end-to-end; live mode
raises until a Google service account is wired in (GOOGLE_SA_JSON).
"""
from __future__ import annotations

from lib import config, dryrun

# Fill colour for human-entered / editorial columns. One colour, used everywhere,
# so readers learn "yellow = a person typed this".
MANUAL_INPUT_FILL = {"red": 1.0, "green": 0.95, "blue": 0.70}


class SheetsClient:
    def __init__(self, dry_run: bool | None = None):
        self.dry_run = config.is_dry_run() if dry_run is None else dry_run
        if not self.dry_run:
            raise NotImplementedError("Live Sheets access arrives in Phase 2 (needs GOOGLE_SA_JSON).")

    def write_range(self, spreadsheet_id: str, a1_range: str, rows: list[list]) -> None:
        dryrun.record("Sheets", "PUT", f"/spreadsheets/{spreadsheet_id}/values/{a1_range}",
                      {"valueInputOption": "USER_ENTERED", "rows": len(rows),
                       "preview": rows[:3]})

    def mark_manual_columns(self, spreadsheet_id: str, sheet_name: str, columns: list[str]) -> None:
        dryrun.record("Sheets", "POST", f"/spreadsheets/{spreadsheet_id}:batchUpdate",
                      {"sheet": sheet_name, "manual_columns": columns, "fill": MANUAL_INPUT_FILL})
