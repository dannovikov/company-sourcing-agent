"""Async client for the HackerNews Firebase API.

Docs: https://github.com/HackerNews/API
Base URL: https://hacker-news.firebaseio.com/v0
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://hacker-news.firebaseio.com/v0"

# How many stories to fetch per category by default
DEFAULT_FETCH_LIMIT = 60


@dataclass
class HNItem:
    """A raw HackerNews item from the API."""

    id: int
    type: str = ""
    title: str = ""
    text: str = ""
    url: str = ""
    by: str = ""
    score: int = 0
    descendants: int = 0  # comment count
    time: int = 0


class HNClient:
    """Lightweight async wrapper around the HN Firebase API."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=30)
        self._owns_client = client is None

    async def _get_json(self, path: str) -> Any:
        url = f"{BASE_URL}{path}"
        resp = await self._client.get(url)
        resp.raise_for_status()
        return resp.json()

    async def get_top_story_ids(self, limit: int = DEFAULT_FETCH_LIMIT) -> list[int]:
        ids = await self._get_json("/topstories.json")
        return ids[:limit]

    async def get_new_story_ids(self, limit: int = DEFAULT_FETCH_LIMIT) -> list[int]:
        ids = await self._get_json("/newstories.json")
        return ids[:limit]

    async def get_best_story_ids(self, limit: int = DEFAULT_FETCH_LIMIT) -> list[int]:
        ids = await self._get_json("/beststories.json")
        return ids[:limit]

    async def get_show_hn_ids(self, limit: int = DEFAULT_FETCH_LIMIT) -> list[int]:
        ids = await self._get_json("/showstories.json")
        return ids[:limit]

    async def get_item(self, item_id: int) -> HNItem | None:
        """Fetch a single HN item by ID."""
        resp = await self._client.get(f"{BASE_URL}/item/{item_id}.json")
        resp.raise_for_status()
        # The HN API returns literal "null" for deleted/missing items
        if resp.text.strip() in ("", "null"):
            return None
        data = resp.json()
        if data is None:
            return None
        return HNItem(
            id=data.get("id", 0),
            type=data.get("type", ""),
            title=data.get("title", ""),
            text=data.get("text", ""),
            url=data.get("url", ""),
            by=data.get("by", ""),
            score=data.get("score", 0),
            descendants=data.get("descendants", 0),
            time=data.get("time", 0),
        )

    async def get_items(self, item_ids: list[int]) -> list[HNItem]:
        """Fetch multiple items concurrently in batches."""
        items: list[HNItem] = []
        batch_size = 20
        for i in range(0, len(item_ids), batch_size):
            batch = item_ids[i : i + batch_size]
            results = await asyncio.gather(
                *(self.get_item(iid) for iid in batch),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, HNItem):
                    items.append(result)
                elif isinstance(result, Exception):
                    logger.warning("Failed to fetch HN item: %s", result)
        return items

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
