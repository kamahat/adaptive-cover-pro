"""Motion sensor timeout management for Adaptive Cover Pro."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING
from collections.abc import Callable

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from ..const import DEFAULT_MOTION_TIMEOUT
from ..helpers import is_entity_active
from .common import EventRecorder, TimeoutController


class MotionManager:
    """Manage motion sensor state and timeout tracking for cover control."""

    def __init__(self, hass: HomeAssistant, logger, *, event_buffer=None) -> None:
        self._hass = hass
        self._logger = logger
        self._event_buffer = event_buffer
        self._events = EventRecorder(event_buffer, now_fn=self._now)

        self._sensors: list[str] = []
        self._timeout_seconds: int = DEFAULT_MOTION_TIMEOUT
        self._timer = TimeoutController(logger, label="motion timeout")
        self._last_motion_time: float | None = None
        self._motion_timeout_active: bool = False

    @staticmethod
    def _now() -> dt.datetime:
        return dt.datetime.now(dt.UTC)

    def update_config(self, sensors: list[str], timeout_seconds: int) -> None:
        self._sensors = list(sensors)
        self._timeout_seconds = timeout_seconds

    @property
    def is_motion_detected(self) -> bool:
        if not self._sensors:
            return True
        return any(is_entity_active(self._hass, sid) for sid in self._sensors)

    @property
    def is_motion_timeout_active(self) -> bool:
        if not self._sensors:
            return False
        return self._motion_timeout_active

    @property
    def has_pending_timeout(self) -> bool:
        return self._timer.is_running

    @property
    def last_motion_time(self) -> float | None:
        return self._last_motion_time

    def set_no_motion(self) -> None:
        self.cancel_motion_timeout()
        self._motion_timeout_active = True

    def record_motion_detected(self) -> bool:
        had_pending = self._timer.is_running
        had_active = self._motion_timeout_active
        self.cancel_motion_timeout()
        self._last_motion_time = self._now().timestamp()
        self._motion_timeout_active = False
        return had_active or had_pending

    def start_motion_timeout(self, refresh_callback: Callable) -> None:
        """Start the no-motion timeout task.

        Cancels any existing timeout before creating a new one so only one
        timer runs at a time.

        Args:
            refresh_callback: Async callable invoked when timeout expires and
                covers should switch to the default position.  Typically
                ``coordinator.async_refresh``.

        """
        # Record the "cancelled" event before the controller swaps timers
        # so the diagnostic ring still shows the cancel-on-restart edge.
        if self._timer.is_running:
            self._events.record("motion_timeout_canceled")

        timeout_seconds = self._timeout_seconds
        self._logger.info(
            "No motion detected - starting %s second timeout before using default position",
            timeout_seconds,
        )
        self._events.record("motion_timeout_started", timeout_seconds=timeout_seconds)

        async def _on_expire() -> None:
            await self._on_motion_timeout_expired(timeout_seconds, refresh_callback)

        self._timer.start(timeout_seconds, _on_expire)

    async def _on_motion_timeout_expired(
        self, timeout_seconds: int, refresh_callback: Callable
    ) -> None:
        if self.is_motion_detected:
            self._logger.debug(
                "Motion detected during timeout - canceling default position"
            )
            self._events.record("motion_detected_during_timeout")
            return
        self._motion_timeout_active = True
        self._logger.info(
            "Motion timeout expired (%s seconds) - using default position",
            timeout_seconds,
        )
        self._events.record("motion_timeout_expired", timeout_seconds=timeout_seconds)

        await refresh_callback()

    def cancel_motion_timeout(self) -> None:
        """Cancel the running timeout task, if any."""
        if self._timer.is_running:
            self._events.record("motion_timeout_canceled")
        self._timer.cancel()
