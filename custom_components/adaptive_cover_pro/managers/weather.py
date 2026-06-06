"""Weather condition override management for Adaptive Cover Pro."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ..const import (
    DEFAULT_WEATHER_RAIN_THRESHOLD,
    DEFAULT_WEATHER_TIMEOUT,
    DEFAULT_WEATHER_WIND_DIRECTION_TOLERANCE,
    DEFAULT_WEATHER_WIND_SPEED_THRESHOLD,
    DEFAULT_WINDOW_AZIMUTH,
    DEGREES_IN_CIRCLE,
)
from .common import EventRecorder, TimeoutController

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_COND_WIND_SPEED = "wind_speed"
_COND_RAIN_RATE = "rain_rate"
_COND_IS_RAINING = "is_raining"
_COND_IS_WINDY = "is_windy"
_COND_SEVERE = "severe_weather"


class WeatherManager:
    """Manage weather-based safety overrides for cover control."""

    def __init__(self, hass: HomeAssistant, logger, *, event_buffer=None) -> None:
        self._hass = hass
        self._logger = logger
        self._event_buffer = event_buffer
        self._events = EventRecorder(event_buffer)

        # Config (updated via update_config)
        self._wind_speed_sensor: str | None = None
        self._wind_direction_sensor: str | None = None
        self._wind_speed_threshold: float = DEFAULT_WEATHER_WIND_SPEED_THRESHOLD
        self._wind_direction_tolerance: int = DEFAULT_WEATHER_WIND_DIRECTION_TOLERANCE
        self._win_azi: int = DEFAULT_WINDOW_AZIMUTH
        self._rain_sensor: str | None = None
        self._rain_threshold: float = DEFAULT_WEATHER_RAIN_THRESHOLD
        self._is_raining_sensor: str | None = None
        self._is_windy_sensor: str | None = None
        self._severe_sensors: list[str] = []
        self._timeout_seconds: int = DEFAULT_WEATHER_TIMEOUT
        self._timer = TimeoutController(logger, label="weather clear-delay")
        self._override_active: bool = False

    def update_config(
        self,
        *,
        wind_speed_sensor: str | None,
        wind_direction_sensor: str | None,
        wind_speed_threshold: float,
        wind_direction_tolerance: int,
        win_azi: int,
        rain_sensor: str | None,
        rain_threshold: float,
        is_raining_sensor: str | None,
        is_windy_sensor: str | None,
        severe_sensors: list[str],
        timeout_seconds: int,
    ) -> None:
        self._wind_speed_sensor = wind_speed_sensor
        self._wind_direction_sensor = wind_direction_sensor
        self._wind_speed_threshold = wind_speed_threshold
        self._wind_direction_tolerance = wind_direction_tolerance
        self._win_azi = win_azi
        self._rain_sensor = rain_sensor
        self._rain_threshold = rain_threshold
        self._is_raining_sensor = is_raining_sensor
        self._is_windy_sensor = is_windy_sensor
        self._severe_sensors = list(severe_sensors)
        self._timeout_seconds = timeout_seconds

    @property
    def configured_sensors(self) -> list[str]:
        sensors: list[str] = []
        for entity_id in [self._wind_speed_sensor, self._wind_direction_sensor, self._rain_sensor, self._is_raining_sensor, self._is_windy_sensor]:
            if entity_id:
                sensors.append(entity_id)
        sensors.extend(self._severe_sensors)
        return sensors

    @property
    def is_any_condition_active(self) -> bool:
        return (
            self._is_wind_active()
            or self._is_rain_active()
            or self._is_binary_on(self._is_raining_sensor)
            or self._is_binary_on(self._is_windy_sensor)
            or self._is_any_severe_active()
        )

    @property
    def is_weather_override_active(self) -> bool:
        if not self.configured_sensors:
            return False
        return self._override_active

    @property
    def is_timeout_running(self) -> bool:
        return self._timer.is_running

    @property
    def in_clear_delay(self) -> bool:
        return self.is_timeout_running

    @property
    def active_conditions(self) -> list[str]:
        result = []
        if self._is_wind_active(): result.append(_COND_WIND_SPEED)
        if self._is_rain_active(): result.append(_COND_RAIN_RATE)
        if self._is_binary_on(self._is_raining_sensor): result.append(_COND_IS_RAINING)
        if self._is_binary_on(self._is_windy_sensor): result.append(_COND_IS_WINDY)
        if self._is_any_severe_active(): result.append(_COND_SEVERE)
        return result

    def _is_wind_active(self) -> bool:
        if not self._wind_speed_sensor: return False
        state = self._hass.states.get(self._wind_speed_sensor)
        if not state or state.state in ("unavailable", "unknown"): return False
        try:
            speed = float(state.state)
        except (ValueError, TypeError):
            return False
        if speed < self._wind_speed_threshold: return False
        if self._wind_direction_sensor:
            dir_state = self._hass.states.get(self._wind_direction_sensor)
            if dir_state and dir_state.state not in ("unavailable", "unknown"):
                try:
                    direction = float(dir_state.state)
                except (ValueError, TypeError):
                    return True
                diff = abs(direction - self._win_azi) % DEGREES_IN_CIRCLE
                angular_dist = min(diff, DEGREES_IN_CIRCLE - diff)
                if angular_dist > self._wind_direction_tolerance: return False
        return True

    def _is_rain_active(self) -> bool:
        if not self._rain_sensor: return False
        state = self._hass.states.get(self._rain_sensor)
        if not state or state.state in ("unavailable", "unknown"): return False
        try:
            rate = float(state.state)
        except (ValueError, TypeError):
            return False
        return rate >= self._rain_threshold

    def _is_binary_on(self, entity_id: str | None) -> bool:
        if not entity_id: return False
        state = self._hass.states.get(entity_id)
        return bool(state and state.state == "on")

    def _is_any_severe_active(self) -> bool:
        return any(self._is_binary_on(eid) for eid in self._severe_sensors)

    def record_conditions_active(self) -> None:
        self.cancel_weather_timeout()
        previous = self._override_active
        self._override_active = True
        if not previous:
            self._events.record(
                "weather_override_changed",
                entity_id="",
                previous=False,
                current=True,
            )

    def reconcile(self) -> str | None:
        if not self.configured_sensors: return None
        if not self._override_active: return None
        if self.is_any_condition_active: return None
        if self.is_timeout_running: return None
        return "should_start_timeout"

    def start_weather_timeout(self, refresh_callback: Callable) -> None:
        timeout_seconds = self._timeout_seconds
        self._logger.info("Weather conditions cleared — starting %s second delay before resuming normal control", timeout_seconds)

        async def _on_expire() -> None:
            await self._on_weather_timeout_expired(timeout_seconds, refresh_callback)

        self._timer.start(timeout_seconds, _on_expire)

    async def _on_weather_timeout_expired(self, timeout_seconds: int, refresh_callback: Callable) -> None:
        if self.is_any_condition_active:
            self._logger.debug("Weather conditions returned during clear-delay — keeping override active")
            self._override_active = True
            return
        self._override_active = False
        self._events.record(
            "weather_override_changed",
            entity_id="",
            previous=True,
            current=False,
            reason=f"clear-delay expired ({timeout_seconds}s)",
        )
        self._logger.info(
            "Weather clear-delay expired (%s seconds) — resuming normal control",
            timeout_seconds,
        )

        await refresh_callback()

    def cancel_weather_timeout(self) -> None:
        self._timer.cancel()
