"""Crawl discovery, robots, fetch, and alternate content representations."""

from aeo_mvp.crawler.alternate import (
    AlternateRepresentation,
    get_supported_alternate_url,
)
from aeo_mvp.crawler.discover import crawl_site

__all__ = [
    "AlternateRepresentation",
    "crawl_site",
    "get_supported_alternate_url",
]
