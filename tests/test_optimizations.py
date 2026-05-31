"""Tests for Section 3 performance optimizations.

1. geometry.py lru_cache — identical (gamma, sol_elev) inputs return cached results.
2. UpdateFingerprint equality contract.
3. UpdateFingerprint change detection on sun position change.
4. Cache hit rate simulation for a 10-cover identical-orientation setup.
"""

from __future__ import annotations

from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# 1. Geometry lru_cache
# ---------------------------------------------------------------------------


class TestGeometryCache:
    """SafetyMarginCalculator and EdgeCaseHandler results are cached."""

    def test_safety_margin_cached_identical_inputs(self):
        """Calling calculate() twice with same args hits the lru_cache."""
        from custom_components.adaptive_cover_pro.geometry import (
            SafetyMarginCalculator,
            _calculate_safety_margin,
        )

        # Clear cache first so this test is isolated
        _calculate_safety_margin.cache_clear()

        result1 = SafetyMarginCalculator.calculate(30.0, 45.0)
        cache_info_after_first = _calculate_safety_margin.cache_info()
        assert cache_info_after_first.misses == 1
        assert cache_info_after_first.hits == 0

        result2 = SafetyMarginCalculator.calculate(30.0, 45.0)
        cache_info_after_second = _calculate_safety_margin.cache_info()
        assert cache_info_after_second.hits == 1, (
            "Second call with identical inputs must be a cache hit"
        )
        assert result1 == result2, "Cached result must equal fresh result"

    def test_edge_case_handler_cached_identical_inputs(self):
        """Calling check_and_handle() twice with same args hits the lru_cache."""
        from custom_components.adaptive_cover_pro.geometry import (
            EdgeCaseHandler,
            _check_edge_case,
        )

        _check_edge_case.cache_clear()

        result1 = EdgeCaseHandler.check_and_handle(45.0, 20.0, 1.0, 2.0)
        cache_after_first = _check_edge_case.cache_info()
        assert cache_after_first.misses == 1

        result2 = EdgeCaseHandler.check_and_handle(45.0, 20.0, 1.0, 2.0)
        cache_after_second = _check_edge_case.cache_info()
        assert cache_after_second.hits == 1, "Second call must hit cache"
        assert result1 == result2

    def test_safety_margin_different_inputs_are_cache_misses(self):
        """Different (gamma, sol_elev) pairs generate distinct cache entries."""
        from custom_components.adaptive_cover_pro.geometry import (
            SafetyMarginCalculator,
            _calculate_safety_margin,
        )

        _calculate_safety_margin.cache_clear()

        r1 = SafetyMarginCalculator.calculate(10.0, 20.0)
        r2 = SafetyMarginCalculator.calculate(50.0, 20.0)  # different gamma
        r3 = SafetyMarginCalculator.calculate(10.0, 80.0)  # different elevation

        cache_info = _calculate_safety_margin.cache_info()
        assert cache_info.misses == 3, "Three distinct inputs must produce 3 misses"
        # Different angles should produce different margins
        # (not strictly required for correctness, but sanity-checks the cache key)
        assert r1 != r2 or r1 != r3  # at least two results differ

    def test_10_cover_cache_hit_rate(self):
        """Simulating 10 covers at same azimuth: 9 out of 10 calls are cache hits."""
        from custom_components.adaptive_cover_pro.geometry import (
            SafetyMarginCalculator,
            _calculate_safety_margin,
        )

        _calculate_safety_margin.cache_clear()

        # All 10 covers have the same gamma and sol_elev (same window orientation)
        gamma, sol_elev = 15.0, 35.0
        for _ in range(10):
            SafetyMarginCalculator.calculate(gamma, sol_elev)

        info = _calculate_safety_margin.cache_info()
        assert info.misses == 1, "Only the first call should miss the cache"
        assert info.hits == 9, "The remaining 9 calls must hit the cache"

    def test_safety_margin_returns_at_least_1(self):
        """Safety margin is always >= 1.0 (no negative correction)."""
        from custom_components.adaptive_cover_pro.geometry import SafetyMarginCalculator

        for gamma in [0.0, 45.0, 80.0, 90.0, -45.0]:
            for elev in [0.0, 10.0, 45.0, 75.0, 89.0]:
                margin = SafetyMarginCalculator.calculate(gamma, elev)
                assert margin >= 1.0, (
                    f"Safety margin must be >=1.0 for gamma={gamma}, elev={elev}"
                )


# ---------------------------------------------------------------------------
# 2 & 3. UpdateFingerprint
# ---------------------------------------------------------------------------


def _make_snapshot(azimuth: float = 180.0, elevation: float = 30.0):
    """Build a minimal CoverStateSnapshot for fingerprint tests."""
    from custom_components.adaptive_cover_pro.state.snapshot import (
        CoverStateSnapshot,
        SunSnapshot,
    )

    return CoverStateSnapshot(
        sun=SunSnapshot(azimuth=azimuth, elevation=elevation),
        climate=None,
        cover_positions={"cover.test": 50},
        cover_capabilities={},
        motion_detected=False,
        force_override_active=False,
    )


