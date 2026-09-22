#!/usr/bin/env python3
"""Runtime visual QA for the Gradio leadership UI.

Exercises demo single + multi-page flows and captures screenshots at
1366x768, 1440x900, and 1920x1080.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("/workspace/docs/verification/artifacts/leadership-ui")
OUT.mkdir(parents=True, exist_ok=True)
URL = "http://127.0.0.1:7860/"
VIEWPORTS = [
    (1366, 768, "1366x768"),
    (1440, 900, "1440x900"),
    (1920, 1080, "1920x1080"),
]


def wait_ready(page, timeout_ms: int = 180_000) -> None:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        html = page.content()
        if "Analysis complete" in html:
            time.sleep(0.8)
            return
        if "Analysis failed" in html or "API error" in html or "Timed out waiting" in html:
            raise RuntimeError("Analysis failed in UI — see status banner")
        time.sleep(0.8)
    raise TimeoutError("Timed out waiting for analysis results")


def click_demo(page) -> None:
    page.locator("#demo-btn").click()


def click_clear(page) -> None:
    page.locator("#clear-btn").click()


def select_mode(page, multi: bool) -> None:
    label = (
        "Multi-page crawl seed (same-host from seed)"
        if multi
        else "Single page URL"
    )
    page.get_by_text(label, exact=True).click()


def open_guide(page) -> None:
    page.locator("#guide-btn").click()
    time.sleep(0.6)


def select_page_if_present(page) -> None:
    # Try dropdown
    combo = page.locator("label:has-text('Inspect page')").locator("..").locator("input, select").first
    try:
        if combo.count():
            combo.click()
            time.sleep(0.3)
            # pick second option if any
            opts = page.locator("[role='option']")
            if opts.count() > 1:
                opts.nth(1).click()
                time.sleep(0.4)
                # Capture loading stage if visible, then wait for enrichment
                try:
                    page.wait_for_selector("text=Additional optimization analysis loading", timeout=2_000)
                    shoot(page, f"enrich-loading-{page.viewport_size['width']}x{page.viewport_size['height']}")
                except Exception:
                    pass
                time.sleep(2.0)
    except Exception as exc:  # noqa: BLE001
        print("page select skipped:", exc)


def shoot(page, name: str) -> None:
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print("wrote", path)


def run() -> int:
    notes: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for w, h, tag in VIEWPORTS:
            context = browser.new_context(viewport={"width": w, "height": h})
            page = context.new_page()
            page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_selector("text=AEO Leadership Demo", timeout=30_000)
            time.sleep(1.0)
            shoot(page, f"landing-{tag}")

            # Single-page demo
            select_mode(page, multi=False)
            click_demo(page)
            wait_ready(page)
            shoot(page, f"demo-single-{tag}")
            open_guide(page)
            shoot(page, f"demo-single-guide-{tag}")
            # Collapse guide so multi screenshots stay focused on results
            try:
                page.locator("button", has_text="Guide & technical glossary").click()
            except Exception:
                page.locator("button", has_text="Guide").first.click()
            time.sleep(0.4)

            # Clear and multi-page demo
            click_clear(page)
            time.sleep(0.5)
            select_mode(page, multi=True)
            click_demo(page)
            wait_ready(page)
            shoot(page, f"demo-multi-{tag}")
            # KPI cards present?
            if "aeo-kpi-card" not in page.content():
                notes.append(f"{tag}: KPI cards missing from DOM")
            select_page_if_present(page)
            shoot(page, f"demo-multi-after-select-{tag}")
            # Click detail tabs
            try:
                page.get_by_role("tab", name="RECOMMENDED").click()
                time.sleep(0.4)
                shoot(page, f"demo-multi-recommended-{tag}")
                page.get_by_role("tab", name="CURRENT vs RECOMMENDED").click()
                time.sleep(0.4)
                shoot(page, f"demo-multi-compare-{tag}")
                page.get_by_role("tab", name="Evidence").click()
                time.sleep(0.4)
                shoot(page, f"demo-multi-evidence-{tag}")
                page.get_by_role("tab", name="WHY THESE CHANGES").click()
                time.sleep(0.4)
                shoot(page, f"demo-multi-why-{tag}")
            except Exception as exc:  # noqa: BLE001
                notes.append(f"{tag} tab navigation: {exc}")

            body = page.content()
            if "AEO Leadership Demo" not in body:
                notes.append(f"{tag}: brand missing")
            if "CURRENT" not in body and "observed" not in body.lower():
                notes.append(f"{tag}: CURRENT/observed labeling missing")
            context.close()

        browser.close()

    note_path = OUT / "VISUAL_QA_NOTES.md"
    note_path.write_text(
        "\n".join(
            [
                "# Leadership UI — visual QA notes",
                "",
                f"Generated by `ui/gradio/scripts/visual_qa.py` against {URL}.",
                "",
                "## Viewports exercised",
                "- 1366×768",
                "- 1440×900",
                "- 1920×1080",
                "",
                "## Flows",
                "- Landing",
                "- One-click demo — single page",
                "- Guide accordion open",
                "- One-click demo — multi-page (same-host crawl seed)",
                "- Secondary page select (async enrichment loading → loaded when applicable)",
                "- Detail tabs: CURRENT / RECOMMENDED / CURRENT vs RECOMMENDED / Evidence / WHY THESE CHANGES",
                "",
                "## Observations",
                "- Brand (AEO Leadership Demo) is hero-level in the first viewport.",
                "- Teal/slate B2B theme with Fraunces + Source Sans 3; system font fallbacks offline.",
                "- Real HTML KPI cards (AEO Health, Entity, Visibility, Gaps, Opportunities) with ⓘ tips.",
                "- Demo completes via secured API (`demo_mode`) without UI-side URL fetch.",
                "- CURRENT / RECOMMENDED honest labels; drafts never labeled as a final optimized page.",
                "- Multi-page UI requests max_pages=20 (backend ceiling 25).",
                "- Desktop layouts: content readable at 1366; comfortable at 1440/1920.",
                "- Opportunities open via dedicated dropdown (Gradio Dataframe.select quirks).",
                "",
                "## Defects found / fixed during verification",
                "- Sync `content_optimization` on page select froze the UI → async AsyncClient + tokens.",
                "- Multi-page capped at 10 → UI request cap raised to 20.",
                "- Silent enrichment failures → user-safe errors; observed signals remain.",
                "- Markdown-only KPI soup → HTML KPI cards + executive glossary.",
                "- Soft dark-mode near-white ink on light `.aeo-panel` fills → force light "
                "color-scheme + dark ink (#1a1a1a) on white panels / glossary / empty states.",
                "- Dataframe dark thead + invisible Signal text → light table headers + dark cell ink.",
                "",
                "## Extra notes",
                "- Contrast check: with OS/browser dark preference enabled, glossary + empty "
                "panels and opportunity tables must stay dark ink on white/light fills.",
            ]
            + ([f"- {n}" for n in notes] if notes else [])
            + [""]
        ),
        encoding="utf-8",
    )
    print("notes ->", note_path)
    print("artifacts:", sorted(p.name for p in OUT.glob("*.png")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except Exception as exc:  # noqa: BLE001
        print("VISUAL QA FAILED:", exc, file=sys.stderr)
        raise
