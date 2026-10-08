"""Capture the hotspot map of each park as a figure for the paper.

    python scripts/make_figures.py --base http://localhost:4173 --out docs/figures

Needs Playwright (`pip install playwright && playwright install chromium`) and a running copy of
the dashboard (`cd web && npm run build && npm run preview`). Each figure is the map element only,
so it includes the map's own attribution to OpenStreetMap contributors.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

PARKS = ["bandipur", "nagarahole", "mudumalai", "serengeti", "everglades", "smokies"]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--base", default="http://localhost:4173")
    p.add_argument("--out", default="docs/figures")
    p.add_argument("--width", type=int, default=1500)
    args = p.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_context(
            viewport={"width": args.width, "height": 1000}, color_scheme="light"
        ).new_page()
        for slug in PARKS:
            page.goto(f"{args.base}/#/hotspots/{slug}")
            page.wait_for_selector(".map", timeout=60000)
            try:
                page.wait_for_selector("text=Busiest squares", timeout=30000)
            except Exception:
                print(f"{slug}: no hotspots to draw")
                continue
            page.wait_for_timeout(3500)  # let the map tiles load
            page.locator(".map").screenshot(path=str(out / f"hotspots-{slug}.png"))
            print(f"wrote {out / f'hotspots-{slug}.png'}")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
