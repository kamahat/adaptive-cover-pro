"""Oscillating (drop-arm / pivoting) awning cover calculation (#412).

Unlike a fixed-angle awning, an oscillating awning's arm sweeps through an arc
as it opens, so the fabric's horizontal reach is a function of the open
percentage rather than a configured constant. This engine:

1. Computes the horizontal reach (metres) needed to shade the window at the
   configured shaded distance — reusing the horizontal-awning projection math
   with a flat fabric (the needed *reach*, independent of the arm sweep).
2. Inverts the arm-sweep arc to find the open percentage whose fabric tip
   reaches that far: ``reach(p) = arm_length · sin(theta(p))`` where
   ``theta(p) = min_angle + (max_angle − min_angle)·p/100``.

This is a first-order geometric model (linear arm sweep, arc projection). It
matches the reporter's description in #412 (arm length + total sweep angle) and
can be refined with measured angle-vs-extension data later.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ...config_types import OscillatingConfig
from .horizontal import AdaptiveHorizontalCover


@dataclass
class AdaptiveOscillatingCover(AdaptiveHorizontalCover):
    """Calculate state for oscillating (drop-arm) awnings."""

    osc_config: OscillatingConfig = None  # type: ignore[assignment]

    @property
    def awn_length(self) -> float:
        """Max horizontal reach scale = the arm length."""
        return self.osc_config.arm_length

    @property
    def awn_angle(self) -> float:
        """Use a flat fabric for the *needed-reach* projection.

        The arm sweep is applied in ``calculate_percentage`` via the arc
        inverse, so the reach computation itself treats the fabric as
        horizontal (angle 0).
        """
        return 0.0

    def calculate_percentage(self) -> float:
        """Map the needed horizontal reach to an open percentage via the arc.

        ``calculate_position`` (inherited) returns the horizontal reach in
        metres needed to block the sun, clamped to ``arm_length``. The open
        percentage is the point on the linear arm sweep whose fabric tip
        projects that far.
        """
        arm = self.osc_config.arm_length
        lo = float(self.osc_config.min_angle)
        hi = float(self.osc_config.max_angle)
        if arm <= 0 or hi <= lo:
            return 0.0

        needed = self.calculate_position()
        frac = float(np.clip(needed / arm, 0.0, 1.0))
        # Arm angle (from the closed position) whose horizontal projection
        # equals the needed reach: reach = arm · sin(theta).
        theta = float(np.degrees(np.arcsin(frac)))
        pos = (theta - lo) / (hi - lo) * 100.0
        return float(np.clip(pos, 0, 100))
