#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image


OUT = Path(__file__).resolve().parents[1]
ROOT = OUT.parents[1]


def main() -> int:
    pages = [OUT / name for name in ("index.html", "listed.html", "private.html", "ma.html", "tender.html")]
    forbidden = ("227份", "3种形态", "1入口", "抓取上限", "本地数据路径", "原始 JSON")
    for path in pages:
        text = path.read_text(encoding="utf-8")
        assert "PREVIEW" in text and "客户联系" in text and "免责声明" in text
        assert not any(word in text for word in forbidden), (path, forbidden)
        for href in re.findall(r"href=['\"]([^'\"]+)", text):
            parsed = urlparse(href)
            if parsed.scheme or href.startswith(("#", "mailto:")):
                continue
            target = (path.parent / parsed.path).resolve()
            assert target.exists(), f"broken link {path.name}: {href}"

    contract = json.loads((ROOT / "v1" / "config" / "v1-source-contract.json").read_text(encoding="utf-8"))
    assert contract["listedUniverse"]["path"] == "v3/data/listed/universe.json"
    assert contract["privateFundUniverse"]["path"] == "v3/config/private-fund-universe.json"
    assert (ROOT / contract["listedUniverse"]["path"]).is_file()
    assert (ROOT / contract["privateFundUniverse"]["path"]).is_file()

    universe = json.loads((ROOT / contract["listedUniverse"]["path"]).read_text(encoding="utf-8"))
    assert universe["counts"] == {"total": 110, "L1": 85, "L2": 14, "L3": 11}
    assert len(universe["entities"]) == 110
    private_pool = json.loads((ROOT / contract["privateFundUniverse"]["path"]).read_text(encoding="utf-8"))
    assert len(private_pool["relatedTargets"]) == 1
    target = private_pool["relatedTargets"][0]
    assert target["managerId"] == "101000026206" and target["universeTier"] == "PF2"
    assert target["currentRegisterProvince"] == "广东省" and "西安" in target["inclusionReason"]

    expected_images = {
        "private-cover.png": (1242, 1080),
        "private-detail-1.png": (1242, 1750),
        "private-detail-2.png": (1242, 1750),
        "private-detail-3.png": (1242, 1750),
        "ma-cover.png": (1242, 1080),
        "ma-detail-1.png": (1242, 1750),
        "ma-detail-2.png": (1242, 1750),
        "ma-detail-3.png": (1242, 1750),
        "ma-detail-4.png": (1242, 1750),
    }
    images = list((OUT / "images").glob("private-*.png")) + list((OUT / "images").glob("ma-*.png"))
    assert {path.name for path in images} == set(expected_images)
    assert all(Image.open(OUT / "images" / name).size == size for name, size in expected_images.items())
    for index in range(1, 5):
        detail = (OUT / "share" / f"ma-detail-{index}.html").read_text(encoding="utf-8")
        assert detail.count("<article>") == 6
        assert f"{index + 1} / 5" in detail
    shots = list((OUT / "output" / "playwright").glob("*-desktop-1440.png")) + list((OUT / "output" / "playwright").glob("*-mobile-390.png"))
    assert len(shots) == 10
    assert all(Image.open(path).width == (390 if "mobile" in path.name else 1440) for path in shots)
    print("candidate validation: PASS (pages=5, links=PASS, share_images=9, screenshots=10)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
