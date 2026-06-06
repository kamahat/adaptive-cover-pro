"""Manual-override engine for Adaptive Cover Pro.

``AdaptiveCoverManager`` is the stateful host: it owns per-entity override
state, the diagnostic ring buffer, the Issue-#33 suppression bookkeeping, and
the command-timing clock. It delegates the *decision* — is this state change a
manual override? — to a pluggable :class:`.detector.OverrideDetector` and
applies the returned :class:`.detector.OverrideDecision`. Edge transitions
(into/out of manual override) fire callbacks so command-side effects
(``discard_target``) wire once and every current and future detector inherits
them.
"""

from __future__ import annotations

import collections
import datetime as dt
import logging
from collections.abc import Callable

from homeassistant.core import HomeAssistant

from ...const import (
    CONF_VENETIAN_BACKROTATE_PUBLISH_LAG,
    DEFAULT_DEBUG_EVENT_BUFFER_SIZE,
)
from ...diagnostics.event_buffer import EventBuffer
from ...helpers import check_cover_features
from ..common import EventRecorder
from .detector import (
    DetectionContext,
    DetectorConfig,
    OverrideDecision,
    OverrideDetector,
    StopToMy,
    UserContextChange,
)
from .position_delta import PositionDeltaDetector
from .secondary_axis import SecondaryAxisCheck

_LOGGER = logging.getLogger(__name__)

# Issue #33 Phase 5: per-entity counters of primary-axis publish-lag
# suppressions are pruned to events newer than this. 24 h matches what the
# diagnostic file surfaces under ``primary_axis_suppression_last_24h``.
_PRIMARY_AXIS_SUPPRESSION_WINDOW = dt.timedelta(hours=24)
# WARN throttle: per-entity, fire on the first suppression then at most once
# per hour to keep the log readable for users with chronically slow actuators.
_PRIMARY_AXIS_SUPPRESSION_WARN_THROTTLE = dt.timedelta(hours=1)


def _never(_entity_id: str) -> bool:
    """Default predicate: always False (gate disabled)."""
    return False


