"""Tests for 3.3 coordinator update batching — SunGeometryCache.

Verifies that:
- SunGeometryCache computes geometry exactly once per (azimuth_left,
  azimuth_right, latitude, longitude) group per minute bucket.
- In a 10-cover simulation where all covers share the same facade config,
  the compute_fn is called exactly once per minute tick.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass


@dataclass
class _FakeCoverConfig:
    azimuth_left: float
    azimuth_right: float
    latitude: float
    longitude: float


class TestSunGeometryCache:
    """3.3 - SunGeometryCache: shared geometry for covers on the same facade."""

    def _make_covers(self, n: int, *, same_facade: bool = True):
        if same_facade:
            return [_FakeCoverConfig(200.0, 260.0, 48.8, 2.3) for _ in range(n)]
        return [
            _FakeCoverConfig(200.0 + i * 10, 260.0, 48.8, 2.3)
            for i in range(n)
        ]

    def test_cache_computes_once_for_identical_facades(self):
        """10 covers on the same facade: sun geometry computed once per tick."""
        from custom_components.adaptive_cover_pro.engine.sun_geometry_cache import (
            SunGeometryCache,
        )

        cache = SunGeometryCache()
        compute_count = 0

        def _fake_compute(azi_left, azi_right, lat, lon):
            nonlocal compute_count
            compute_count += 1
            return {"computed": True, "azi_left": azi_left}

        covers = self._make_covers(10)
        minute_bucket = datetime.datetime(2024, 6, 1, 12, 0, 0)

        results = []
        for cover in covers:
            result = cache.get_or_compute(
                azimuth_left=cover.azimuth_left,
                azimuth_right=cover.azimuth_right,
                latitude=cover.latitude,
                longitude=cover.longitude,
                minute_bucket=minute_bucket,
                compute_fn=_fake_compute,
            )
            results.append(result)

        assert compute_count == 1, (
            f"Sun geometry must be computed exactly once for 10 covers on the same "
            f"facade, but compute_fn was called {compute_count} times"
        )
        assert all(r == results[0] for r in results), "All results must be identical"

    def test_cache_computes_once_per_unique_facade(self):
        """10 covers on 10 different facades: geometry computed 10 times."""
        from custom_components.adaptive_cover_pro.engine.sun_geometry_cache import (
            SunGeometryCache,
        )

        cache = SunGeometryCache()
        compute_count = 0

        def _fake_compute(azi_left, azi_right, lat, lon):
            nonlocal compute_count
            compute_count += 1
            return {"computed": True}

        covers = self._make_covers(10, same_facade=False)
        minute_bucket = datetime.datetime(2024, 6, 1, 12, 0, 0)

        for cover in covers:
            cache.get_or_compute(
                azimuth_left=cover.azimuth_left,
                azimuth_right=cover.azimuth_right,
                latitude=cover.latitude,
                longitude=cover.longitude,
                minute_bucket=minute_bucket,
                compute_fn=_fake_compute,
            )

        assert compute_count == 10, "Each unique facade must produce exactly one compute call"

    def test_cache_invalidates_on_minute_tick(self):
        """After the minute bucket advances, values are recomputed."""
        from custom_components.adaptive_cover_pro.engine.sun_geometry_cache import (
            SunGeometryCache,
        )

        cache = SunGeometryCache()
        compute_count = 0

        def _fake_compute(azi_left, azi_right, lat, lon):
            nonlocal compute_count
            compute_count += 1
            return {"tick": compute_count}

        now = datetime.datetime(2024, 6, 1, 12, 0, 0)
        next_minute = now + datetime.timedelta(minutes=1)

        cache.get_or_compute(200.0, 260.0, 48.8, 2.3, minute_bucket=now, compute_fn=_fake_compute)
        assert compute_count == 1

        # Same minute again: cached, no recompute
        cache.get_or_compute(200.0, 260.0, 48.8, 2.3, minute_bucket=now, compute_fn=_fake_compute)
        assert compute_count == 1

        # Next minute: recomputed
        cache.get_or_compute(200.0, 260.0, 48.8, 2.3, minute_bucket=next_minute, compute_fn=_fake_compute)
        assert compute_count == 2, "Cache must recompute after minute tick"

    def test_10_cover_simulation_geometry_computed_once_per_minute(self):
        """Full 10-cover simulation: geometry computed exactly once per minute tick."""
        from custom_components.adaptive_cover_pro.engine.sun_geometry_cache import (
            SunGeometryCache,
        )

        cache = SunGeometryCache()
        ticks = [
            datetime.datetime(2024, 6, 1, 12, m, 0)
            for m in range(5)
        ]
        covers = self._make_covers(10)
        compute_calls_per_tick = []

        for tick in ticks:
            tick_count = 0

            def _fake_compute(a, b, c, d, _tc=None):
                nonlocal tick_count
                tick_count += 1
                return {"result": tick_count}

            for cover in covers:
                cache.get_or_compute(
                    azimuth_left=cover.azimuth_left,
                    azimuth_right=cover.azimuth_right,
                    latitude=cover.latitude,
                    longitude=cover.longitude,
                    minute_bucket=tick,
                    compute_fn=_fake_compute,
                )
            compute_calls_per_tick.append(tick_count)

        assert all(c == 1 for c in compute_calls_per_tick), (
            f"Expected 1 compute call per minute tick, got: {compute_calls_per_tick}"
        )
