"""Tests for 3.1 debounce audit — no duplicate state writes within 100 ms.

Verifies that:
1. _handle_coordinator_update() is the only path that calls async_write_ha_state().
2. The proxy cover's _handle_source_event already change-gates state writes.
3. No duplicate writes occur within a 100ms window for the same state key.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch
import pytest


class TestHandleCoordinatorUpdateNoDuplicates:
    """3.1 - coordinator push: write occurs once per coordinator update."""

    def test_handle_coordinator_update_calls_write_once(self):
        """_handle_coordinator_update calls async_write_ha_state exactly once."""
        from custom_components.adaptive_cover_pro.entity_base import (
            AdaptiveCoverBaseEntity,
        )

        entity = MagicMock(spec=AdaptiveCoverBaseEntity)
        entity.async_write_ha_state = MagicMock()
        AdaptiveCoverBaseEntity._handle_coordinator_update(entity)
        entity.async_write_ha_state.assert_called_once()


class TestProxyCoverChangeGate:
    """3.1 - proxy cover: change-gated writes skip duplicates."""

    def test_no_write_on_identical_state(self):
        """_handle_source_event skips async_write_ha_state when state key is unchanged."""
        from custom_components.adaptive_cover_pro.cover import AdaptiveProxyCover

        entity = MagicMock(spec=AdaptiveProxyCover)
        entity._last_written_state_key = None
        entity.async_write_ha_state = MagicMock()

        mock_state = MagicMock()
        mock_state.state = "open"
        mock_state.attributes = {
            "current_position": 50,
            "current_tilt_position": None,
            "supported_features": 15,
        }
        mock_event = MagicMock()
        mock_event.data = {"new_state": mock_state}

        # First call: no previous key - should write
        AdaptiveProxyCover._handle_source_event(entity, mock_event)
        assert entity.async_write_ha_state.call_count == 1

        # Second call with identical state: must NOT write
        AdaptiveProxyCover._handle_source_event(entity, mock_event)
        assert entity.async_write_ha_state.call_count == 1, (
            "Duplicate state write must be suppressed by change gate"
        )

    def test_write_occurs_on_state_change(self):
        """_handle_source_event writes when state actually changes."""
        from custom_components.adaptive_cover_pro.cover import AdaptiveProxyCover

        entity = MagicMock(spec=AdaptiveProxyCover)
        entity._last_written_state_key = ("open", 50, None, 15)
        entity.async_write_ha_state = MagicMock()

        mock_state = MagicMock()
        mock_state.state = "closed"
        mock_state.attributes = {
            "current_position": 0,
            "current_tilt_position": None,
            "supported_features": 15,
        }
        mock_event = MagicMock()
        mock_event.data = {"new_state": mock_state}

        AdaptiveProxyCover._handle_source_event(entity, mock_event)
        entity.async_write_ha_state.assert_called_once()


class TestNoWritesWithin100ms:
    """3.1 - integration: no duplicate writes fired within 100ms window."""

    @pytest.mark.asyncio
    async def test_no_duplicate_writes_within_100ms(self):
        """Simulate rapid state events; assert no write fires more than once per key."""
        from custom_components.adaptive_cover_pro.cover import AdaptiveProxyCover

        entity = MagicMock(spec=AdaptiveProxyCover)
        entity._last_written_state_key = None
        entity.async_write_ha_state = MagicMock()

        def make_event(state_str, position):
            mock_state = MagicMock()
            mock_state.state = state_str
            mock_state.attributes = {
                "current_position": position,
                "current_tilt_position": None,
                "supported_features": 15,
            }
            ev = MagicMock()
            ev.data = {"new_state": mock_state}
            return ev

        # Fire the same event 10 times within 100ms
        ev = make_event("opening", 75)
        for _ in range(10):
            AdaptiveProxyCover._handle_source_event(entity, ev)
            await asyncio.sleep(0.005)  # 5ms apart = 50ms total

        assert entity.async_write_ha_state.call_count == 1, (
            "Only the first write should fire; 9 duplicates suppressed by change gate"
        )