class TestUpdateFingerprint:
    """UpdateFingerprint equality and change detection."""

    def test_same_inputs_produce_equal_fingerprints(self):
        """Two snapshots with identical inputs produce equal fingerprints."""
        from custom_components.adaptive_cover_pro.state.update_fingerprint import (
            UpdateFingerprint,
        )

        snap1 = _make_snapshot(azimuth=180.0, elevation=30.0)
        snap2 = _make_snapshot(azimuth=180.0, elevation=30.0)

        fp1 = UpdateFingerprint.from_coordinator_state(
            snap1,
            manual_override_active=False,
            weather_override_active=False,
            motion_timeout_active=False,
        )
        fp2 = UpdateFingerprint.from_coordinator_state(
            snap2,
            manual_override_active=False,
            weather_override_active=False,
            motion_timeout_active=False,
        )
        assert fp1 == fp2, "Identical inputs must produce equal fingerprints"

    def test_changed_sun_azimuth_produces_different_fingerprint(self):
        """Changed sun azimuth (rounded to 1 dp) produces a different fingerprint."""
        from custom_components.adaptive_cover_pro.state.update_fingerprint import (
            UpdateFingerprint,
        )

        snap1 = _make_snapshot(azimuth=180.0, elevation=30.0)
        snap2 = _make_snapshot(azimuth=181.0, elevation=30.0)  # 1 degree change

        fp1 = UpdateFingerprint.from_coordinator_state(
            snap1,
            manual_override_active=False,
            weather_override_active=False,
            motion_timeout_active=False,
        )
        fp2 = UpdateFingerprint.from_coordinator_state(
            snap2,
            manual_override_active=False,
            weather_override_active=False,
            motion_timeout_active=False,
        )
        assert fp1 != fp2, "Changed azimuth must produce different fingerprint"

    def test_tiny_azimuth_change_below_rounding_threshold_matches(self):
        """A change of 0.05° is below the 1-dp rounding threshold and should match."""
        from custom_components.adaptive_cover_pro.state.update_fingerprint import (
            UpdateFingerprint,
        )

        snap1 = _make_snapshot(azimuth=180.000, elevation=30.0)
        snap2 = _make_snapshot(azimuth=180.049, elevation=30.0)  # rounds to 180.0

        fp1 = UpdateFingerprint.from_coordinator_state(
            snap1,
            manual_override_active=False,
            weather_override_active=False,
            motion_timeout_active=False,
        )
        fp2 = UpdateFingerprint.from_coordinator_state(
            snap2,
            manual_override_active=False,
            weather_override_active=False,
            motion_timeout_active=False,
        )
        assert fp1 == fp2, (
            "Sub-0.1-degree change should round to same value and match"
        )

    def test_changed_manual_override_flag_produces_different_fingerprint(self):
        """Toggling manual_override_active produces a different fingerprint."""
        from custom_components.adaptive_cover_pro.state.update_fingerprint import (
            UpdateFingerprint,
        )

        snap = _make_snapshot()
        fp_no_override = UpdateFingerprint.from_coordinator_state(
            snap,
            manual_override_active=False,
            weather_override_active=False,
            motion_timeout_active=False,
        )
        fp_with_override = UpdateFingerprint.from_coordinator_state(
            snap,
            manual_override_active=True,
            weather_override_active=False,
            motion_timeout_active=False,
        )
        assert fp_no_override != fp_with_override, (
            "Manual override flag change must invalidate fingerprint"
        )

    def test_changed_cover_position_produces_different_fingerprint(self):
        """A cover moving to a new position changes the fingerprint."""
        from custom_components.adaptive_cover_pro.state.snapshot import (
            CoverStateSnapshot,
            SunSnapshot,
        )
        from custom_components.adaptive_cover_pro.state.update_fingerprint import (
            UpdateFingerprint,
        )

        snap_before = CoverStateSnapshot(
            sun=SunSnapshot(azimuth=180.0, elevation=30.0),
            climate=None,
            cover_positions={"cover.test": 50},
            cover_capabilities={},
            motion_detected=False,
            force_override_active=False,
        )
        snap_after = CoverStateSnapshot(
            sun=SunSnapshot(azimuth=180.0, elevation=30.0),
            climate=None,
            cover_positions={"cover.test": 75},  # cover moved
            cover_capabilities={},
            motion_detected=False,
            force_override_active=False,
        )
        fp_before = UpdateFingerprint.from_coordinator_state(
            snap_before,
            manual_override_active=False,
            weather_override_active=False,
            motion_timeout_active=False,
        )
        fp_after = UpdateFingerprint.from_coordinator_state(
            snap_after,
            manual_override_active=False,
            weather_override_active=False,
            motion_timeout_active=False,
        )
        assert fp_before != fp_after, "Cover position change must invalidate fingerprint"

    def test_fingerprint_is_frozen_and_hashable(self):
        """UpdateFingerprint is frozen (immutable) and can be used in a set."""
        from custom_components.adaptive_cover_pro.state.update_fingerprint import (
            UpdateFingerprint,
        )

        snap = _make_snapshot()
        fp = UpdateFingerprint.from_coordinator_state(
            snap,
            manual_override_active=False,
            weather_override_active=False,
            motion_timeout_active=False,
        )
        # Frozen dataclasses are hashable
        fp_set = {fp}
        assert fp in fp_set, "Frozen UpdateFingerprint must be hashable"
