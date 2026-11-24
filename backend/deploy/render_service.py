"""Deploy the UDC API (demo data) as a Render free web service.

    cd backend
    uv run --with truststore python deploy/render_service.py [--branch main]

Reads RENDER_API_KEY from the environment or backend/.env (create one at
https://dashboard.render.com/u/settings?add-api-key). The first run creates the
service (Docker, free plan, built from this repo's backend/ directory); later
runs update its branch and key and redeploy. Waits until the API answers, then
writes mcp-app/.env.deploy for the Alpic deploy. Secrets are never printed.

Free services sleep after 15 minutes without traffic and take about a minute
to wake, so the MCP app gets generous timeouts.
"""

import os
import sys
import time
from typing import Any

from common import demo_api_key, load_env, trust_system_certificates, write_mcp_env

API = "https://api.render.com/v1"
REPO = "https://github.com/rbelateche/universal-data-connector"
SERVICE_NAME = "udc-demo-api"
REGION = "frankfurt"
TERMINAL_FAILURES = {
    "build_failed",
    "update_failed",
    "canceled",
    "pre_deploy_failed",
    "deactivated",
}


class RenderError(RuntimeError):
    pass


def _check(r: Any) -> Any:
    if r.status_code >= 400:
        try:
            message = r.json().get("message", r.text)
        except ValueError:
            message = r.text
        raise RenderError(
            f"Render API {r.request.method} {r.request.url.path}: {r.status_code} {message}"
        )
    return r.json() if r.content else None


def _arg(argv: list[str], flag: str, default: str) -> str:
    return (
        argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default
    )


def main(argv: list[str]) -> int:
    trust_system_certificates()
    load_env()
    import httpx

    token = os.environ.get("RENDER_API_KEY")
    if not token:
        print(
            "RENDER_API_KEY is not set. Create one at "
            "https://dashboard.render.com/u/settings?add-api-key and add RENDER_API_KEY=... "
            "to backend/.env.",
            file=sys.stderr,
        )
        return 1
    branch = _arg(argv, "--branch", "main")
    api_key = demo_api_key()
    client = httpx.Client(
        base_url=API,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=30,
    )

    try:
        owner_id = os.environ.get("RENDER_OWNER_ID")
        if not owner_id:
            owners = _check(client.get("/owners", params={"limit": 20}))
            if not owners:
                raise RenderError("No Render workspace found for this API key.")
            owner = owners[0]["owner"]
            owner_id = owner["id"]
            print(f"Workspace: {owner.get('name', owner_id)}")

        found = _check(client.get("/services", params={"name": SERVICE_NAME, "ownerId": owner_id}))
        if found:
            service = found[0]["service"]
            sid = service["id"]
            print(f"Updating service {SERVICE_NAME} ({sid}) on branch {branch}")
            _check(client.patch(f"/services/{sid}", json={"branch": branch}))
            _check(client.put(f"/services/{sid}/env-vars/API_KEY", json={"value": api_key}))
            _check(client.post(f"/services/{sid}/deploys", json={}))
        else:
            print(f"Creating service {SERVICE_NAME} (free, {REGION}) from {REPO}@{branch}")
            created = _check(
                client.post(
                    "/services",
                    json={
                        "type": "web_service",
                        "name": SERVICE_NAME,
                        "ownerId": owner_id,
                        "repo": REPO,
                        "branch": branch,
                        "rootDir": "backend",
                        "autoDeploy": "yes",
                        "envVars": [{"key": "API_KEY", "value": api_key}],
                        "serviceDetails": {
                            "runtime": "docker",
                            "plan": "free",
                            "region": REGION,
                            "healthCheckPath": "/health",
                            "envSpecificDetails": {
                                "dockerfilePath": "./deploy/Dockerfile",
                                "dockerContext": ".",
                            },
                        },
                    },
                )
            )
            service = created["service"]
            sid = service["id"]

        url = service["serviceDetails"]["url"]
        print(f"Service URL: {url}")
        print("Waiting for the deploy (Docker build, a few minutes)...")
        last = None
        for _ in range(90):
            deploys = _check(client.get(f"/services/{sid}/deploys", params={"limit": 1}))
            status = deploys[0]["deploy"]["status"] if deploys else "pending"
            if status != last:
                print(f"  {status}")
                last = status
            if status == "live":
                break
            if status in TERMINAL_FAILURES:
                raise RenderError(
                    f"Deploy ended with status {status}; see the Render dashboard logs."
                )
            time.sleep(10)
        else:
            raise RenderError("Timed out waiting for the deploy; check the Render dashboard.")

        health = httpx.get(f"{url}/health", timeout=120)
        print(f"Health check: {health.status_code}")
    except RenderError as exc:
        print(exc, file=sys.stderr)
        return 1

    write_mcp_env(url, api_key, {"UDC_TIMEOUT_MS": "75000", "UDC_INFER_TIMEOUT_MS": "120000"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
