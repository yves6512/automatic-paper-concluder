"""Create or update private HackMD notes from local Markdown reports."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

API = "https://api.hackmd.io/v1"


def load_token(project: Path) -> str:
    token = os.environ.get("HACKMD_API_TOKEN", "").strip()
    env_path = project / ".hackmd.env"
    if not token and env_path.exists():
        for raw in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key.strip() == "HACKMD_API_TOKEN":
                    token = value.strip().strip("\"'")
    if not token:
        raise RuntimeError("Missing HACKMD_API_TOKEN in .hackmd.env")
    return token


def request(token: str, method: str, path: str, payload: dict | None = None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API + path,
        data=body,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HackMD HTTP {exc.code}; check token, permissions, rate limits, and note length") from None


def hackmd_content(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig")
    title = path.stem
    marker = "# 論文分析報告"
    if marker in text:
        text = text.replace(marker, f"# {title}｜論文分析報告", 1)
    else:
        text = f"# {title}｜論文分析報告\n\n{text}"
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload Markdown reports to private HackMD notes")
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    project = args.project.resolve()
    state_path = project / ".hackmd-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    token = "" if args.dry_run else load_token(project)

    for raw_path in args.reports:
        path = raw_path.resolve()
        if path.suffix.lower() != ".md" or not path.is_file():
            raise RuntimeError(f"Not a Markdown report: {path}")
        content = hackmd_content(path)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        key = str(path)
        old = state.get(key, {})
        if old.get("sha256") == digest and old.get("url"):
            print(f"UNCHANGED\t{path.name}\t{old['url']}")
            continue
        if args.dry_run:
            print(f"DRY-RUN\t{path.name}\tchars={len(content)}\taction={'update' if old.get('note_id') else 'create'}")
            continue
        if old.get("note_id"):
            request(token, "PATCH", f"/notes/{old['note_id']}", {
                "content": content, "readPermission": "owner", "writePermission": "owner"
            })
            note_id = old["note_id"]
            url = old.get("url") or f"https://hackmd.io/{note_id}"
            action = "UPDATED"
        else:
            result = request(token, "POST", "/notes", {
                "content": content,
                "readPermission": "owner",
                "writePermission": "owner",
                "commentPermission": "disabled",
            })
            note_id = result["id"]
            url = result.get("publishLink") or f"https://hackmd.io/{result.get('shortId', note_id)}"
            action = "CREATED"
        state[key] = {"note_id": note_id, "url": url, "sha256": digest}
        temp = state_path.with_suffix(".tmp")
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(state_path)
        print(f"{action}\t{path.name}\t{url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
