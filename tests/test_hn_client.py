"""Tests for the HN API client using respx to mock HTTP calls."""

import pytest
import respx

from src.hn.client import BASE_URL, HNClient


@pytest.fixture
def mock_api():
    with respx.mock(base_url=BASE_URL) as rsps:
        yield rsps


@pytest.fixture
async def client():
    c = HNClient()
    yield c
    await c.close()


class TestHNClient:
    async def test_get_top_story_ids(self, mock_api, client):
        mock_api.get("/topstories.json").respond(json=list(range(1, 101)))
        ids = await client.get_top_story_ids(limit=10)
        assert ids == list(range(1, 11))

    async def test_get_show_hn_ids(self, mock_api, client):
        mock_api.get("/showstories.json").respond(json=[42, 43, 44])
        ids = await client.get_show_hn_ids(limit=5)
        assert ids == [42, 43, 44]

    async def test_get_item(self, mock_api, client):
        mock_api.get("/item/42.json").respond(
            json={
                "id": 42,
                "type": "story",
                "title": "Show HN: Acme",
                "url": "https://acme.com",
                "score": 100,
                "by": "user1",
                "descendants": 25,
                "time": 1700000000,
            }
        )
        item = await client.get_item(42)
        assert item is not None
        assert item.id == 42
        assert item.title == "Show HN: Acme"
        assert item.score == 100

    async def test_get_item_not_found(self, mock_api, client):
        mock_api.get("/item/999.json").respond(text="null")
        item = await client.get_item(999)
        assert item is None

    async def test_get_items_batch(self, mock_api, client):
        for i in [1, 2, 3]:
            mock_api.get(f"/item/{i}.json").respond(
                json={"id": i, "type": "story", "title": f"Story {i}"}
            )
        items = await client.get_items([1, 2, 3])
        assert len(items) == 3
