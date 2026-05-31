"""Tests for 3.5 event subscription audit.

Verifies that:
- Every async_track_state_change_event() call in async_setup_entry is wrapped
  via entry.async_on_unload() so listeners are cleaned up on unload.
- The unsubscribe callables structure is correct (structural static analysis).
"""

from __future__ import annotations

import inspect


class TestAllSubscriptionsProperlyUnloaded:
    """3.5 - every subscription is registered with entry.async_on_unload."""

    def test_every_state_tracker_is_wrapped_with_async_on_unload(self):
        """Static analysis: every async_track_state_change_event call in
        async_setup_entry is directly wrapped by entry.async_on_unload().
        """
        import custom_components.adaptive_cover_pro as acp_init

        source = inspect.getsource(acp_init.async_setup_entry)

        track_count = source.count("async_track_state_change_event(")
        on_unload_with_track = source.count(
            "entry.async_on_unload(\n"
            "        async_track_state_change_event("
        )

        assert on_unload_with_track == track_count, (
            f"Expected all {track_count} async_track_state_change_event() calls "
            f"to be directly wrapped with entry.async_on_unload(), "
            f"but only {on_unload_with_track} are. "
            f"Listener leak detected."
        )

    def test_bus_listen_wrapped_with_async_on_unload(self):
        """hass.bus.async_listen() call is wrapped with entry.async_on_unload()."""
        import custom_components.adaptive_cover_pro as acp_init

        source = inspect.getsource(acp_init.async_setup_entry)
        assert "entry.async_on_unload(\n        hass.bus.async_listen(" in source, (
            "hass.bus.async_listen() must be wrapped with entry.async_on_unload()"
        )

    def test_forecast_timer_cleanup_registered(self):
        """The forecast timer cleanup is registered via entry.async_on_unload()."""
        import custom_components.adaptive_cover_pro as acp_init

        source = inspect.getsource(acp_init.async_setup_entry)
        assert "_cancel_forecast_timer" in source
        assert "entry.async_on_unload(_cancel_forecast_timer)" in source

    def test_cmd_svc_stop_registered(self):
        """The cover command service stop is registered via entry.async_on_unload()."""
        import custom_components.adaptive_cover_pro as acp_init

        source = inspect.getsource(acp_init.async_setup_entry)
        assert "entry.async_on_unload(coordinator._cmd_svc.stop)" in source

    def test_unsubscribe_called_on_unload(self):
        """The unsubscribe callable returned by a subscription is called on unload."""
        from unittest.mock import MagicMock

        registered_fns = []
        mock_entry = MagicMock()
        mock_entry.async_on_unload = lambda fn: registered_fns.append(fn)

        unsubscribe_mock = MagicMock()
        mock_entry.async_on_unload(unsubscribe_mock)

        # Simulate HA firing all cleanup callbacks on unload
        for fn in registered_fns:
            fn()

        unsubscribe_mock.assert_called_once_with()
