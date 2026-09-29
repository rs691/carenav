"""
scripts/load_members.py
───────────────────────
Load or update the member roster (public.members) from a CSV so users can
identify themselves on the welcome screen.

CSV columns (header row required):
    member_number, group_number, first_name, last_name, coverage_tier, effective_date

- The plan (tenant) comes from plan_groups via group_number; rows with an
  unknown group are skipped and reported.
- Re-running updates existing members by member_number and never touches who
  has claimed a record.

Usage (repo root, venv active):
    python scripts/load_members.py path/to/members.csv --dry-run
    python scripts/load_members.py path/to/members.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.settings import settings  # noqa: E402

REQUIRED = ["member_number", "group_number", "first_name", "last_name"]
BATCH = 500


def _headers() -> dict[str, str]:
    key = settings.service_role_key
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _url(table: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}"


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"CSV is missing columns: {', '.join(missing)}")
        return list(reader)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the CareNav member roster from CSV")
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Validate only; write nothing")
    args = parser.parse_args()

    if not settings.supabase_url or not settings.service_role_key:
        raise SystemExit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")

    with httpx.Client(timeout=30.0) as client:
        resp = client.get(_url("plan_groups"), headers=_headers(), params={"select": "group_number,tenant_id"})
        resp.raise_for_status()
        groups = {g["group_number"]: g["tenant_id"] for g in resp.json()}

        records: list[dict] = []
        problems: list[str] = []
        for line, row in enumerate(read_rows(args.csv_path), start=2):
            values = {k: (row.get(k) or "").strip() for k in row}
            if any(not values.get(c) for c in REQUIRED):
                problems.append(f"line {line}: missing a required value")
                continue
            group = values["group_number"].upper()
            if group not in groups:
                problems.append(f"line {line}: unknown group {group}")
                continue
            records.append({
                "member_number": values["member_number"].upper(),
                "group_number": group,
                "tenant_id": groups[group],
                "first_name": values["first_name"],
                "last_name": values["last_name"],
                "coverage_tier": values.get("coverage_tier") or "Individual",
                "effective_date": values.get("effective_date") or None,
            })

        print(f"{len(records)} valid row(s), {len(problems)} skipped")
        for p in problems:
            print(f"  skipped {p}")
        if args.dry_run or not records:
            return

        for i in range(0, len(records), BATCH):
            resp = client.post(
                _url("members"),
                headers={**_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": "member_number"},
                json=records[i : i + BATCH],
            )
            if resp.status_code >= 400:
                raise SystemExit(f"Upload failed: {resp.status_code} {resp.text}")
        print(f"Loaded {len(records)} member(s).")


if __name__ == "__main__":
    main()
