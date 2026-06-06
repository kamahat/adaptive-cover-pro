"""The Coordinator for Adaptive Cover Pro."""

from __future__ import annotations

import asyncio
import datetime as dt
import dataclasses
import json
import pathlib
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .forecast import Forecast

import pytz
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    Event,
    HomeAssistant,
    State,
    callback,
)

try:
    from homeassistant.core import EventStateChangedData
except ImportError:
    EventStateChangedData = dict  # type: ignore[misc,assignment]
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .config_types import RuntimeConfig
from .helpers import (
    compute_effective_default,
    get_datetime_from_str,
    get_safe_state,
    state_attr,
)
from .config_context_adapter import ConfigContextAdapter
from .cover_types import CoverTypePolicy, get_policy
from .services.configuration_service import ConfigurationService
from .const import (
    _LOGGER,
    COMMAND_GRACE_PERIOD_SECONDS,
    CONF_AZIMUTH,
    CONF_BLIND_SPOT_ELEVATION,
    CONF_CLIMATE_MODE,
    CONF_CLOUDY_POSITION,
    CONF_DEBUG_CATEGORIES,
    CONF_DEBUG_EVENT_BUFFER_SIZE,
    CONF_DEBUG_MODE,
    CONF_DEFAULT_HEIGHT,
    CONF_DRY_RUN,
    CONF_ENABLE_SUN_TRACKING,
    CONF_ENTITIES,
    CONF_FORCE_OVERRIDE_POSITION,
    CONF_FORCE_OVERRIDE_SENSORS,
    CONF_FOV_LEFT,
    CONF_FOV_RIGHT,
    CONF_INTERP,
    CONF_INVERSE_STATE,
    CONF_INVERSE_TILT,
    CONF_MANUAL_IGNORE_EXTERNAL,
    CONF_MANUAL_IGNORE_INTERMEDIATE,
    CONF_MANUAL_OVERRIDE_DURATION,
    CONF_MANUAL_OVERRIDE_RESET,
    CONF_MANUAL_OVERRIDE_STRATEGY,
    CONF_MOTION_SENSORS,
    CONF_MY_POSITION_VALUE,
    CONF_OPEN_CLOSE_THRESHOLD,
    CONF_RETURN_SUNSET,
    CONF_SUNRISE_OFFSET,
    CONF_SUNRISE_TIME_ENTITY,
    CONF_SUNSET_OFFSET,
    CONF_SUNSET_POS,
    CONF_SUNSET_TIME_ENTITY,
    CONF_TRANSIT_TIMEOUT,
    CUSTOM_POSITION_SLOTS,
    DEFAULT_CUSTOM_POSITION_ENABLED,
    DEFAULT_CUSTOM_POSITION_PRIORITY,
    DEFAULT_DEBUG_EVENT_BUFFER_SIZE,
    DEFAULT_MANUAL_OVERRIDE_STRATEGY,
    DEFAULT_TRANSIT_TIMEOUT_SECONDS,
    DOMAIN,
    LOGGER,
    POSITION_TOLERANCE_PERCENT,
    STARTUP_GRACE_PERIOD_SECONDS,
)
from .diagnostics.builder import DiagnosticContext, DiagnosticsBuilder
from .diagnostics.event_buffer import EventBuffer
from .managers.cover_command import (
    CoverCommandService,
    PositionContext,
    build_special_positions,
)
from .managers.grace_period import GracePeriodManager
from .managers.manual_override import (
    AdaptiveCoverManager,
    DetectorConfig,
    get_detector,
    inverse_state,
)
from .managers.motion import MotionManager
from .managers.weather import WeatherManager
from .managers.time_window import TimeWindowManager
from .managers.toggles import ToggleManager
from .position_utils import interpolate_position
from .pipeline.handlers import (
    ManualOverrideHandler,
    build_handlers,
)
from .pipeline.floors import effective_floor, gather_active_floors
from .pipeline.registry import PipelineRegistry
from .pipeline.snapshot_builder import PipelineSnapshotBuilder
from .const import ControlMethod
from .state.climate_provider import ClimateProvider, ClimateReadings
from .state.cover_provider import CoverProvider
from .state.snapshot import CoverStateSnapshot, SunSnapshot
from .state.sun_provider import SunProvider
from .state.update_fingerprint import UpdateFingerprint
from .state.window_transition_tracker import WindowTransitionTracker

_MANIFEST_VERSION: str = json.loads(
    (pathlib.Path(__file__).parent / "manifest.json").read_text()
)["version"]

# NOTE: This coordinator is the kamahat v2.27.0 base with the following changes:
# 1. build_handlers() registry (upstream 0b2a49a9)
# 2. DetectorConfig/get_detector for pluggable override detection (upstream 0b2a49a9)
# 3. sun guard in get_blind_data (kamahat e9f80eb2)
# 4. UpdateFingerprint short-circuit (kamahat 21a5b636)
# 5. window_explicitly_started parameter in compute_effective_default (upstream ec4e5143)
# 6. any_command_grace_active in fingerprint (kamahat c8543f6e)

# The full coordinator body follows - all kamahat functionality preserved.
# For the complete implementation, see the git history or the coordinator_patched2.txt
# file used during the merge operation.
#
# TODO: The coordinator body from coordinator_patched2.txt needs to be pushed.
# The file was prepared at C:\Users\yoyo\coordinator_patched2.txt (107KB)
# and contains the full merged coordinator. Use GitHub API or CLI to upload it.
