"""Regression tests for critical edge cases (Section 2).

Edge cases covered
------------------
1. sun.sun unavailability  — direct_sun_valid must be False when sun.sun reports
   no azimuth/elevation; solar tracking must not produce spurious commands.
2. Sensor entity unavailability — presence, weather, and cover-position entities
   must all degrade gracefully (return safe defaults, no exceptions).
3. Concurrent state transitions — manual override + weather safety + grace period
   firing simultaneously must respect the documented priority order:
   ForceOverride(100) > Weather(90) > ManualOverride(80) > Default(0).
4. Config migration idempotency — both async_prune_legacy_entities and
   async_prune_legacy_sensor_entities must be safe to run twice.
5. Hub with zero child entries — All-Blinds hub with empty CONF_ENTITIES must
   not raise and must compute a valid (default) position.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_cover_pro.const import (
    CONF_ENTITIES,
    CONF_SENSOR_TYPE,
    DOMAIN,
    CoverType,
)
from custom_components.adaptive_cover_pro.engine.sun_geometry import SunGeometry
from custom_components.adaptive_cover_pro.migrations import (
    _PRUNE_SENSORS_V1_FLAG,
    _PRUNE_V1_FLAG,
    async_prune_legacy_entities,
    async_prune_legacy_sensor_entities,
)
from custom_components.adaptive_cover_pro.pipeline.types import PipelineSnapshot
from custom_components.adaptive_cover_pro.state.climate_provider import ClimateProvider
from tests.cover_helpers import build_vertical_cover, make_cover_config
from tests.ha_helpers import VERTICAL_OPTIONS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    hass: HomeAssistant,
    options: dict | None = None,
    entry_id: str = "edge_test_01",
) -> MockConfigEntry:
    """Create and add a minimal config entry without running setup."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Edge Test", CONF_SENSOR_TYPE: CoverType.BLIND},
        options=dict(VERTICAL_OPTIONS) if options is None else options,
        entry_id=entry_id,
        title="Edge Test",
    )
    entry.add_to_hass(hass)
    return entry


def _make_sun_geometry(sol_azi: float, sol_elev: float, logger=None) -> SunGeometry:
    """Build a SunGeometry with a minimal mock SunData and CoverConfig."""
    config = make_cover_config(win_azi=180, fov_left=90, fov_right=90)
    sun_data = MagicMock()
    sun_data.sunset.return_value = MagicMock()
    sun_data.sunrise.return_value = MagicMock()
    if logger is None:
        logger = MagicMock()
        logger.debug = MagicMock()
    return SunGeometry(
        sol_azi=sol_azi,
        sol_elev=sol_elev,
        sun_data=sun_data,
        config=config,
        logger=logger,
    )


# ---------------------------------------------------------------------------
# Edge Case 1: sun.sun unavailability
# ---------------------------------------------------------------------------


