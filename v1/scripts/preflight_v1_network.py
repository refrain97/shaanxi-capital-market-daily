#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
AMAC_HOST = "gs.amac.org.cn"
AMAC_FALLBACK_IPS = ["101.37.42.117", "47.98.56.138", "47.97.11.29", "47.96.173.133"]
FAKE_NETS = [ipaddress.ip_network("198.18.0.0/15")]


def run(cmd: list[str], *, timeout: int = 30, input_text: str | None = None) -> dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            input=input_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip()[:2000],
            "stderr": proc.stderr.strip()[:2000],
            "elapsedSec": round(time.time() - started, 3),
        }
    except Exception as exc:  # noqa: BLE001 - preflight must report instead of crashing.
        return {"ok": False, "error": repr(exc), "elapsedSec": round(time.time() - started, 3)}


def resolve_host(host: str) -> dict[str, Any]:
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        ips = sorted({item[4][0] for item in infos})
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "host": host, "ips": [], "error": repr(exc)}
    fake_ips = [ip for ip in ips if is_fake_ip(ip)]
    return {"ok": bool(ips), "host": host, "ips": ips, "fakeIps": fake_ips, "usesFakeIp": bool(fake_ips)}


def is_fake_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return any(ip in net for net in FAKE_NETS)


def doh_resolve(host: str) -> list[str]:
    ips: list[str] = []
    for url in (
        f"https://dns.alidns.com/resolve?name={host}&type=A",
        f"https://cloudflare-dns.com/dns-query?name={host}&type=A",
    ):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/dns-json", "User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            for answer in payload.get("Answer", []) or []:
                value = str(answer.get("data") or "")
                try:
                    ipaddress.ip_address(value)
                except ValueError:
                    continue
                if value and not is_fake_ip(value) and value not in ips:
                    ips.append(value)
        except Exception:
            continue
    for value in AMAC_FALLBACK_IPS:
        if value not in ips:
            ips.append(value)
    return ips


def curl_json(
    label: str,
    cmd: list[str],
    *,
    required: bool = True,
    timeout: int = 30,
    input_text: str | None = None,
) -> dict[str, Any]:
    if not shutil.which("curl"):
        return {"label": label, "ok": False, "required": required, "error": "curl not found"}
    result = run(cmd, timeout=timeout, input_text=input_text)
    result.update({"label": label, "required": required})
    return result


def amac_probe() -> dict[str, Any]:
    payload = json.dumps({}, separators=(",", ":"))
    base_cmd = [
        "curl",
        "-fsS",
        "--connect-timeout",
        "12",
        "--max-time",
        "25",
        "-H",
        "Content-Type: application/json",
        "-H",
        "Origin: https://gs.amac.org.cn",
        "-H",
        "Referer: https://gs.amac.org.cn/amac-infodisc/res/cancelled/manager/index.html",
        "-H",
        "X-Requested-With: XMLHttpRequest",
        "--data-binary",
        "@-",
        "https://gs.amac.org.cn/amac-infodisc/api/cancelled/manager?rand=&page=0&size=1",
    ]
    direct = curl_json("amac_api_direct", base_cmd, required=False, timeout=30, input_text=payload)
    if direct["ok"] and direct.get("stdout", "").startswith("{"):
        return {"ok": True, "mode": "direct", "direct": direct}

    module_probe = run(
        [
            sys.executable,
            "-c",
            (
                "import json, sys; "
                f"sys.path.insert(0, {str(ROOT / '陕西省证券私募日报v1' / 'scripts')!r}); "
                "import amac_security_private_daily as a; "
                "data = a.post_json('/cancelled/manager', {}, page=0, referer=a.CANCEL_REFERER); "
                "print(json.dumps({'rows': len(data.get('content') or []), 'totalElements': data.get('totalElements')}, ensure_ascii=False))"
            ),
        ],
        timeout=120,
    )
    if module_probe["ok"]:
        return {"ok": True, "mode": "module_fallback", "direct": direct, "module": module_probe}

    attempts = []
    for ip in doh_resolve(AMAC_HOST):
        cmd = base_cmd[:1] + ["--resolve", f"{AMAC_HOST}:443:{ip}"] + base_cmd[1:]
        attempt = curl_json(f"amac_api_resolve_{ip}", cmd, required=False, timeout=30, input_text=payload)
        attempts.append(attempt)
        if attempt["ok"] and attempt.get("stdout", "").startswith("{"):
            return {"ok": True, "mode": "curl_resolve", "ip": ip, "direct": direct, "attempts": attempts}
    return {"ok": False, "mode": "failed", "direct": direct, "attempts": attempts}


