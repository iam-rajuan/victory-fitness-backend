from __future__ import annotations

import importlib
import unittest
from unittest.mock import AsyncMock, patch


content_router_module = importlib.import_module("app.api.routers.content")


class HomepageQuoteRotationTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_quote_remains_default_for_existing_clients(self) -> None:
        quotes = [
            {"id": "quote-1", "text": "First", "author": "Victor Akko", "active": True, "selected": False},
            {"id": "quote-2", "text": "Second", "author": "Victor Akko", "active": True, "selected": True},
        ]

        with patch.object(content_router_module, "_load_homepage_quotes", AsyncMock(return_value=quotes)):
            quote = await content_router_module.get_homepage_quote(app_version="1.0.0")

        self.assertIsNotNone(quote)
        self.assertEqual(quote.id, "quote-2")

    async def test_rotating_quote_avoids_previous_quote_when_possible(self) -> None:
        quotes = [
            {"id": "quote-1", "text": "First", "author": "Victor Akko", "active": True, "selected": True},
            {"id": "quote-2", "text": "Second", "author": "Victor Akko", "active": True, "selected": False},
            {"id": "quote-3", "text": "Third", "author": "Victor Akko", "active": True, "selected": False},
        ]

        with patch.object(content_router_module, "_load_homepage_quotes", AsyncMock(return_value=quotes)):
            quote = await content_router_module.get_homepage_quote(
                app_version="1.0.0",
                rotate=True,
                previous_quote_id="quote-1",
                nonce="refresh-1",
            )

        self.assertIsNotNone(quote)
        self.assertIn(quote.id, {"quote-2", "quote-3"})