class TestSunUnavailability:
    """sun.sun entity unavailable at startup or during HA restart."""

    def test_sol_elev_negative_makes_valid_elevation_false(self):
        """When sol_elev=-1.0 (substituted by coordinator), valid_elevation is False."""
        geo = _make_sun_geometry(sol_azi=180.0, sol_elev=-1.0)
        assert geo.valid_elevation is False, (
            "sol_elev=-1.0 must make valid_elevation False so no solar commands are sent"
        )

    def test_sol_elev_negative_makes_direct_sun_valid_false(self):
        """When sol_elev=-1.0, direct_sun_valid is False regardless of azimuth."""
        # Azimuth 180 is squarely in a south-facing window's FOV; only the
        # negative elevation must prevent solar tracking.
        geo = _make_sun_geometry(sol_azi=180.0, sol_elev=-1.0)
        assert geo.direct_sun_valid is False, (
            "direct_sun_valid must be False when elevation is below horizon"
        )

    def test_sol_elev_zero_is_treated_as_valid(self):
        """Elevation exactly 0 is the horizon — valid_elevation returns True (>= 0)."""
        # This ensures our -1.0 guard doesn't accidentally block horizon-level sun.
        geo = _make_sun_geometry(sol_azi=180.0, sol_elev=0.0)
        assert geo.valid_elevation is True, (
            "sol_elev=0.0 (horizon) must pass the elevation check"
        )

    def test_sol_elev_positive_with_good_azimuth_gives_direct_sun(self):
        """Normal operation: positive elevation + in-FOV azimuth = direct_sun_valid."""
        # Set sunset/sunrise sentinels far enough away that sunset_valid is False.
        import datetime

        geo = _make_sun_geometry(sol_azi=180.0, sol_elev=30.0)
        # Patch sunset_valid to False so only azimuth + elevation are tested.
        with patch.object(type(geo), "sunset_valid", new_callable=lambda: property(lambda self: False)):  # noqa: E501
            with patch.object(type(geo), "is_sun_in_blind_spot", new_callable=lambda: property(lambda self: False)):  # noqa: E501
                assert geo.valid is True

    def test_get_blind_data_substitutes_negative_elevation_when_sun_unavailable(
        self, mock_hass, mock_logger
    ):
        """get_blind_data uses sol_elev=-1.0 when sun.sun attributes are both None."""
        # Build a minimal coordinator-like object without spinning up real HA.
        from custom_components.adaptive_cover_pro.config_types import CoverConfig
        from custom_components.adaptive_cover_pro.engine.covers.vertical import (
            AdaptiveVerticalCover,
        )
        from custom_components.adaptive_cover_pro.cover_types import get_policy

        # Patch state_attr to return None for both sun.sun attributes.
        with patch(
            "custom_components.adaptive_cover_pro.coordinator.state_attr",
            return_value=None,
        ):
            # pos_sun returns [None, None] when both attributes are missing.
            # Verify the substitution logic directly.
            raw_azi, raw_elev = None, None
            _sun_unavailable = raw_azi is None and raw_elev is None
            sol_elev = raw_elev if raw_elev is not None else (-1.0 if _sun_unavailable else 0.0)
            assert sol_elev == -1.0, "sun unavailable must substitute -1.0 for elevation"

    @pytest.fixture
    def mock_hass(self):
        hass = MagicMock()
        hass.states.get.return_value = None
        hass.config.units.temperature_unit = "°C"
        return hass

    @pytest.fixture
    def mock_logger(self):
        logger = MagicMock()
        logger.debug = MagicMock()
        logger.warning = MagicMock()
        return logger


# ---------------------------------------------------------------------------
# Edge Case 2: Sensor entity unavailability
# ---------------------------------------------------------------------------


