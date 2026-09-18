"""Load demo fixtures without network I/O."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from urllib.parse import urljoin


def fixtures_dir() -> Path:
    """Return filesystem path to packaged fixtures."""
    try:
        root = resources.files("aeo_mvp.demo") / "fixtures"
        return Path(str(root))
    except Exception:
        return Path(__file__).resolve().parent / "fixtures"


@dataclass(frozen=True)
class DemoPageFixture:
    url: str
    path: str
    depth: int
    title: str
    html: str
    file: str


@lru_cache
def _site_map() -> dict:
    path = fixtures_dir() / "site_map.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_demo_robots() -> str:
    return (fixtures_dir() / "robots.txt").read_text(encoding="utf-8")


def load_demo_pages() -> list[DemoPageFixture]:
    site = _site_map()
    base = site["base_url"]
    pages: list[DemoPageFixture] = []
    for entry in site["pages"]:
        file_rel = entry["file"]
        html = (fixtures_dir() / file_rel).read_text(encoding="utf-8")
        url = urljoin(base, entry["path"].lstrip("/")) if entry["path"] != "/" else base
        if entry["path"] != "/" and not url.endswith("/") and "?" not in url:
            # keep path as /about style without trailing slash for uniqueness
            url = urljoin(base, entry["path"].lstrip("/"))
        pages.append(
            DemoPageFixture(
                url=url,
                path=entry["path"],
                depth=int(entry["depth"]),
                title=entry["title"],
                html=html,
                file=file_rel,
            )
        )
    return pages


def load_visibility_fixture() -> dict:
    path = fixtures_dir() / "visibility" / "observations.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_prompt_set_fixture() -> dict:
    path = fixtures_dir() / "visibility" / "prompt_set.json"
    return json.loads(path.read_text(encoding="utf-8"))