def git_remote_probe() -> dict[str, Any]:
    if not shutil.which("git"):
        return {"ok": False, "error": "git not found"}
    return run(["git", "ls-remote", "--heads", "origin", "gh-pages"], timeout=45)


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight network and deployment dependencies for the V1 daily run.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--write-log", action="store_true")
    args = parser.parse_args()

    probes: dict[str, Any] = {
        "date": args.date,
        "checkedAt": datetime.now().isoformat(timespec="seconds"),
        "environment": {
            "http_proxy": os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY") or "",
            "https_proxy": os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY") or "",
            "all_proxy": os.environ.get("all_proxy") or os.environ.get("ALL_PROXY") or "",
        },
        "proxy": run(["scutil", "--proxy"], timeout=10) if shutil.which("scutil") else {"ok": False, "error": "scutil not found"},
        "dns": {
            "cninfo": resolve_host("www.cninfo.com.cn"),
            "cninfo_static": resolve_host("static.cninfo.com.cn"),
            "amac": resolve_host(AMAC_HOST),
            "github_pages": resolve_host("refrain97.github.io"),
            "vercel": resolve_host("shaanxi-capital-market-daily.vercel.app"),
        },
    }
    probes["checks"] = {
        "cninfo_index": curl_json(
            "cninfo_index",
            ["curl", "-fsSI", "--connect-timeout", "10", "--max-time", "25", "https://www.cninfo.com.cn/new/index"],
        ),
        "cninfo_query": curl_json(
            "cninfo_query",
            [
                "curl",
                "-fsS",
                "--connect-timeout",
                "10",
                "--max-time",
                "25",
                "-H",
                "Content-Type: application/x-www-form-urlencoded",
                "-H",
                "Referer: https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
                "--data",
                "pageNum=1&pageSize=1&tabName=fulltext&seDate=2026-01-01~2026-01-02",
                "https://www.cninfo.com.cn/new/hisAnnouncement/query",
            ],
        ),
        "amac": amac_probe(),
        "vercel_site": curl_json(
            "vercel_site",
            ["curl", "-fsSI", "--connect-timeout", "10", "--max-time", "25", "https://shaanxi-capital-market-daily.vercel.app/v1/"],
        ),
        "github_pages_site": curl_json(
            "github_pages_site",
            ["curl", "-fsSI", "--connect-timeout", "10", "--max-time", "25", "https://refrain97.github.io/shaanxi-capital-market-daily/v1/"],
        ),
        "git_origin_gh_pages": git_remote_probe(),
        "vercel_cli": {"ok": bool(shutil.which("vercel") or shutil.which("npx"))},
        "chrome": {"ok": Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome").exists()},
    }

    required = ["cninfo_index", "cninfo_query", "amac", "vercel_site", "git_origin_gh_pages", "vercel_cli", "chrome"]
    failures = [name for name in required if not probes["checks"].get(name, {}).get("ok")]
    fake_dns = [name for name, item in probes["dns"].items() if item.get("usesFakeIp")]
    probes["summary"] = {
        "ok": not failures,
        "failures": failures,
        "fakeDnsHosts": fake_dns,
        "note": "AMAC direct access may fail on proxy fake-ip networks; ok if amac mode is direct, module_fallback, or curl_resolve.",
    }

    if args.write_log:
        log_dir = ROOT / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / f"preflight-{args.date}.json").write_text(json.dumps(probes, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(probes["summary"], ensure_ascii=False, indent=2))
    if fake_dns:
        print(f"preflight warning: fake-ip DNS detected for {', '.join(fake_dns)}", file=sys.stderr)
    if failures:
        print(f"preflight failed: {', '.join(failures)}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