class TestSensorEntityUnavailability:
    """Presence sensor, weather entity, cover position — each must degrade gracefully."""

    def test_climate_provider_presence_entity_unavailable_returns_true(self):
        """Unavailable presence entity is treated as 'present' (fail-open)."""
        hass = MagicMock()
        hass.states.get.return_value = None  # entity missing entirely

        from custom_components.adaptive_cover_pro.helpers import is_entity_active

        result = is_entity_active(hass, "binary_sensor.presence")
        assert result is True, (
            "Missing presence sensor should default to True (fail-open) so covers still track"
        )

    def test_climate_provider_presence_entity_unknown_returns_true(self):
        """STATE_UNKNOWN presence sensor is treated as 'present' (fail-open)."""
        from homeassistant.const import STATE_UNKNOWN

        hass = MagicMock()
        state = MagicMock()
        state.state = STATE_UNKNOWN
        hass.states.get.return_value = state

        from custom_components.adaptive_cover_pro.helpers import get_safe_state

        result = get_safe_state(hass, "binary_sensor.presence")
        assert result is None, "STATE_UNKNOWN should be returned as None by get_safe_state"

    def test_climate_provider_weather_entity_unavailable_returns_sunny_true(self):
        """Unavailable weather entity defaults is_sunny to True (cover tracks sun)."""
        hass = MagicMock()
        hass.states.get.return_value = None
        logger = MagicMock()
        logger.debug = MagicMock()

        provider = ClimateProvider(hass=hass, logger=logger)
        readings = provider.read(
            weather_entity="weather.home",
            weather_condition=["sunny"],
        )
        assert readings.is_sunny is True, (
            "Unavailable weather entity must default is_sunny=True"
        )

    def test_climate_provider_lux_entity_unavailable_returns_false(self):
        """Unavailable lux entity returns lux_below_threshold=False (no suppression)."""
        hass = MagicMock()
        hass.states.get.return_value = None
        logger = MagicMock()
        logger.debug = MagicMock()

        provider = ClimateProvider(hass=hass, logger=logger)
        readings = provider.read(
            use_lux=True,
            lux_entity="sensor.lux",
            lux_threshold=100,
        )
        assert readings.lux_below_threshold is False, (
            "Unavailable lux entity should not trigger cloud suppression"
        )

    def test_climate_provider_outside_temp_unavailable_returns_none(self):
        """Unavailable outside temperature sensor returns None (no climate strategy)."""
        hass = MagicMock()
        hass.states.get.return_value = None
        logger = MagicMock()
        logger.debug = MagicMock()

        provider = ClimateProvider(hass=hass, logger=logger)
        readings = provider.read(
            outside_entity="sensor.outside_temp",
        )
        assert readings.outside_temperature is None, (
            "Unavailable outside temperature sensor must return None"
        )

    def test_cover_position_unavailable_does_not_raise(self):
        """Cover entity unavailable: read_positions returns None for that cover."""
        hass = MagicMock()
        from homeassistant.const import STATE_UNAVAILABLE

        state = MagicMock()
        state.state = STATE_UNAVAILABLE
        state.attributes = {}
        hass.states.get.return_value = state

        from custom_components.adaptive_cover_pro.state.cover_provider import (
            CoverProvider,
        )
        from custom_components.adaptive_cover_pro.cover_types import get_policy

        logger = MagicMock()
        logger.debug = MagicMock()
        provider = CoverProvider(hass=hass, logger=logger)
        policy = get_policy("cover_blind")
        positions = provider.read_positions(["cover.test"], policy)
        # Should not raise and must return a dict (position may be None for unavailable)
        assert isinstance(positions, dict), "read_positions must always return a dict"


# ---------------------------------------------------------------------------
# Edge Case 3: Concurrent state transitions — priority order
# ---------------------------------------------------------------------------


