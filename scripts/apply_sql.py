"""Apply a SQL file via Supabase Management API. Usage: python scripts/apply_sql.py sql/foo.sql"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python scripts/apply_sql.py sql/migrate.sql")
    sql_path = Path(sys.argv[1])
    if not sql_path.is_absolute():
        sql_path = ROOT / sql_path
    token = os.environ.get("SUPABASE_ACCESS_TOKEN") or ""
    ref = os.environ.get("SUPABASE_PROJECT_REF") or ""
    if not token or not ref:
        raise SystemExit("缺少 SUPABASE_ACCESS_TOKEN 或 SUPABASE_PROJECT_REF")
    sql = sql_path.read_text(encoding="utf-8")
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{ref}/database/query",
        data=json.dumps({"query": sql}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"SQL failed HTTP {exc.code}: {detail[:400]}") from exc
    print(f"applied {sql_path.name} ok {raw[:200]}")


if __name__ == "__main__":
    main()
