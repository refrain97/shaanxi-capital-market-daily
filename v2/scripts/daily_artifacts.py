#!/usr/bin/env python3
"""Create, archive and optionally upload the V2 daily image edition.

PNG files are deliberately *ephemeral*.  The immutable daily production
snapshot and the public archive index are the records; images live only in a
non-versioned staging directory until GitHub Pages confirms them.  IMA retries
rebuild from the frozen snapshot and erase the temporary PNG after every try.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from PIL import Image, ImageChops, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / "v2"
TZ = ZoneInfo("Asia/Shanghai")
INDEX_PATH = V2 / "data" / "daily-image-archive.json"
RELEASES = V2 / "data" / "releases"
STAGING = V2 / ".runtime" / "daily-images"
PUBLIC_PREFIX = "archive/daily"
LIVE_ROOT = "https://refrain97.github.io/shaanxi-capital-market-daily"
FONT_PATHS = (
    Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/System/Library/Fonts/STHeiti Light.ttc"),
)
CHANNELS = {
    "listed": {
        "title": "陕西上市公司早报",
        "label": "上市公司",
        "file": "V2陕西上市公司早报",
        "accent": "#A62F31",
    },
    "private": {
        "title": "陕西证券私募行业动态日报",
        "label": "证券私募",
        "file": "V2证券私募行业动态日报",
        "accent": "#8A692B",
    },
    "ma": {
        "title": "陕西收并购日报",
        "label": "收并购",
        "file": "V2陕西收并购日报",
        "accent": "#8E3033",
    },
    "tender": {
        "title": "陕西金融招投标日报",
        "label": "金融招投标",
        "file": "V2陕西金融招投标日报",
        "accent": "#275E88",
    },
}
def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def zh_date(day: str) -> str:
    year, month, date = (int(part) for part in day.split("-"))
    return f"{year}年{month}月{date}日"


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in FONT_PATHS:
        if candidate.is_file():
            try:
                return ImageFont.truetype(str(candidate), size=size, index=0)
            except OSError:
                continue
    return ImageFont.load_default()


def text_width(draw: ImageDraw.ImageDraw, text: str, value: ImageFont.ImageFont) -> int:
    return int(draw.textbbox((0, 0), text, font=value)[2])


def wrap(draw: ImageDraw.ImageDraw, value: str, value_font: ImageFont.ImageFont, width: int, max_lines: int) -> list[str]:
    value = " ".join(str(value or "").replace("\n", " ").split()) or "暂无可公开核验事项"
    lines: list[str] = []
    current = ""
    for char in value:
        proposal = current + char
        if current and text_width(draw, proposal, value_font) > width:
            lines.append(current)
            current = char
        else:
            current = proposal
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        suffix = "…"
        while lines[-1] and text_width(draw, lines[-1] + suffix, value_font) > width:
            lines[-1] = lines[-1][:-1]
        lines[-1] += suffix
    return lines


def draw_lines(draw: ImageDraw.ImageDraw, xy: tuple[int, int], lines: list[str], value_font: ImageFont.ImageFont, color: str, leading: int) -> int:
    x, y = xy
    for line in lines:
        draw.text((x, y), line, fill=color, font=value_font)
        y += leading
    return y


def listed_items(data: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
    daily = data["listed"]["daily"]
    rows: list[tuple[str, str]] = []
    for row in daily.get("opportunities", []) + daily.get("capital_rows", []) + daily.get("risk_rows", []):
        title = str(row.get("title") or row.get("company") or "上市公司事项")
        body = str(row.get("body") or row.get("attention") or row.get("event") or "")
        rows.append((title, body))
    for group in daily.get("fixed_columns", []):
        for row in group.get("items", []):
            rows.append((str(row.get("title") or group.get("title") or "固定披露"), str(row.get("body") or "")))
    summary = f"{daily.get('subtitle') or '当日正式公告与重点事项'}｜{data['listed'].get('sourceCoverage', {}).get('total', 0)}项已关联原始来源"
    return summary, rows[:6]


def listed_image_html(data: dict[str, Any]) -> str:
    """Render the V1 six-section information architecture from V2 data."""
    daily = data["listed"]["daily"]

    def esc(value: Any) -> str:
        return html.escape(str(value or ""))

    def numeric(value: Any) -> str:
        text = re.sub(r"<[^>]+>", "", str(value or ""))
        escaped = esc(text)
        return re.sub(
            r"(\d+(?:[,.]\d+)?(?:亿元|万元|%|股|张|元|个月|日)?)",
            r"<b>\1</b>",
            escaped,
        )

    kpis = "".join(
        f'<div class="kpi"><strong>{esc(row.get("num"))}</strong><span>{esc(row.get("label"))}</span></div>'
        for row in daily.get("kpis", [])
    )
    opportunities = "".join(
        f'<article class="chip"><h3>{esc(row.get("title"))}</h3><p>{esc(row.get("body"))}</p></article>'
        for row in daily.get("opportunities", [])[:4]
    )
    risks = "".join(
        f'<tr><td>{esc(row.get("company"))}</td><td>{esc(row.get("event"))}</td>'
        f'<td><span class="risk-tag">{esc(row.get("tag"))}</span></td></tr>'
        for row in daily.get("risk_rows", [])[:4]
    )
    tiles = "".join(
        f'<article class="tile"><h3>{esc(row.get("title"))}</h3><p>{esc(row.get("body"))}</p></article>'
        for row in daily.get("tiles", [])[:4]
    )
    capital = "".join(
        f'<tr><td>{esc(row.get("company"))}</td><td>{numeric(row.get("numbersHtml"))}</td>'
        f'<td>{esc(row.get("attention"))}</td></tr>'
        for row in daily.get("capital_rows", [])[:5]
    )
    fixed = "".join(
        '<div><h3>' + esc(group.get("title")) + "</h3>"
        + "".join(
            f'<article class="fixed"><b>{esc(row.get("title"))}</b><span>{esc(row.get("body"))}</span></article>'
            for row in group.get("items", [])[:4]
        )
        + "</div>"
        for group in daily.get("fixed_columns", [])[:2]
    )
    follow = "".join(
        f'<article class="follow"><b>{esc(row.get("title"))}</b><span>{esc(row.get("body") or row.get("whyImportant"))}</span></article>'
        for row in daily.get("follow_items", [])[:6]
    )
    counts = data["listed"]["counts"]
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>
    :root{{--navy:#0f243f;--ink:#1d2733;--muted:#667085;--line:#d8dee8;--soft:#f4f7fb;--red:#b83235;--redbg:#fff0ec}}
    *{{box-sizing:border-box}}body{{margin:0;background:#fff;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;color:var(--ink)}}
    .page{{width:1242px;min-height:2060px;background:#fff}}header{{display:grid;grid-template-columns:1.35fr 1fr;gap:28px;align-items:end;padding:38px 54px 28px;background:var(--navy);color:#fff}}
    h1{{margin:0;font:800 54px/1.05 Georgia,"Songti SC",serif}}.subtitle{{margin-top:14px;color:#d8e3f3;font-size:20px;line-height:1.45}}.source{{text-align:right;color:#c8d5e6;font-size:18px;line-height:1.5}}.source b{{display:block;color:#fff;font-size:27px}}
    main{{padding:18px 42px 14px}}.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:12px}}.kpi{{min-height:82px;padding:11px 15px;border:1px solid var(--line);border-radius:8px;background:var(--soft)}}.kpi strong,.kpi span{{display:block}}.kpi strong{{color:var(--navy);font-size:29px}}.kpi span{{margin-top:5px;color:var(--muted);font-size:14px;line-height:1.35}}
    .grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}.section{{border:1px solid var(--line);border-radius:8px;overflow:hidden}}.wide{{grid-column:1/-1}}.section-title{{display:flex;align-items:center;gap:10px;padding:8px 15px;background:#f7f9fc;border-bottom:1px solid var(--line);color:var(--navy);font-size:20px;font-weight:800}}.no{{display:grid;place-items:center;width:43px;height:28px;border-radius:5px;background:var(--navy);color:#fff;font-size:17px}}.body{{padding:9px 14px 10px}}
    .chips{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}.chip{{min-height:105px;padding:9px 10px;border:1px solid var(--line);border-radius:7px}}.chip h3,.chip p,.tile h3,.tile p{{margin:0}}.chip h3{{color:var(--red);font-size:17px}}.chip p{{margin-top:4px;font-size:15px;line-height:1.38}}
    table{{width:100%;border-collapse:collapse;table-layout:fixed;font-size:15px;line-height:1.35}}th,td{{padding:6px 8px;border-bottom:1px solid #edf1f6;text-align:left;vertical-align:top}}th{{color:var(--muted);background:#fbfcfe}}tr:last-child td{{border:0}}.risk-tag{{display:inline-block;padding:2px 6px;border-radius:4px;background:var(--redbg);color:var(--red);font-weight:800}}
    .tiles{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}}.tile{{min-height:95px;padding:8px 9px;border:1px solid var(--line);border-radius:7px}}.tile h3{{color:var(--navy);font-size:17px}}.tile p{{margin-top:4px;color:#344054;font-size:14px;line-height:1.35}}td b{{color:var(--red)}}
    .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}.two-col h3{{margin:0 0 6px;color:var(--navy);font-size:16px}}.fixed{{display:block;margin-top:5px;padding:6px 8px;border:1px solid #e5ebf3;border-radius:6px;font-size:14px;line-height:1.32}}.fixed b{{margin-right:5px;color:var(--navy)}}.fixed span{{color:#344054}}
    .follows{{display:grid;grid-template-columns:repeat(6,1fr);gap:7px}}.follow{{min-height:84px;padding:7px 8px;border:1px solid var(--line);border-radius:7px;background:#fcfdff;font-size:13px;line-height:1.32}}.follow b,.follow span{{display:block}}.follow b{{margin-bottom:4px;color:var(--navy);font-size:15px}}
    footer{{margin:10px 42px 22px;padding-top:9px;border-top:1px solid var(--line);display:flex;justify-content:space-between;gap:18px;color:var(--muted);font-size:14px;line-height:1.4}}
    </style></head><body><div class="page"><header><div><h1>陕西上市公司公告早报</h1><div class="subtitle">{esc(daily.get("subtitle"))}</div></div><div class="source"><b>重要观察主体 {counts["total"]} 家</b>辖区A股{counts["L1"]}家｜陕西港股{counts["L2"]}家｜陕西关联{counts["L3"]}家<br>公告源：CNINFO（港股回源HKEX）</div></header>
    <main><div class="kpis">{kpis}</div><div class="grid">
    <section class="section"><div class="section-title"><span class="no">01</span>今日业务机会</div><div class="body chips">{opportunities}</div></section>
    <section class="section"><div class="section-title"><span class="no">02</span>重大事项与风险公告</div><div class="body"><table><colgroup><col style="width:18%"><col style="width:60%"><col style="width:22%"></colgroup><thead><tr><th>公司</th><th>事项</th><th>业务判断</th></tr></thead><tbody>{risks}</tbody></table></div></section>
    <section class="section wide"><div class="section-title"><span class="no">03</span>上市公司动态</div><div class="body tiles">{tiles}</div></section>
    <section class="section wide"><div class="section-title"><span class="no">04</span>股东变动与资本运作</div><div class="body"><table><colgroup><col style="width:16%"><col style="width:48%"><col style="width:36%"></colgroup><thead><tr><th>公司</th><th>关键事实</th><th>业务关注</th></tr></thead><tbody>{capital}</tbody></table></div></section>
    <section class="section wide"><div class="section-title"><span class="no">05</span>股东会、治理与固定披露清单</div><div class="body two-col">{fixed}</div></section>
    <section class="section wide"><div class="section-title"><span class="no">06</span>今日重点跟踪公司</div><div class="body follows">{follow}</div></section>
    </div></main><footer><span>资料来源：V2正式观察池、巨潮资讯公告原文及港交所官方复核。仅作公告信息整理，不构成投资建议。</span><span>华泰证券西安锦业路证券营业部（西北分公司机构业务中心）｜{LIVE_ROOT}/v2/</span></footer></div></body></html>"""


