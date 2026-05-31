"""Per-minute TTL cache for sun geometry computations shared across covers.

Covers that share the same facade orientation (azimuth_left, azimuth_right)
at the same geographic location produce identical sun geometry on every
coordinator update cycle.  Without caching, a 10-cover setup computes the
same geometry 10 times per reconciliation tick.

``SunGeometryCache`` solves this by keying on
``(azimuth_left, azimuth_right, latitude, longitude, minute_bucket)``
where ``minute_bucket`` is the current wall-clock minute truncated to second=0.
The cache self-invalidates when the minute rolls over — no explicit eviction
required.

Thread-safety note
------------------
All coordinator activity runs on the HA event loop (single thread).  No
locking is required.
"""

from __future__ import annotations

import datetime
from typing import Any, Callable


class SunGeometryCache:
    """Minute-granularity cache for sun geometry keyed on facade + location.

    Usage example (inside coordinator.get_blind_data)::

        minute_bucket = datetime.datetime.now().replace(second=0, microsecond=0)
        geometry = self._sun_geometry_cache.get_or_compute(
            azimuth_left=config.fov_left,
            azimuth_right=config.fov_right,
            latitude=lat,
            longitude=lon,
            minute_bucket=minute_bucket,
            compute_fn=lambda al, ar, la, lo: _do_expensive_computation(al, ar, la, lo),
        )
    """

    def __init__(self) -> None:
        """Initialise an empty cache."""
        # Key: (azimuth_left, azimuth_right, latitude, longitude, minute_bucket)
        # Value: whatever compute_fn returns
        self._store: dict[tuple, Any] = {}
        # Track the minute bucket of the last stored entry so we can purge
        # stale entries efficiently without iterating the whole dict.
        self._last_minute: datetime.datetime | None = None

    def get_or_compute(
        self,
        *,
        azimuth_left: float,
        azimuth_right: float,
        latitude: float,
        longitude: float,
        minute_bucket: datetime.datetime,
        compute_fn: Callable[[float, float, float, float], Any],
    ) -> Any:
        """Return cached geometry or call *compute_fn* and cache the result.

        Args:
            azimuth_left:  Left edge of the cover's field of view (degrees).
            azimuth_right: Right edge of the cover's field of view (degrees).
            latitude:      Geographic latitude of the installation.
            longitude:     Geographic longitude of the installation.
            minute_bucket: ``datetime.now().replace(second=0, microsecond=0)``.
                           Controls cache TTL — the entire cache is flushed
                           whenever this value advances.
            compute_fn:    Called as ``compute_fn(azimuth_left, azimuth_right,
                           latitude, longitude)`` when the cache misses.

        Returns:
            The (possibly cached) geometry result.

        """
        # Flush stale entries when the minute rolls over.
        if self._last_minute is not None and minute_bucket != self._last_minute:
            self._store.clear()
        self._last_minute = minute_bucket

        key = (azimuth_left, azimuth_right, latitude, longitude, minute_bucket)
        if key not in self._store:
            self._store[key] = compute_fn(azimuth_left, azimuth_right, latitude, longitude)
        return self._store[key]

    def clear(self) -> None:
        """Explicitly flush all cached entries (e.g. on config reload)."""
        self._store.clear()
        self._last_minute = None
