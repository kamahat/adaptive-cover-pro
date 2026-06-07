"""Security handler - closes covers when no presence is detected.

Priority 95: between force_override (100) and weather_override (90).

When a presence/occupancy sensor is configured and reports 'off' (no one home),
this handler closes all covers to the configured security position (default 0%).
Fail-safe: unavailable/unknown sensor state is treated as "present" so covers
are never accidentally closed by a flapping sensor.
"""

from __future__ import annotations

from ...const import ControlMethod
from ..handler import OverrideHandler
from ..helpers import compute_raw_calculated_position
from ..types import PipelineResult, PipelineSnapshot


class SecurityHandler(OverrideHandler):
    """Closes covers when presence sensor is inactive (no one home).

    Priority 95: fires after ForceOverrideHandler (100) but before
    WeatherOverrideHandler (90), so security always wins over weather
    but can still be overridden by a manual force-override sensor.

    Fail-safe rule: when the presence sensor is unavailable or unknown,
    the handler passes (returns None) - covers are never closed by a
    sensor glitch.
    """

    name = "security"
    priority = 95

    def evaluate(self, snapshot: PipelineSnapshot) -> PipelineResult | None:
        """Return closed position when security mode is active and no presence."""
        if not snapshot.security_mode_active:
            return None

        # Presence sensor is present (True) or sensor is unavailable ? pass through
        if snapshot.security_presence_detected:
            return None

        pos = snapshot.security_close_position
        raw = compute_raw_calculated_position(snapshot)
        return PipelineResult(
            position=pos,
            control_method=ControlMethod.SECURITY,
            reason=f"security mode active - no presence detected, closing to {pos}%",
            bypass_auto_control=True,
            raw_calculated_position=raw,
        )

    def describe_skip(self, snapshot: PipelineSnapshot) -> str:
        """Reason when security handler does not fire."""
        if not snapshot.security_mode_active:
            return "security mode not configured"
        return "presence detected - security inactive"