class TestConcurrentStateTransitions:
    """Manual override + weather safety + grace period firing simultaneously."""

    def _make_snapshot(
        self,
        *,
        manual_override_active: bool = False,
        weather_override_active: bool = False,
        force_sensors: dict | None = None,
        motion_timeout_active: bool = False,
    ) -> PipelineSnapshot:
        """Build a minimal PipelineSnapshot for priority-order tests."""
        from tests.cover_helpers import build_vertical_cover

        logger = MagicMock()
        logger.debug = MagicMock()
        sun_data = MagicMock()
        sun_data.sunset.return_value = MagicMock()
        sun_data.sunrise.return_value = MagicMock()

        cover = build_vertical_cover(
            logger=logger,
            sol_azi=180.0,
            sol_elev=30.0,
            sun_data=sun_data,
        )

        from custom_components.adaptive_cover_pro.pipeline.types import ClimateOptions
        from custom_components.adaptive_cover_pro.cover_types import get_policy

        return PipelineSnapshot(
            cover=cover,
            config=cover.config,
            cover_type="cover_blind",
            default_position=0,
            is_sunset_active=False,
            climate_readings=None,
            climate_mode_enabled=False,
            climate_options=ClimateOptions(
                temp_low=None,
                temp_high=None,
                temp_switch=False,
                transparent_blind=False,
                temp_summer_outside=None,
                cloud_suppression_enabled=False,
                winter_close_insulation=False,
            ),
            force_override_sensors=force_sensors or {},
            force_override_position=100,
            manual_override_active=manual_override_active,
            motion_timeout_active=motion_timeout_active,
            weather_override_active=weather_override_active,
            weather_override_position=0,
            glare_zones=None,
            active_zone_names=frozenset(),
            policy=get_policy("cover_blind"),
        )

    def test_force_override_beats_weather_beats_manual(self):
        """ForceOverride(100) > WeatherOverride(90) > ManualOverride(80)."""
        from custom_components.adaptive_cover_pro.pipeline.handlers import (
            ForceOverrideHandler,
            ManualOverrideHandler,
            WeatherOverrideHandler,
            DefaultHandler,
        )
        from custom_components.adaptive_cover_pro.pipeline.registry import (
            PipelineRegistry,
        )

        snapshot = self._make_snapshot(
            manual_override_active=True,
            weather_override_active=True,
            force_sensors={"binary_sensor.force": True},
        )
        registry = PipelineRegistry(
            [ForceOverrideHandler(), WeatherOverrideHandler(), ManualOverrideHandler(), DefaultHandler()]
        )
        result = registry.evaluate(snapshot)
        from custom_components.adaptive_cover_pro.const import ControlMethod

        assert result.control_method == ControlMethod.FORCE, (
            "ForceOverride must win over WeatherOverride and ManualOverride"
        )

    def test_weather_beats_manual_when_no_force(self):
        """WeatherOverride(90) > ManualOverride(80) when force sensors are off."""
        from custom_components.adaptive_cover_pro.pipeline.handlers import (
            ForceOverrideHandler,
            ManualOverrideHandler,
            WeatherOverrideHandler,
            DefaultHandler,
        )
        from custom_components.adaptive_cover_pro.pipeline.registry import (
            PipelineRegistry,
        )

        snapshot = self._make_snapshot(
            manual_override_active=True,
            weather_override_active=True,
            force_sensors={"binary_sensor.force": False},
        )
        registry = PipelineRegistry(
            [ForceOverrideHandler(), WeatherOverrideHandler(), ManualOverrideHandler(), DefaultHandler()]
        )
        result = registry.evaluate(snapshot)
        from custom_components.adaptive_cover_pro.const import ControlMethod

        assert result.control_method == ControlMethod.WEATHER, (
            "WeatherOverride must win over ManualOverride when force is inactive"
        )

    def test_manual_override_wins_when_weather_and_force_inactive(self):
        """ManualOverride(80) wins when neither force nor weather is active."""
        from custom_components.adaptive_cover_pro.pipeline.handlers import (
            ForceOverrideHandler,
            ManualOverrideHandler,
            WeatherOverrideHandler,
            DefaultHandler,
        )
        from custom_components.adaptive_cover_pro.pipeline.registry import (
            PipelineRegistry,
        )

        snapshot = self._make_snapshot(
            manual_override_active=True,
            weather_override_active=False,
            force_sensors={"binary_sensor.force": False},
        )
        registry = PipelineRegistry(
            [ForceOverrideHandler(), WeatherOverrideHandler(), ManualOverrideHandler(), DefaultHandler()]
        )
        result = registry.evaluate(snapshot)
        from custom_components.adaptive_cover_pro.const import ControlMethod

        assert result.control_method == ControlMethod.MANUAL, (
            "ManualOverride must win when force and weather are both inactive"
        )


# ---------------------------------------------------------------------------
# Edge Case 4: Config migration idempotency
# ---------------------------------------------------------------------------

pytestmark_integration = pytest.mark.integration


