"""Tests for the oscillating (drop-arm) awning cover type and the config
abstraction capabilities it exercises (#412).
"""

from __future__ import annotations

import math

import pytest

from custom_components.adaptive_cover_pro.config_types import OscillatingConfig
from custom_components.adaptive_cover_pro.const import (
    CONF_ARM_LENGTH,
    CONF_AWNING_ANGLE,
    CONF_AWNING_MAX_ANGLE,
    CONF_AWNING_MIN_ANGLE,
    CoverType,
)
from custom_components.adaptive_cover_pro.cover_types import POLICY_REGISTRY, get_policy
from custom_components.adaptive_cover_pro.engine.covers import AdaptiveOscillatingCover


def test_registered_and_in_picker():
    assert "cover_oscillating_awning" in POLICY_REGISTRY
    assert CoverType.OSCILLATING_AWNING.value == "cover_oscillating_awning"


def test_geometry_has_new_keys_and_drops_angle():
    policy = get_policy("cover_oscillating_awning")
    geo = {str(m) for m in policy.build_section_schema("geometry").schema}
    assert {CONF_ARM_LENGTH, CONF_AWNING_MIN_ANGLE, CONF_AWNING_MAX_ANGLE} <= geo
    # The fixed-angle field is disabled for this cover type.
    assert CONF_AWNING_ANGLE not in geo


def test_disabled_key_excluded_from_live_keys():
    policy = get_policy("cover_oscillating_awning")
    live = policy.live_option_keys()
    assert CONF_AWNING_ANGLE not in live
    assert CONF_ARM_LENGTH in live


def test_validation_rejects_angle_accepts_arm_length():
    from homeassistant.core import ServiceValidationError

    from custom_components.adaptive_cover_pro.services.options_service import (
        validate_options_patch,
    )

    # arm_length is valid for this cover type.
    validate_options_patch(
        {CONF_ARM_LENGTH: 0.8}, {}, sensor_type="cover_oscillating_awning"
    )
    # The fixed awning angle is rejected (it belongs to the fixed awning type).
    with pytest.raises(ServiceValidationError):
        validate_options_patch(
            {CONF_AWNING_ANGLE: 10}, {}, sensor_type="cover_oscillating_awning"
        )


def _osc_engine(arm: float, lo: float, hi: float) -> AdaptiveOscillatingCover:
    """Build an engine instance without the heavy sun/config plumbing."""
    eng = object.__new__(AdaptiveOscillatingCover)
    eng.osc_config = OscillatingConfig(
        arm_length=arm, min_angle=lo, max_angle=hi, housing_offset=0.0
    )
    return eng


@pytest.mark.parametrize(
    ("reach", "expected_pos"),
    [
        (0.0, 0.0),  # no reach needed → closed
        (0.8, 50.0),  # full arm reach → 90° → halfway through a 0-180 sweep
        (0.8 * math.sin(math.radians(45)), 25.0),  # 45° → quarter sweep
        (5.0, 50.0),  # over-reach clamps to full arm (90°)
    ],
)
def test_engine_reach_to_percentage_arc(reach, expected_pos):
    eng = _osc_engine(arm=0.8, lo=0.0, hi=180.0)
    eng.calculate_position = lambda: reach  # shadow the inherited reach calc
    assert eng.calculate_percentage() == pytest.approx(expected_pos, abs=0.5)


def test_reporter_sweep_is_linear_175_over_100():
    """#412 reporter: 175° total sweep ⇒ 1.75° per 1% (forward mapping)."""
    cfg = OscillatingConfig.from_options({CONF_AWNING_MAX_ANGLE: 175})
    span = cfg.max_angle - cfg.min_angle
    assert span / 100 == pytest.approx(1.75)


def test_config_from_options_defaults():
    cfg = OscillatingConfig.from_options({})
    assert cfg.arm_length == 0.8
    assert cfg.min_angle == 0
    assert cfg.max_angle == 175
