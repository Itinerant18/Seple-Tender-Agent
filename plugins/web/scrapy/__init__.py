"""Scrapy web extract plugin — bundled, auto-loaded.

Provides a fallback extraction backend using Scrapy for cases where
the primary provider returns empty/falsy content.
"""

from __future__ import annotations

from plugins.web.scrapy.provider import ScrapyWebSearchProvider


def register(ctx) -> None:
    """Register the Scrapy provider with the plugin context."""
    ctx.register_web_search_provider(ScrapyWebSearchProvider())