def render_listed_image(data: dict[str, Any], target: Path) -> None:
    chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not chrome.is_file():
        raise FileNotFoundError(f"Chrome not found: {chrome}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="v2-listed-image-") as directory:
        html_path = Path(directory) / "listed.html"
        html_path.write_text(listed_image_html(data), encoding="utf-8")
        subprocess.run(
            [
                str(chrome),
                "--headless",
                "--disable-gpu",
                "--hide-scrollbars",
                "--force-device-scale-factor=1",
                "--window-size=1242,3600",
                f"--screenshot={target}",
                html_path.as_uri(),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    with Image.open(target) as source:
        image = source.convert("RGB")
    background = Image.new("RGB", image.size, image.getpixel((0, image.height - 1)))
    content_box = ImageChops.difference(image, background).getbbox()
    if content_box and content_box[3] + 28 < image.height:
        image.crop((0, 0, image.width, content_box[3] + 28)).save(target, format="PNG", optimize=True)


def private_items(data: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
    channel = data["private"]
    products = sorted(channel.get("products", []), key=lambda row: str(row.get("filingDate") or ""), reverse=True)
    rows = [
        (
            str(row.get("fundName") or "证券私募基金"),
            f"{row.get('managerName') or '管理人未披露'}｜托管：{row.get('custodianLabel') or row.get('custodian') or '未披露'}｜备案：{row.get('filingDate') or '—'}",
        )
        for row in products[:6]
    ]
    summary = f"年内备案 {len(products)} 只｜观察池 {channel.get('managerCounts', {}).get('total', 0)} 家｜最近备案 {channel.get('latestEventDate') or '—'}"
    return summary, rows


def ma_items(data: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
    channel = data["ma"]
    projects = sorted(channel.get("verifiedProjects", []), key=lambda row: str(row.get("eventDate") or row.get("reportedDate") or ""), reverse=True)
    rows = [
        (
            str(row.get("title") or "收并购项目"),
            f"{row.get('stageText') or row.get('stage') or '进展待核验'}｜{row.get('fact') or row.get('progress') or row.get('amount') or ''}",
        )
        for row in projects[:6]
    ]
    summary = f"年度项目 {len(channel.get('projects', []))} 个｜已核验原始来源 {len(channel.get('verifiedProjects', []))} 个｜最近事件 {channel.get('sourceAsOf') or '—'}"
    return summary, rows


def tender_items(data: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
    channel = data["tender"]
    projects = sorted(channel.get("projects", []), key=lambda row: str(row.get("latestProgressDate") or ""), reverse=True)
    rows = [
        (
            str(row.get("title") or "金融招投标项目"),
            f"{row.get('statusGroup') or row.get('stage') or '进展待核验'}｜{row.get('purchaser') or '采购主体未披露'}｜{row.get('projectScale') or '规模未披露'}",
        )
        for row in projects[:6]
    ]
    summary = f"正式项目 {len(projects)} 个｜待回源线索 {len(channel.get('pending', []))} 条｜最近事件 {channel.get('sourceAsOf') or '—'}"
    return summary, rows


ITEM_EXTRACTORS = {
    "listed": listed_items,
    "private": private_items,
    "ma": ma_items,
    "tender": tender_items,
}


def render_image(data: dict[str, Any], channel: str, target: Path) -> None:
    if channel == "listed":
        render_listed_image(data, target)
        return
    spec = CHANNELS[channel]
    day = str(data["asOf"])
    summary, rows = ITEM_EXTRACTORS[channel](data)
    width, height = 1600, 2200
    canvas = Image.new("RGB", (width, height), "#F6F2EA")
    draw = ImageDraw.Draw(canvas)
    navy, muted, line = "#152B44", "#68788A", "#D9D0C1"
    title_font, body_font, small_font = font(64), font(35), font(25)
    draw.rectangle((0, 0, width, 230), fill=navy)
    draw.text((100, 55), "陕西资本市场日报", fill="#FFFFFF", font=font(38))
    draw.rounded_rectangle((1320, 53, 1470, 118), radius=13, fill=spec["accent"])
    draw.text((1346, 66), "日图", fill="#FFFFFF", font=font(30))
    draw.text((100, 316), spec["title"], fill=navy, font=title_font)
    draw.text((100, 404), zh_date(day), fill=muted, font=font(32))
    draw.line((100, 465, 1500, 465), fill=spec["accent"], width=7)
    y = 520
    draw.rounded_rectangle((100, y, 1500, y + 190), radius=20, fill="#FFFFFF", outline=line, width=2)
    draw.text((135, y + 34), "本期概览", fill=spec["accent"], font=font(30))
    draw_lines(draw, (135, y + 83), wrap(draw, summary, body_font, 1310, 2), body_font, navy, 50)
    y += 245
    for index, (headline, body) in enumerate(rows or [("暂无新增有效事项", "已完成当日扫描，未识别可公开核验的新事项。")] , start=1):
        item_height = 230
        draw.rounded_rectangle((100, y, 1500, y + item_height), radius=20, fill="#FFFFFF", outline=line, width=2)
        draw.rounded_rectangle((132, y + 30, 205, y + 103), radius=36, fill=spec["accent"])
        draw.text((153, y + 45), f"{index:02d}", fill="#FFFFFF", font=font(25))
        title_lines = wrap(draw, headline, font(37), 1200, 2)
        title_end = draw_lines(draw, (235, y + 29), title_lines, font(37), navy, 48)
        draw_lines(draw, (235, title_end + 8), wrap(draw, body, body_font, 1200, 2), body_font, "#3E5063", 46)
        y += item_height + 28
        if y + item_height > height - 160:
            break
    draw.line((100, height - 115, 1500, height - 115), fill=line, width=2)
    draw.text((100, height - 82), "数据与来源以 V2 当日已核验快照为准", fill=muted, font=small_font)
    draw.text((1010, height - 82), f"构建版本 {data['build']['version']}", fill=muted, font=small_font)
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, format="PNG", optimize=True)


def empty_index() -> dict[str, Any]:
    return {"schemaVersion": "1.0", "updatedAt": "", "channels": {channel: [] for channel in CHANNELS}}


def load_index() -> dict[str, Any]:
    if not INDEX_PATH.is_file():
        return empty_index()
    value = load(INDEX_PATH)
    value.setdefault("channels", {})
    for channel in CHANNELS:
        value["channels"].setdefault(channel, [])
    return value


def release_paths(day: str) -> tuple[Path, Path, Path, Path]:
    directory = RELEASES / day
    return (
        directory / "morning-production-data.json",
        directory / "morning-production-data.json.gz",
        directory / "morning-release.json",
        STAGING / day,
    )


def snapshot_exists(snapshot_json: Path, snapshot_gzip: Path) -> bool:
    return snapshot_gzip.is_file() or snapshot_json.is_file()


def read_snapshot(snapshot_json: Path, snapshot_gzip: Path) -> dict[str, Any]:
    if snapshot_gzip.is_file():
        with gzip.open(snapshot_gzip, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    if snapshot_json.is_file():
        return load(snapshot_json)
    raise FileNotFoundError("不存在冻结日图快照")


def write_snapshot(snapshot_gzip: Path, value: dict[str, Any]) -> None:
    """Write a deterministic compressed snapshot without retaining a JSON twin."""
    snapshot_gzip.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    temporary = snapshot_gzip.with_suffix(snapshot_gzip.suffix + ".tmp")
    with temporary.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as handle:
            handle.write(payload)
    temporary.replace(snapshot_gzip)


def snapshot_reference(snapshot_json: Path, snapshot_gzip: Path) -> Path:
    return snapshot_gzip if snapshot_gzip.is_file() else snapshot_json


def image_name(day: str, channel: str) -> str:
    return f"{zh_date(day)}{CHANNELS[channel]['file']}.png"


def public_path(day: str, channel: str) -> str:
    return f"{PUBLIC_PREFIX}/{channel}/{day[:4]}/{image_name(day, channel)}"


def find_entry(index: dict[str, Any], channel: str, day: str) -> dict[str, Any] | None:
    return next((row for row in index["channels"][channel] if row.get("date") == day), None)


def prepare_v2_legacy(day: str, slot: str, *, create_if_missing: bool = False) -> dict[str, Any]:
    snapshot_json, snapshot_gzip, release_path, staging = release_paths(day)
    if slot != "morning" and not (create_if_missing and not release_path.is_file()):
        return {"created": False, "reason": "daily_images_morning_only", "snapshot": snapshot_exists(snapshot_json, snapshot_gzip), "manifest": release_path.is_file()}
    production = load(V2 / "data" / "production-data.json")
    if production.get("asOf") != day:
        raise ValueError(f"production-data 日期不是 {day}")
    version = str(production.get("build", {}).get("version") or "")
    if not version:
        raise ValueError("production-data 缺少构建版本")
    if snapshot_exists(snapshot_json, snapshot_gzip):
        existing = read_snapshot(snapshot_json, snapshot_gzip)
        if existing.get("build", {}).get("version") != version:
            raise ValueError("同日早报快照已经存在且构建版本不同；拒绝重写唯一日图")
    else:
        write_snapshot(snapshot_gzip, production)
    if snapshot_json.is_file() and not snapshot_gzip.is_file():
        write_snapshot(snapshot_gzip, existing)
    if snapshot_json.is_file():
        snapshot_json.unlink()
    snapshot_path = snapshot_reference(snapshot_json, snapshot_gzip)
    index = load_index()
    files: list[dict[str, Any]] = []
    for channel in CHANNELS:
        target = staging / channel / day[:4] / image_name(day, channel)
        entry = find_entry(index, channel, day)
        if entry and entry.get("sourceBuildVersion") not in {None, version}:
            raise ValueError(f"{channel} 同日归档版本冲突")
        if not target.is_file():
            render_image(production, channel, target)
        digest = sha256(target)
        payload = {
            "date": day,
            "channel": channel,
            "label": CHANNELS[channel]["label"],
            "fileName": target.name,
            "publicPath": public_path(day, channel),
            "sourceBuildVersion": version,
            "snapshotPath": snapshot_path.relative_to(ROOT).as_posix(),
            "snapshotSha256": sha256(snapshot_path),
            "sha256": digest,
            "origin": "v2",
            "webStatus": "staged",
            "ima": (entry or {}).get("ima", {"status": "pending"}),
            "updatedAt": now(),
        }
        if entry:
            index["channels"][channel].remove(entry)
        index["channels"][channel].append(payload)
        index["channels"][channel].sort(key=lambda row: str(row.get("date") or ""), reverse=True)
        files.append({"channel": channel, "stagedPath": target.relative_to(ROOT).as_posix(), **payload})
    index["updatedAt"] = now()
    write(INDEX_PATH, index)
    release = {
        "schemaVersion": "1.0",
        "date": day,
        "slot": slot,
        "sourceBuildVersion": version,
        "snapshotPath": snapshot_path.relative_to(ROOT).as_posix(),
        "snapshotSha256": sha256(snapshot_path),
        "imageFiles": files,
        "webStatus": "staged",
        "imaStatus": "pending",
        "preparedAt": now(),
    }
    write(release_path, release)
    return {"created": True, "release": release_path.relative_to(ROOT).as_posix(), "stage": staging.relative_to(ROOT).as_posix(), "files": files}


def prepare(day: str, slot: str, *, create_if_missing: bool = False, replace_v2_edition: bool = False) -> dict[str, Any]:
    """Prepare V2's unique daily image edition from the frozen V2 snapshot."""
    if replace_v2_edition:
        raise ValueError("V2日图由同日冻结快照唯一生成，不支持替换版式")
    return prepare_v2_legacy(
        day,
        slot,
        create_if_missing=create_if_missing,
    )


def mark_web_published(day: str) -> dict[str, Any]:
    index = load_index()
    snapshot_json, snapshot_gzip, release_path, _ = release_paths(day)
    if not release_path.is_file():
        return {"updated": False, "reason": "no_daily_image_release"}
    release = load(release_path)
    if not snapshot_exists(snapshot_json, snapshot_gzip):
        return {"updated": False, "reason": "no_daily_image_snapshot"}
    for channel in CHANNELS:
        entry = find_entry(index, channel, day)
        if entry:
            entry["webStatus"] = "published"
            entry["updatedAt"] = now()
            for image in release.get("imageFiles", []):
                if image.get("channel") == channel:
                    image["webStatus"] = "published"
                    image["updatedAt"] = entry["updatedAt"]
    index["updatedAt"] = now()
    release["webStatus"] = "published"
    release["webPublishedAt"] = now()
    write(INDEX_PATH, index)
    write(release_path, release)
    return {"updated": True, "release": release_path.relative_to(ROOT).as_posix()}


def restore(day: str) -> dict[str, Any]:
    """Recreate a missing temporary PNG from the immutable daily snapshot.

    This is intentionally independent from ``production-data.json``.  It is
    used only by the IMA retry path after a temporary local file has gone
    missing, so a later intra-day web update can never alter an old morning
    image.
    """
    snapshot_json, snapshot_gzip, release_path, staging = release_paths(day)
    if not release_path.is_file():
        raise FileNotFoundError(f"不存在 {day} 的日图发布清单")
    release = load(release_path)
    index = load_index()
    if not snapshot_exists(snapshot_json, snapshot_gzip):
        raise FileNotFoundError(f"不存在 {day} 的冻结日图快照")
    snapshot_path = snapshot_reference(snapshot_json, snapshot_gzip)
    production = read_snapshot(snapshot_json, snapshot_gzip)
    version = str(production.get("build", {}).get("version") or "")
    if not version or version != release.get("sourceBuildVersion"):
        raise ValueError("冻结快照与日图发布清单的构建版本不一致")
    restored: list[str] = []
    for channel in CHANNELS:
        entry = find_entry(index, channel, day)
        if (
            not entry
            or entry.get("origin") != "v2"
            or entry.get("sourceBuildVersion") != version
        ):
            continue
        target = staging / channel / day[:4] / str(entry["fileName"])
        if not target.is_file():
            render_image(production, channel, target)
            restored.append(target.relative_to(ROOT).as_posix())
        actual = sha256(target)
        expected = str(entry.get("sha256") or "")
        if expected and actual != expected:
            raise ValueError(f"{channel} 由冻结快照复原后的图片哈希不一致")
    return {"restored": restored, "snapshot": snapshot_path.relative_to(ROOT).as_posix()}


def compact_snapshots() -> dict[str, Any]:
    """Convert legacy release JSON files to compressed immutable snapshots.

    The public image archive remains untouched; the index and release
    manifests are rewritten atomically to point at the compressed record.
    """
    index = load_index()
    converted: list[str] = []
    for directory in sorted(path for path in RELEASES.iterdir() if path.is_dir()):
        snapshot_json, snapshot_gzip, release_path, _ = release_paths(directory.name)
        if not snapshot_json.is_file() and not snapshot_gzip.is_file():
            continue
        if snapshot_json.is_file():
            production = load(snapshot_json)
            if snapshot_gzip.is_file() and read_snapshot(snapshot_json, snapshot_gzip) != production:
                raise ValueError(f"{directory.name} 的压缩快照与原始快照不一致")
            if not snapshot_gzip.is_file():
                write_snapshot(snapshot_gzip, production)
            snapshot_json.unlink()
            converted.append(directory.name)
        snapshot_ref = snapshot_reference(snapshot_json, snapshot_gzip)
        snapshot_value = snapshot_ref.relative_to(ROOT).as_posix()
        snapshot_digest = sha256(snapshot_ref)
        for rows in index["channels"].values():
            for entry in rows:
                if entry.get("origin") == "v2" and entry.get("date") == directory.name:
                    entry["snapshotPath"] = snapshot_value
                    entry["snapshotSha256"] = snapshot_digest
        if release_path.is_file():
            release = load(release_path)
            release["snapshotPath"] = snapshot_value
            release["snapshotSha256"] = snapshot_digest
            for image in release.get("imageFiles", []):
                image["snapshotPath"] = snapshot_value
                image["snapshotSha256"] = snapshot_digest
            write(release_path, release)
    if converted:
        index["updatedAt"] = now()
        write(INDEX_PATH, index)
    return {"converted": converted, "count": len(converted)}


def cleanup_staging(day: str) -> dict[str, Any]:
    """Remove only the exact V2 PNG staging directory for a validated day."""
    try:
        if datetime.strptime(day, "%Y-%m-%d").strftime("%Y-%m-%d") != day:
            raise ValueError
    except ValueError as error:
        raise ValueError(f"非法日图暂存日期：{day}") from error
    target = STAGING / day
    if target.exists():
        shutil.rmtree(target)
    return {"cleaned": True, "stage": target.relative_to(ROOT).as_posix()}


def main() -> int:
    parser = argparse.ArgumentParser(description="V2日图快照、临时渲染和网页归档管理")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "mark-web-published", "restore", "compact-snapshots", "cleanup-staging"):
        item = sub.add_parser(name)
        if name != "compact-snapshots":
            item.add_argument("--date", required=True)
            item.add_argument("--slot", choices=("morning", "midday", "closing"), default="morning")
        if name == "prepare":
            item.add_argument("--create-if-missing", action="store_true")
            item.add_argument("--replace-v2-edition", action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(
            args.date,
            args.slot,
            create_if_missing=args.create_if_missing,
            replace_v2_edition=args.replace_v2_edition,
        )
    elif args.command == "mark-web-published":
        result = mark_web_published(args.date)
    elif args.command == "restore":
        result = restore(args.date)
    elif args.command == "compact-snapshots":
        result = compact_snapshots()
    elif args.command == "cleanup-staging":
        result = cleanup_staging(args.date)
    else:
        result = cleanup_staging(args.date)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