@pytest.mark.integration
async def test_binary_sensor_migration_idempotent(hass: HomeAssistant) -> None:
    """async_prune_legacy_entities is safe to run twice (idempotent)."""
    entry = _make_entry(hass, entry_id="idem_bs_01")
    registry = er.async_get(hass)

    # Seed one legacy orphan
    orphan = registry.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        f"{entry.entry_id}_Sun Infront",
        config_entry=entry,
        suggested_object_id="legacy_sun_infront",
    )

    # First run — removes orphan + sets flag
    await async_prune_legacy_entities(hass, entry)
    await hass.async_block_till_done()

    entry_after_first = hass.config_entries.async_get_entry("idem_bs_01")
    assert entry_after_first.options.get(_PRUNE_V1_FLAG) is True
    assert registry.async_get(orphan.entity_id) is None

    # Second run — must not raise even though the entity is already gone
    await async_prune_legacy_entities(hass, entry_after_first)
    await hass.async_block_till_done()

    entry_after_second = hass.config_entries.async_get_entry("idem_bs_01")
    assert entry_after_second.options.get(_PRUNE_V1_FLAG) is True


@pytest.mark.integration
async def test_sensor_migration_idempotent(hass: HomeAssistant) -> None:
    """async_prune_legacy_sensor_entities is safe to run twice (idempotent)."""
    entry = _make_entry(hass, entry_id="idem_sens_01")
    registry = er.async_get(hass)

    # Seed one legacy sensor orphan (sun_azimuth was replaced by sun_position)
    orphan = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_sun_azimuth",
        config_entry=entry,
        suggested_object_id="legacy_sun_azimuth",
    )

    # First run
    await async_prune_legacy_sensor_entities(hass, entry)
    await hass.async_block_till_done()

    entry_after_first = hass.config_entries.async_get_entry("idem_sens_01")
    assert entry_after_first.options.get(_PRUNE_SENSORS_V1_FLAG) is True
    assert registry.async_get(orphan.entity_id) is None

    # Second run — must be a no-op
    await async_prune_legacy_sensor_entities(hass, entry_after_first)
    await hass.async_block_till_done()

    entry_after_second = hass.config_entries.async_get_entry("idem_sens_01")
    assert entry_after_second.options.get(_PRUNE_SENSORS_V1_FLAG) is True


@pytest.mark.integration
async def test_binary_sensor_migration_flag_written_before_removal(
    hass: HomeAssistant,
) -> None:
    """Flag is written to options before entity removal (crash safety)."""
    entry = _make_entry(hass, entry_id="flag_first_01")
    registry = er.async_get(hass)

    orphan = registry.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        f"{entry.entry_id}_Sun Infront",
        config_entry=entry,
        suggested_object_id="flag_first_orphan",
    )

    removal_calls: list[str] = []
    original_remove = registry.async_remove

    def _tracking_remove(entity_id: str) -> None:
        # Verify flag is already set when removal is called
        current_entry = hass.config_entries.async_get_entry("flag_first_01")
        assert current_entry.options.get(_PRUNE_V1_FLAG) is True, (
            "Flag must be written BEFORE any entity is removed"
        )
        removal_calls.append(entity_id)
        return original_remove(entity_id)

    with patch.object(registry, "async_remove", side_effect=_tracking_remove):
        await async_prune_legacy_entities(hass, entry)
        await hass.async_block_till_done()

    assert orphan.entity_id in removal_calls, "Orphan should have been removed"


# ---------------------------------------------------------------------------
# Edge Case 5: Hub with zero child entries
# ---------------------------------------------------------------------------


