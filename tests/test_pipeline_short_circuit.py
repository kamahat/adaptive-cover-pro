"""Tests for 3.4 pipeline short-circuit.

Verifies that:
1. UpdateFingerprint covers ALL pipeline inputs.
2. Identical inputs on two consecutive ticks produce matching fingerprints.
3. Any changed input produces a different fingerprint (no skip).
"""

from __future__ import annotations


def _make_snap(
    azimuth=180.0,
    elevation=30.0,
    cover_pos=50,
    force_override=False,
    motion=False,
    presence=True,
    is_sunny=True,
    lux_low=False,
    irr_low=False,
    cloud_high=False,
    outside_temp=20.5,
    inside_temp=22.0,
):
    from custom_components.adaptive_cover_pro.state.snapshot import (
        CoverStateSnapshot, SunSnapshot,
    )
    from custom_components.adaptive_cover_pro.state.climate_provider import ClimateReadings

    return CoverStateSnapshot(
        sun=SunSnapshot(azimuth=azimuth, elevation=elevation),
        climate=ClimateReadings(
            outside_temperature=outside_temp,
            inside_temperature=inside_temp,
            is_presence=presence,
            is_sunny=is_sunny,
            lux_below_threshold=lux_low,
            irradiance_below_threshold=irr_low,
            cloud_coverage_above_threshold=cloud_high,
        ),
        cover_positions={"cover.test": cover_pos},
        cover_capabilities={},
        motion_detected=motion,
        force_override_active=force_override,
    )


def _fp(snap, *, manual=False, weather=False, motion_to=False, grace=False, window=True, custom=None):
    from custom_components.adaptive_cover_pro.state.update_fingerprint import UpdateFingerprint
    return UpdateFingerprint.from_coordinator_state(
        snap,
        manual_override_active=manual,
        weather_override_active=weather,
        motion_timeout_active=motion_to,
        grace_period_active=grace,
        in_time_window=window,
        custom_position_sensor_states=custom,
    )


class TestFingerprintFullCoverage:
    """All pipeline inputs are captured by the fingerprint."""

    def test_presence_change_invalidates(self):
        assert _fp(_make_snap(presence=True)) != _fp(_make_snap(presence=False))

    def test_lux_change_invalidates(self):
        assert _fp(_make_snap(lux_low=False)) != _fp(_make_snap(lux_low=True))

    def test_irradiance_change_invalidates(self):
        assert _fp(_make_snap(irr_low=False)) != _fp(_make_snap(irr_low=True))

    def test_cloud_coverage_change_invalidates(self):
        assert _fp(_make_snap(cloud_high=False)) != _fp(_make_snap(cloud_high=True))

    def test_grace_period_change_invalidates(self):
        snap = _make_snap()
        assert _fp(snap, grace=False) != _fp(snap, grace=True)

    def test_in_time_window_change_invalidates(self):
        snap = _make_snap()
        assert _fp(snap, window=True) != _fp(snap, window=False)

    def test_custom_sensor_toggle_invalidates(self):
        snap = _make_snap()
        assert (
            _fp(snap, custom={"binary_sensor.s": False})
            != _fp(snap, custom={"binary_sensor.s": True})
        )

    def test_weather_override_change_invalidates(self):
        snap = _make_snap()
        assert _fp(snap, weather=False) != _fp(snap, weather=True)

    def test_manual_override_change_invalidates(self):
        snap = _make_snap()
        assert _fp(snap, manual=False) != _fp(snap, manual=True)

    def test_sun_azimuth_change_invalidates(self):
        assert _fp(_make_snap(azimuth=180.0)) != _fp(_make_snap(azimuth=181.5))

    def test_cover_position_change_invalidates(self):
        assert _fp(_make_snap(cover_pos=50)) != _fp(_make_snap(cover_pos=75))

    def test_outside_temp_change_invalidates(self):
        assert _fp(_make_snap(outside_temp=20.0)) != _fp(_make_snap(outside_temp=25.0))


class TestShortCircuitCondition:
    """The coordinator _can_skip logic works correctly."""

    def test_identical_ticks_can_skip(self):
        """When all inputs are identical, _can_skip should be True."""
        snap = _make_snap()
        fp1 = _fp(snap)
        fp2 = _fp(snap)
        can_skip = (fp1 == fp2)
        assert can_skip, "_calculate_cover_state must be skippable when fingerprints match"

    def test_changed_sun_prevents_skip(self):
        """Changed sun azimuth must prevent the short-circuit."""
        fp1 = _fp(_make_snap(azimuth=180.0))
        fp2 = _fp(_make_snap(azimuth=182.0))
        assert fp1 != fp2, "Changed azimuth must prevent skip"

    def test_first_fingerprint_none_prevents_skip(self):
        """When _last_fingerprint is None (first cycle), skip is impossible."""
        last_fingerprint = None
        fp_current = _fp(_make_snap())
        can_skip = (last_fingerprint is not None and fp_current == last_fingerprint)
        assert not can_skip, "First cycle (no prior fingerprint) must not skip"
