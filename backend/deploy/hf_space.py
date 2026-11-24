"""Deploy the UDC API (demo data) to a Hugging Face Docker Space (needs HF PRO).

    cd backend
    uv run --with huggingface_hub --with truststore python deploy/hf_space.py [space-name]

Reads HF_TOKEN (a token with write access) from the environment or backend/.env.
The API key protecting the Space comes from UDC_DEMO_API_KEY, generated and
appended to backend/.env the first time. Secrets are never printed.

Writes mcp-app/.env.deploy (gitignored) with UDC_API_URL and UDC_API_KEY for
`alpic deploy --env-file .env.deploy`.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

from common import BACKEND, demo_api_key, load_env, trust_system_certificates, write_mcp_env

SPACE_FILES = BACKEND / "deploy" / "hf-space"
DEFAULT_SPACE = "udc-demo-api"


def _stage(folder: Path) -> None:
    shutil.copy(BACKEND / "pyproject.toml", folder / "pyproject.toml")
    shutil.copy(BACKEND / "uv.lock", folder / "uv.lock")
    shutil.copytree(
        BACKEND / "src",
        folder / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copy(BACKEND / "deploy" / "Dockerfile", folder / "Dockerfile")
    shutil.copy(SPACE_FILES / "README.md", folder / "README.md")


def main(argv: list[str]) -> int:
    trust_system_certificates()
    load_env()
    from huggingface_hub import HfApi

    token = os.environ.get("HF_TOKEN")
    if not token:
        print(
            "HF_TOKEN is not set. Create a token with write access at "
            "https://huggingface.co/settings/tokens and add HF_TOKEN=... to backend/.env.",
            file=sys.stderr,
        )
        return 1

    api = HfApi(token=token)
    owner = api.whoami()["name"]
    positional = [a for a in argv[1:] if not a.startswith("--")]
    name = positional[0] if positional else DEFAULT_SPACE
    repo_id = f"{owner}/{name}"
    api_key = demo_api_key()

    api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True)
    api.add_space_secret(repo_id, "API_KEY", api_key)
    if "--with-anthropic-key" in argv and os.environ.get("ANTHROPIC_API_KEY"):
        # Enables live inference (refresh=true) on the Space, billed to your key.
        api.add_space_secret(repo_id, "ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY"])

    with tempfile.TemporaryDirectory() as tmp:
        _stage(Path(tmp))
        api.upload_folder(
            folder_path=tmp,
            repo_id=repo_id,
            repo_type="space",
            commit_message="Deploy UDC API (demo)",
        )

    host = getattr(api.space_info(repo_id), "host", None) or (
        "https://" + f"{owner}-{name}".lower().replace("_", "-").replace(".", "-") + ".hf.space"
    )
    write_mcp_env(host, api_key)
    print(f"Space:    https://huggingface.co/spaces/{repo_id}")
    print(f"API URL:  {host}   (building; first start takes a few minutes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