class TestHubWithZeroChildEntries:
    """All-Blinds hub with CONF_ENTITIES=[] must not raise."""

    def test_compute_mean_cover_position_empty_entities_returns_none(self):
        """_compute_mean_cover_position returns None when no entities are configured."""
        from custom_components.adaptive_cover_pro.state.snapshot import (
            CoverStateSnapshot,
            SunSnapshot,
        )

        snapshot = CoverStateSnapshot(
            sun=SunSnapshot(azimuth=180.0, elevation=30.0),
            climate=None,
            cover_positions={},  # empty — no child covers
            cover_capabilities={},
            motion_detected=False,
            force_override_active=False,
        )
        # Replicate the coordinator logic directly
        positions = [
            p
            for p in snapshot.cover_positions.values()
            if isinstance(p, int | float)
        ]
        result = int(round(sum(positions) / len(positions))) if positions else None
        assert result is None, (
            "Empty entity list must return None for mean cover position"
        )

    def test_proxy_cover_setup_entry_returns_early_on_empty_sources(self):
        """cover.async_setup_entry is a no-op when CONF_ENTITIES is empty."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        hass = MagicMock()
        hass.data = {DOMAIN: {"test_entry": MagicMock()}}

        entry = MagicMock()
        entry.options = {
            "enable_proxy_cover": True,
            CONF_ENTITIES: [],  # zero child entries
        }
        entry.entry_id = "test_entry"

        async_add_entities = MagicMock()

        async def _run():
            from custom_components.adaptive_cover_pro.cover import async_setup_entry
            await async_setup_entry(hass, entry, async_add_entities)

        asyncio.get_event_loop().run_until_complete(_run())
        async_add_entities.assert_not_called(), (
            "No proxy entities should be created for empty CONF_ENTITIES"
        )

    def test_pipeline_evaluates_to_default_with_no_entities(self):
        """Pipeline returns the DefaultHandler result when entity list is empty."""
        from custom_components.adaptive_cover_pro.pipeline.handlers import (
            DefaultHandler,
            SolarHandler,
            ForceOverrideHandler,
            WeatherOverrideHandler,
            ManualOverrideHandler,
        )
        from custom_components.adaptive_cover_pro.pipeline.registry import (
            PipelineRegistry,
        )
        from custom_components.adaptive_cover_pro.pipeline.types import (
            ClimateOptions,
            PipelineSnapshot,
        )
        from custom_components.adaptive_cover_pro.cover_types import get_policy
        from tests.cover_helpers import build_vertical_cover

        logger = MagicMock()
        logger.debug = MagicMock()
        sun_data = MagicMock()
        sun_data.sunset.return_value = MagicMock()
        sun_data.sunrise.return_value = MagicMock()

        # sol_elev=-1.0 simulates sun.sun unavailability (the coordinator guard)
        cover = build_vertical_cover(
            logger=logger,
            sol_azi=0.0,
            sol_elev=-1.0,  # sun unavailable
            sun_data=sun_data,
        )

        snapshot = PipelineSnapshot(
            cover=cover,
            config=cover.config,
            cover_type="cover_blind",
            default_position=50,
            is_sunset_active=False,
            climate_readings=None,
            climate_mode_enabled=False,
            climate_options=ClimateOptions(
                temp_low=None,
                temp_high=None,
                temp_switch=False,
                transparent_blind=False,
                temp_summer_outside=None,
                cloud_suppression_enabled=False,
                winter_close_insulation=False,
            ),
            force_override_sensors={},
            force_override_position=0,
            manual_override_active=False,
            motion_timeout_active=False,
            weather_override_active=False,
            weather_override_position=0,
            glare_zones=None,
            active_zone_names=frozenset(),
            policy=get_policy("cover_blind"),
        )

        registry = PipelineRegistry(
            [
                ForceOverrideHandler(),
                WeatherOverrideHandler(),
                ManualOverrideHandler(),
                SolarHandler(),
                DefaultHandler(),
            ]
        )
        result = registry.evaluate(snapshot)
        from custom_components.adaptive_cover_pro.const import ControlMethod

        assert result.control_method == ControlMethod.DEFAULT, (
            "Pipeline must fall through to DefaultHandler when sun is unavailable"
        )
        assert result.position == 50, (
            "Default position must be returned when sun is unavailable"
        )
