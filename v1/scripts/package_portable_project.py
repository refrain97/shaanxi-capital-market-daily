#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import posixpath
import shutil
import sys
import zipfile
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT_NAME = "shaanxi-capital-market-daily"
DEFAULT_BUILD_DIR = ROOT / "dist" / PACKAGE_ROOT_NAME
DEFAULT_PACKAGE_DIR = ROOT / "packages"

EXCLUDED_NAMES = {
    ".DS_Store",
    ".git",
    ".npm-cache",
    ".pytest_cache",
    ".vercel",
    "__pycache__",
    "dist",
    "node_modules",
    "output",
    "packages",
}

EXCLUDED_PATTERNS = (
    ".env",
    ".env.*",
    "*.pyc",
)

HTML_ATTRS = {
    "a": ("href",),
    "area": ("href",),
    "audio": ("src",),
    "embed": ("src",),
    "iframe": ("src",),
    "img": ("src", "srcset"),
    "link": ("href",),
    "script": ("src",),
    "source": ("src", "srcset"),
    "track": ("src",),
    "video": ("poster", "src"),
}


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        wanted = HTML_ATTRS.get(tag)
        if not wanted:
            return
        attr_map = dict(attrs)
        for attr in wanted:
            value = attr_map.get(attr)
            if not value:
                continue
            if attr == "srcset":
                self.links.extend(parse_srcset(value))
            else:
                self.links.append(value.strip())


def parse_srcset(value: str) -> list[str]:
    links: list[str] = []
    for candidate in value.split(","):
        url = candidate.strip().split(" ", 1)[0]
        if url:
            links.append(url)
    return links


def should_exclude(path: Path) -> bool:
    rel_parts = path.relative_to(ROOT).parts
    if any(part in EXCLUDED_NAMES for part in rel_parts):
        return True
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in EXCLUDED_PATTERNS)


def copy_project(build_dir: Path) -> None:
    if build_dir == ROOT or ROOT not in build_dir.parents:
        raise SystemExit(f"Refusing to write outside repo: {build_dir}")
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)

    for source in sorted(ROOT.rglob("*")):
        if should_exclude(source):
            continue
        target = build_dir / source.relative_to(ROOT)
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def is_external(value: str) -> bool:
    lower = value.lower()
    return (
        not value
        or lower.startswith("#")
        or lower.startswith("data:")
        or lower.startswith("mailto:")
        or lower.startswith("tel:")
        or lower.startswith("javascript:")
        or lower.startswith("//")
        or urlsplit(value).scheme in {"http", "https"}
    )


def resolve_link(html_path: Path, site_root: Path, value: str) -> Path | None:
    if is_external(value):
        return None
    parsed = urlsplit(value)
    link_path = unquote(parsed.path)
    if not link_path:
        return None
    if link_path.startswith("/"):
        normalized = posixpath.normpath(link_path.lstrip("/"))
        target = site_root / normalized
    else:
        normalized = posixpath.normpath(posixpath.join(html_path.parent.as_posix(), link_path))
        target = Path(normalized)
    if parsed.path.endswith("/"):
        return target / "index.html"
    return target


def validate_html_links(site_root: Path) -> list[str]:
    missing: list[str] = []
    for html_path in sorted(site_root.rglob("*.html")):
        parser = LinkParser()
        parser.feed(html_path.read_text(encoding="utf-8", errors="ignore"))
        for raw_link in parser.links:
            target = resolve_link(html_path, site_root, raw_link)
            if target is None:
                continue
            if not target.exists():
                rel_html = html_path.relative_to(site_root).as_posix()
                missing.append(f"{rel_html} -> {raw_link}")
    return missing


def write_zip(build_dir: Path, package_dir: Path, stamp: str) -> Path:
    package_dir.mkdir(parents=True, exist_ok=True)
    zip_path = package_dir / f"{PACKAGE_ROOT_NAME}-{stamp}.zip"
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(build_dir.rglob("*")):
            if not path.is_file():
                continue
            archive_name = Path(PACKAGE_ROOT_NAME) / path.relative_to(build_dir)
            archive.write(path, archive_name.as_posix())
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a portable zip for the Shaanxi Capital Market Daily project."
    )
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD_DIR)
    parser.add_argument("--package-dir", type=Path, default=DEFAULT_PACKAGE_DIR)
    parser.add_argument("--stamp", default=datetime.now().strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args()

    build_dir = args.build_dir.resolve()
    package_dir = args.package_dir.resolve()

    copy_project(build_dir)
    missing = validate_html_links(build_dir)
    if missing:
        print("Missing local links found in packaged HTML:", file=sys.stderr)
        for item in missing[:80]:
            print(f"  {item}", file=sys.stderr)
        if len(missing) > 80:
            print(f"  ... {len(missing) - 80} more", file=sys.stderr)
        return 1

    zip_path = write_zip(build_dir, package_dir, args.stamp)
    file_count = sum(1 for path in build_dir.rglob("*") if path.is_file())
    print(f"Packaged {file_count} files")
    print(f"Build folder: {build_dir.relative_to(ROOT)}")
    print(f"Zip package: {zip_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
