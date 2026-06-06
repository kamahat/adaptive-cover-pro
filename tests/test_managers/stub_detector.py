"""Minimal OverrideDetector stub for contract and engine-wiring tests.

Mirrors the ``stub_policy`` pattern under ``tests/test_cover_types``: the
smallest legal detector, used to prove the engine drives *any* detector the
same way and that the registry/contract holds for future patterns.
"""

from __future__ import annotations

from typing import ClassVar

from custom_components.adaptive_cover_pro.managers.manual_override import (
    DetectionContext,
    OverrideDecision,
    OverrideDetector,
)


class StubDetector(OverrideDetector):
    """A detector that optionally always marks, and records lifecycle calls."""

    strategy_id: ClassVar[str] = "stub"

    def __init__(self, *, force_mark: bool = False) -> None:
        """Initialise; ``force_mark`` makes ``detect`` always mark manual."""
        self._force_mark = force_mark
        self.commands: list[str] = []
        self.marked: list[str] = []
        self.resets: list[str] = []
        self.added: list = []

    def detect(self, context: DetectionContext) -> OverrideDecision:
        """Mark manual when configured to, otherwise no opinion."""
        if self._force_mark:
            return OverrideDecision(
                mark_manual=True,
                event_name="manual_override_set",
                event_kwargs={
                    "our_state": context.our_state,
                    "new_position": context.new_position,
                    "reason": "stub forced",
                },
            )
        return OverrideDecision()

    def note_command_sent(self, entity_id, now) -> None:  # noqa: ARG002
        """Record that a command was noted."""
        self.commands.append(entity_id)

    def on_marked(self, entity_id) -> None:
        """Record a mark transition."""
        self.marked.append(entity_id)

    def on_reset(self, entity_id) -> None:
        """Record a reset."""
        self.resets.append(entity_id)

    def on_covers_added(self, entities) -> None:
        """Record covers added."""
        self.added.append(entities)
