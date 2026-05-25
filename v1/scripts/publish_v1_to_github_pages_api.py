#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


API = "https://api.github.com"


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def credential_token() -> str:
    env_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if env_token:
        return env_token
    proc = subprocess.run(
        ["git", "credential-osxkeychain", "get"],
        input="protocol=https\nhost=github.com\n\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        return ""
    for line in proc.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    return ""


def request(method: str, path: str, token: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "shaanxi-capital-market-daily-publisher",
        },
    )
    for attempt in range(1, 6):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = resp.read()
            return json.loads(body.decode("utf-8")) if body else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code not in {500, 502, 503, 504} or attempt == 5:
                raise SystemExit(f"GitHub API {method} {path} failed: HTTP {exc.code} {detail}") from exc
        except urllib.error.URLError as exc:
            if attempt == 5:
                raise SystemExit(f"GitHub API {method} {path} failed after retries: {exc}") from exc
        time.sleep(2 * attempt)
    raise SystemExit(f"GitHub API {method} {path} failed unexpectedly")


def current_tree(owner: str, repo: str, branch: str, token: str) -> tuple[str, str, dict[str, str]]:
    ref = request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{branch}", token)
    commit_sha = ref["object"]["sha"]  # type: ignore[index]
    commit = request("GET", f"/repos/{owner}/{repo}/git/commits/{commit_sha}", token)
    tree_sha = commit["tree"]["sha"]  # type: ignore[index]
    tree = request("GET", f"/repos/{owner}/{repo}/git/trees/{tree_sha}?recursive=1", token)
    existing: dict[str, str] = {}
    for item in tree.get("tree", []):
        if isinstance(item, dict) and item.get("type") == "blob":
            existing[str(item["path"])] = str(item["sha"])
    return str(commit_sha), str(tree_sha), existing


def create_blob(owner: str, repo: str, token: str, data: bytes) -> str:
    payload = {
        "content": base64.b64encode(data).decode("ascii"),
        "encoding": "base64",
    }
    blob = request("POST", f"/repos/{owner}/{repo}/git/blobs", token, payload)
    return str(blob["sha"])


def iter_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and ".git" not in path.parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish packaged static site to GitHub Pages via GitHub API.")
    parser.add_argument("--dist", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--repo", default="refrain97/shaanxi-capital-market-daily")
    parser.add_argument("--branch", default="gh-pages")
    args = parser.parse_args()

    dist = Path(args.dist).resolve()
    if not dist.exists():
        raise SystemExit(f"dist folder not found: {dist}")
    token = credential_token()
    if not token:
        raise SystemExit("GitHub token not found in GITHUB_TOKEN/GH_TOKEN or macOS keychain.")

    owner, repo = args.repo.split("/", 1)
    parent_sha, base_tree_sha, existing = current_tree(owner, repo, args.branch, token)

    entries: list[dict[str, object]] = []
    uploaded = reused = 0
    packaged_paths: set[str] = set()
    files = iter_files(dist)
    total = len(files)
    for index, path in enumerate(files, start=1):
        rel = path.relative_to(dist).as_posix()
        packaged_paths.add(rel)
        data = path.read_bytes()
        local_sha = git_blob_sha(data)
        if existing.get(rel) == local_sha:
            blob_sha = local_sha
            reused += 1
        else:
            blob_sha = create_blob(owner, repo, token, data)
            uploaded += 1
        entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob_sha})
        if index % 50 == 0 or index == total:
            print(f"prepared {index}/{total} files; reused={reused} uploaded={uploaded}", flush=True)
    for rel in sorted(set(existing) - packaged_paths):
        entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": None})

    tree = request(
        "POST",
        f"/repos/{owner}/{repo}/git/trees",
        token,
        {"base_tree": base_tree_sha, "tree": entries},
    )
    tree_sha = str(tree["sha"])
    if tree_sha == base_tree_sha:
        print(f"GitHub Pages already matches packaged site. reused={reused} uploaded={uploaded}")
        return 0

    commit = request(
        "POST",
        f"/repos/{owner}/{repo}/git/commits",
        token,
        {
            "message": f"Deploy {args.date} reports to GitHub Pages",
            "tree": tree_sha,
            "parents": [parent_sha],
        },
    )
    new_commit_sha = str(commit["sha"])
    request(
        "PATCH",
        f"/repos/{owner}/{repo}/git/refs/heads/{args.branch}",
        token,
        {"sha": new_commit_sha, "force": False},
    )
    print(f"GitHub Pages API publish: commit={new_commit_sha} reused={reused} uploaded={uploaded}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