class AdaptiveCoverManager:
    """Track position changes and manage manual override detection.

    Monitors cover position changes to detect user-initiated manual overrides.
    Maintains per-cover manual control state with configurable duration and
    reset behavior. The detection decision is delegated to a pluggable
    :class:`.detector.OverrideDetector` (default
    :class:`.position_delta.PositionDeltaDetector`); this class owns all state
    and side effects.

    """

    def __init__(
        self,
        hass: HomeAssistant,
        reset_duration: dict[str, int],
        logger,
        *,
        event_buffer: EventBuffer | None = None,
        detector: OverrideDetector | None = None,
        on_engaged: Callable[[str], None] | None = None,
        on_cleared: Callable[[list[str]], None] | None = None,
    ) -> None:
        """Initialize the AdaptiveCoverManager.

        Args:
            hass: Home Assistant instance
            reset_duration: Duration dict (e.g., {"minutes": 15}) for auto-reset
            logger: Logger instance for debug output
            event_buffer: Shared ring buffer owned by the coordinator. When None
                a private buffer is created (useful for unit tests).
            detector: Active detection strategy. Defaults to
                ``PositionDeltaDetector`` (the historical behaviour).
            on_engaged: Callback fired with the entity_id whenever a cover
                transitions into manual override via a detection channel.
            on_cleared: Callback fired with a list of entity_ids whenever
                manual override is cleared (reset or auto-expiry).

        """
        self.hass = hass
        self.covers: set[str] = set()

        self.manual_control: dict[str, bool] = {}
        self.manual_control_time: dict[str, dt.datetime] = {}
        self.reset_duration = dt.timedelta(**reset_duration)
        self.logger = logger
        self._event_buffer: EventBuffer = (
            event_buffer
            if event_buffer is not None
            else EventBuffer(maxlen=DEFAULT_DEBUG_EVENT_BUFFER_SIZE)
        )
        self._events = EventRecorder(self._event_buffer)
        # Issue #33 Phase 5: rolling per-entity log of primary-axis publish-lag
        # suppressions and a per-entity WARN throttle. Both live on the
        # manager (per-instance state, side-effect bookkeeping); the
        # predicate that decides whether to fire lives on the cover-type
        # policy (cover-type-specific behaviour). Per CODING_GUIDELINES.md §
        # "Managers Hold State, Policies Hold Behavior".
        self._primary_axis_suppression_counts: dict[
            str, collections.deque[dt.datetime]
        ] = {}
        self._last_suppression_warn_at: dict[str, dt.datetime] = {}

        self._detector: OverrideDetector = (
            detector if detector is not None else PositionDeltaDetector()
        )
        self._on_engaged = on_engaged
        self._on_cleared = on_cleared
        # Last ACP command time per entity (float UTC timestamp), feeding the
        # ``seconds_since_command`` context field for time-based detectors.
        self._last_command_at: dict[str, float] = {}
        # ACP-origin predicate over a context id; the coordinator wires the
        # real one. Default treats nothing as ACP-originated.
        self._is_acp_context_fn: Callable[[str | None], bool] = lambda _cid: False

    # --- wiring -----------------------------------------------------------

    def set_transition_callbacks(
        self,
        *,
        on_engaged: Callable[[str], None] | None = None,
        on_cleared: Callable[[list[str]], None] | None = None,
    ) -> None:
        """Register edge-transition callbacks after construction."""
        self._on_engaged = on_engaged
        self._on_cleared = on_cleared

    def set_acp_context_predicate(self, fn: Callable[[str | None], bool]) -> None:
        """Register the predicate that recognises ACP-originated context ids."""
        self._is_acp_context_fn = fn

    def update_config(self, config: DetectorConfig) -> None:
        """Apply an options change at runtime (no reload).

        Refreshes the auto-reset duration and forwards the config to the active
        detector. This is what lets the manual-override duration take effect
        without a config-entry reload.
        """
        self.reset_duration = dt.timedelta(**config.duration)
        self._detector.update_config(config)

    @property
    def detector(self) -> OverrideDetector:
        """Return the active detection strategy."""
        return self._detector

    # --- diagnostics bookkeeping -----------------------------------------

    def _record_primary_axis_suppression(self, entity_id: str, *, delta: float) -> None:
        """Log a primary-axis publish-lag suppression and throttle the WARN."""
        now = dt.datetime.now(dt.UTC)
        deque = self._primary_axis_suppression_counts.setdefault(
            entity_id, collections.deque()
        )
        deque.append(now)
        cutoff = now - _PRIMARY_AXIS_SUPPRESSION_WINDOW
        while deque and deque[0] < cutoff:
            deque.popleft()

        last_warn = self._last_suppression_warn_at.get(entity_id)
        if (
            last_warn is None
            or (now - last_warn) >= _PRIMARY_AXIS_SUPPRESSION_WARN_THROTTLE
        ):
            _LOGGER.warning(
                "Primary-axis manual override suppressed for %s "
                "(publish-lag, delta=%.1f%%, count_last_24h=%d). "
                "If this fires repeatedly for the same actuator, "
                "increase '%s' in options.",
                entity_id,
                delta,
                len(deque),
                CONF_VENETIAN_BACKROTATE_PUBLISH_LAG,
            )
            self._last_suppression_warn_at[entity_id] = now

    def primary_axis_suppression_counts(self) -> dict[str, int]:
        """Return per-entity counts of primary-axis suppressions in the last 24 h."""
        return {
            eid: len(deque)
            for eid, deque in self._primary_axis_suppression_counts.items()
            if deque
        }

    def _record_event(
        self,
        entity_id: str,
        event_name: str,
        *,
        our_state,
        new_position,
        effective_threshold=None,
        reason: str = "",
    ) -> None:
        """Append a manual-override decision event to the shared ring buffer."""
        self._events.record(
            event_name,
            entity_id=entity_id,
            our_state=our_state,
            new_position=new_position,
            effective_threshold=effective_threshold,
            reason=reason,
        )

    def get_event_buffer(self) -> list[dict]:
        """Return a snapshot of the ring buffer (backward-compat wrapper)."""
        return self._event_buffer.snapshot()

    def resize_event_buffer(self, size: int) -> None:
        """Resize the ring buffer, preserving the most-recent events (backward-compat wrapper)."""
        self._event_buffer.resize(size)

    def add_covers(self, entity):
        """Add covers to tracking."""
        self.covers.update(entity)
        self._detector.on_covers_added(entity)

    # --- command-timing clock --------------------------------------------

    def note_command_sent(self, entity_id: str) -> None:
        """Record that ACP just issued a command to ``entity_id``."""
        now = dt.datetime.now(dt.UTC)
        self._last_command_at[entity_id] = now.timestamp()
        self._detector.note_command_sent(entity_id, now)

    def _seconds_since_command(self, entity_id: str, now: dt.datetime) -> float | None:
        """Seconds since the last ACP command for ``entity_id`` (None if never)."""
        ts = self._last_command_at.get(entity_id)
        return (now.timestamp() - ts) if ts is not None else None

    # --- decision application --------------------------------------------

    def _apply_decision(
        self,
        entity_id: str,
        decision: OverrideDecision,
        *,
        set_timestamp: Callable[[], None],
    ) -> None:
        """Apply a detector decision: record events, suppression, mark, fire edge."""
        if decision.event_name is not None:
            self._record_event(
                entity_id, decision.event_name, **(decision.event_kwargs or {})
            )
        if decision.record_primary_axis_suppression:
            self._record_primary_axis_suppression(
                entity_id, delta=decision.suppression_delta
            )
        if decision.mark_manual:
            was_manual = self.is_cover_manual(entity_id)
            self.mark_manual_control(entity_id)
            set_timestamp()
            if not was_manual:
                self._detector.on_marked(entity_id)
                if self._on_engaged is not None:
                    self._on_engaged(entity_id)

    def handle_state_change(
        self,
        states_data,
        our_state,
        policy,
        allow_reset,
        is_waiting,
        manual_threshold,
        *,
        secondary_axis_check: SecondaryAxisCheck | None = None,
        is_in_command_grace: Callable[[str], bool] | None = None,
        is_in_transit: Callable[[str], bool] | None = None,
    ):
        """Process state change for manual override."""
        event = states_data
        if event is None:
            return
        entity_id = event.entity_id
        if entity_id not in self.covers:
            return
        if is_waiting(entity_id):
            self._record_event(
                entity_id,
                "manual_override_rejected_wait_for_target",
                our_state=our_state,
                new_position=None,
                reason="wait_for_target active",
            )
            return
        if is_in_command_grace is not None and is_in_command_grace(entity_id):
            self._record_event(
                entity_id,
                "manual_override_rejected_command_grace",
                our_state=our_state,
                new_position=None,
                reason="command grace period active",
            )
            return

        new_state = event.new_state

        if secondary_axis_check is not None:
            res = secondary_axis_check.evaluate(entity_id, new_state, manual_threshold)
            if res.is_manual:
                self.logger.debug(
                    "Manual %s change for %s: ours=%s, new=%s",
                    secondary_axis_check.label,
                    entity_id,
                    secondary_axis_check.expected,
                    new_state.attributes.get(secondary_axis_check.attribute),
                )
            self._apply_decision(
                entity_id,
                OverrideDecision(
                    mark_manual=res.is_manual,
                    event_name=res.event_name,
                    event_kwargs=res.event_kwargs,
                ),
                set_timestamp=lambda: self.set_last_updated(
                    entity_id, new_state, allow_reset
                ),
            )
            if res.consumed:
                return

        caps = check_cover_features(self.hass, entity_id)
        new_position = policy.read_axis_value(
            self.hass, entity_id, caps, state_obj=new_state
        )

        now = dt.datetime.now(dt.UTC)
        ctx_obj = getattr(new_state, "context", None)
        context_user_id = getattr(ctx_obj, "user_id", None) if ctx_obj else None
        context_id = getattr(ctx_obj, "id", None) if ctx_obj else None
        context = DetectionContext(
            entity_id=entity_id,
            our_state=our_state,
            new_state=new_state,
            old_state=getattr(event, "old_state", None),
            new_position=new_position,
            caps=caps,
            policy=policy,
            manual_threshold=manual_threshold,
            allow_reset=allow_reset,
            is_acp_context=self._is_acp_context_fn(context_id),
            context_user_id=context_user_id,
            context_id=context_id,
            seconds_since_command=self._seconds_since_command(entity_id, now),
            secondary_axis_check=secondary_axis_check,
            is_waiting=is_waiting,
            is_in_command_grace=is_in_command_grace or _never,
            is_in_transit=is_in_transit or _never,
            now=now,
        )
        decision = self._detector.detect(context)
        resolved_allow_reset = (
            decision.allow_reset if decision.allow_reset is not None else allow_reset
        )
        self._apply_decision(
            entity_id,
            decision,
            set_timestamp=lambda: self.set_last_updated(
                entity_id, new_state, resolved_allow_reset
            ),
        )

    def handle_user_initiated_state_change(
        self,
        entity_id: str,
        new_state,
        allow_reset: bool,
        *,
        context_user_id: str | None,
        context_id: str | None,
    ) -> bool:
        """Mark manual override for a state change confirmed user-initiated by HA context."""
        if entity_id not in self.covers:
            return False
        decision = self._detector.on_user_context_change(
            UserContextChange(
                entity_id=entity_id,
                new_state=new_state,
                allow_reset=allow_reset,
                context_user_id=context_user_id,
                context_id=context_id,
            )
        )
        if decision is None:
            return False
        self.logger.debug(
            "Manual override via user-initiated state change for %s "
            "(context user_id=%s, id=%s)",
            entity_id,
            context_user_id,
            context_id,
        )
        resolved_allow_reset = (
            decision.allow_reset if decision.allow_reset is not None else allow_reset
        )
        self._apply_decision(
            entity_id,
            decision,
            set_timestamp=lambda: self.set_last_updated(
                entity_id, new_state, resolved_allow_reset
            ),
        )
        return True

    def handle_stop_service_call(
        self,
        entity_id: str,
        my_position_value: int,
        is_waiting,
    ) -> None:
        """Mark manual override when a user-initiated cover.stop_cover is detected."""
        if entity_id not in self.covers:
            return
        decision = self._detector.on_stop_to_my(
            StopToMy(
                entity_id=entity_id,
                my_position_value=my_position_value,
                is_waiting=is_waiting,
            )
        )
        if decision is None:
            self.logger.debug(
                "handle_stop_service_call: ignoring stop for %s — wait_for_target active",
                entity_id,
            )
            return
        self.logger.debug(
            "Manual override via user stop_cover for %s (My position = %d%%)",
            entity_id,
            my_position_value,
        )
        self._apply_decision(
            entity_id,
            decision,
            set_timestamp=lambda: self.manual_control_time.setdefault(
                entity_id, dt.datetime.now(dt.UTC)
            ),
        )

    def set_last_updated(self, entity_id, new_state, allow_reset):
        """Set last updated time for manual control."""
        if entity_id not in self.manual_control_time or allow_reset:
            last_updated = new_state.last_updated
            self.manual_control_time[entity_id] = last_updated
            self.logger.debug(
                "Updating last updated for manual control to %s for %s. Allow reset:%s",
                last_updated,
                entity_id,
                allow_reset,
            )
        elif not allow_reset:
            self.logger.debug(
                "Already manual control time specified for %s, reset is not allowed by user setting:%s",
                entity_id,
                allow_reset,
            )

    def mark_manual_control(self, cover: str) -> None:
        """Mark cover as manual."""
        self.manual_control[cover] = True

    def mark_user_command(self, entity_id: str, *, reason: str) -> None:
        """Engage manual override pre-emptively from an ACP-owned surface."""
        self.manual_control[entity_id] = True
        self.manual_control_time.setdefault(entity_id, dt.datetime.now(dt.UTC))
        self._record_event(
            entity_id,
            "manual_override_set",
            our_state=None,
            new_position=None,
            reason=reason,
        )

    async def reset_if_needed(self) -> set[str]:
        """Reset expired manual overrides."""
        expired: set[str] = set()
        current_time = dt.datetime.now(dt.UTC)
        manual_control_time_copy = dict(self.manual_control_time)
        for entity_id, last_updated in manual_control_time_copy.items():
            if current_time - last_updated > self.reset_duration:
                self.logger.debug(
                    "Resetting manual override for %s, because duration has elapsed",
                    entity_id,
                )
                self.reset(entity_id)
                expired.add(entity_id)
        return expired

    def reset(self, entity_id):
        """Reset manual control."""
        self.manual_control[entity_id] = False
        self.manual_control_time.pop(entity_id, None)
        self.logger.debug("Reset manual override for %s", entity_id)
        self._record_event(
            entity_id,
            "manual_override_reset",
            our_state=None,
            new_position=None,
            reason="manual override cleared",
        )
        self._detector.on_reset(entity_id)
        if self._on_cleared is not None:
            self._on_cleared([entity_id])

    def is_cover_manual(self, entity_id):
        """Check if cover is manual."""
        return self.manual_control.get(entity_id, False)

    @property
    def binary_cover_manual(self):
        """Check if any cover is manual."""
        return any(value for value in self.manual_control.values())

    @property
    def manual_controlled(self):
        """Get list of manual covers."""
        return [k for k, v in self.manual_control.items() if v]


def inverse_state(state: int) -> int:
    """Inverse state."""
    return 100 - state
