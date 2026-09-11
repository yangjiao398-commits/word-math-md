"""Create or reuse a Supabase project, apply schema.sql, and write .env."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "sql" / "schema.sql"
ENV_PATH = ROOT / ".env"
PROJECT_NAME = "word-math-md"
REGION = "ap-southeast-1"


def run_json(args: list[str]) -> object:
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "command failed").strip())
    out = (proc.stdout or "").strip()
    return json.loads(out) if out else {}


def npx(*args: str) -> object:
    return run_json(["npx", "--yes", "supabase", *args, "-o", "json"])


def main() -> None:
    print("Checking Supabase login…")
    try:
        orgs = npx("orgs", "list")
    except RuntimeError as exc:
        raise SystemExit(
            "尚未登录 Supabase。请先在本机执行：\n"
            "  npx supabase login\n"
            "然后重新运行：python scripts/setup_supabase.py\n"
            f"详情：{exc}"
        ) from exc

    org_id = None
    if isinstance(orgs, list) and orgs:
        org_id = orgs[0].get("id") or orgs[0].get("org_id")
    elif isinstance(orgs, dict):
        items = orgs.get("orgs") or orgs.get("data") or []
        if items:
            org_id = items[0].get("id")
    if not org_id:
        raise SystemExit(f"找不到组织。CLI 输出：{orgs!r}")

    projects = npx("projects", "list")
    project = None
    rows = projects if isinstance(projects, list) else (projects.get("projects") or [])
    for row in rows:
        if row.get("name") == PROJECT_NAME:
            project = row
            break

    db_password = os.environ.get("SUPABASE_DB_PASSWORD") or secrets.token_urlsafe(18)
    if project is None:
        print(f"Creating project {PROJECT_NAME} in {REGION}…")
        project = npx(
            "projects",
            "create",
            PROJECT_NAME,
            "--org-id",
            str(org_id),
            "--db-password",
            db_password,
            "--region",
            REGION,
            "--size",
            "micro",
        )
        if isinstance(project, list):
            project = project[0]
        print("Waiting for the database to become ready…")
        ref = project.get("id") or project.get("ref")
        for _ in range(40):
            time.sleep(8)
            listed = npx("projects", "list")
            listed_rows = listed if isinstance(listed, list) else []
            hit = next((p for p in listed_rows if (p.get("id") or p.get("ref")) == ref), None)
            status = (hit or {}).get("status") or (hit or {}).get("database", {}).get("status")
            print(f"  status={status}")
            if status in {"ACTIVE_HEALTHY", "ACTIVE"}:
                project = hit or project
                break
        else:
            print("Project created but not healthy yet; continuing to fetch keys.")
    else:
        print(f"Reusing existing project {PROJECT_NAME}.")
        ref = project.get("id") or project.get("ref")

    ref = project.get("id") or project.get("ref")
    if not ref:
        raise SystemExit(f"No project ref in {project!r}")

    keys = npx("projects", "api-keys", "--project-ref", str(ref))
    anon = service = ""
    key_rows = keys if isinstance(keys, list) else (keys.get("keys") or keys.get("api_keys") or [])
    for item in key_rows:
        name = (item.get("name") or item.get("id") or "").lower()
        api = item.get("api_key") or item.get("key") or ""
        if "anon" in name or name == "publishable":
            anon = api
        if "service" in name:
            service = api
    if not service:
        raise SystemExit(f"Could not read service role key: {keys!r}")

    url = f"https://{ref}.supabase.co"
    print("Applying schema.sql…")
    proc = subprocess.run(
        [
            "npx",
            "--yes",
            "supabase",
            "db",
            "query",
            "--project-ref",
            str(ref),
            "--file",
            str(SCHEMA),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        # Older CLI may not support db query; write SQL for the dashboard.
        fail = (proc.stderr or proc.stdout or "").strip()
        print("CLI could not apply SQL automatically:")
        print(fail[-1500:])
        print(f"Open https://supabase.com/dashboard/project/{ref}/sql and run sql/schema.sql")
    else:
        print("Schema applied.")

    lines = {
        "PORT": "3010",
        "HOST": "0.0.0.0",
        "SUPABASE_URL": url,
        "SUPABASE_ANON_KEY": anon,
        "SUPABASE_SERVICE_ROLE_KEY": service,
        "SUPABASE_PROJECT_REF": str(ref),
        "SUPABASE_DB_PASSWORD": db_password,
    }
    existing: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                existing[k.strip()] = v.strip()
    existing.update(lines)
    ENV_PATH.write_text(
        "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {ENV_PATH}")
    try:
        import httpx

        httpx.post(
            f"{url}/storage/v1/bucket",
            headers={
                "Authorization": f"Bearer {service}",
                "apikey": service,
                "Content-Type": "application/json",
            },
            json={"id": "exam-assets", "name": "exam-assets", "public": True},
            timeout=30,
        )
        print("Storage bucket exam-assets ready.")
    except Exception as exc:
        print(f"Bucket create skipped or already exists: {exc}")
    print(f"Dashboard: https://supabase.com/dashboard/project/{ref}")


if __name__ == "__main__":
    main()
