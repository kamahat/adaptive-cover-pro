"""Hub switch entities for Adaptive Cover Pro."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..const import CONF_HUB_ENTITIES, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_hub_switch(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up hub switch entities."""
    tracked: list[str] = entry.options.get(CONF_HUB_ENTITIES, [])
    async_add_entities(
        [
            AdaptiveControlAllSwitch(hass, entry, tracked),
            AdaptiveSecurityAllSwitch(hass, entry, tracked),
        ]
    )


class _HubSwitchBase(SwitchEntity):
    """Base class for hub switches."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        tracked: list[str],
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._tracked = tracked
        self._is_on: bool = True

    @property
    def is_on(self) -> bool:
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._is_on = True
        await self._propagate(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._is_on = False
        await self._propagate(False)
        self.async_write_ha_state()

    async def _propagate(self, state: bool) -> None:
        raise NotImplementedError


class AdaptiveControlAllSwitch(_HubSwitchBase):
    """Switch that enables/disables adaptive control for all tracked covers."""

    _attr_translation_key = "hub_adaptive_control"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, tracked: list[str]) -> None:
        super().__init__(hass, entry, tracked)
        self._attr_unique_id = f"{entry.entry_id}_hub_adaptive_control"

    async def _propagate(self, state: bool) -> None:
        service = "turn_on" if state else "turn_off"
        for entity_id in self._tracked:
            # Derive the switch entity id for adaptive control
            switch_id = entity_id.replace("cover.", "switch.").replace(
                "_cover", "_adaptive_control"
            )
            if self._hass.states.get(switch_id) is not None:
                await self._hass.services.async_call(
                    "switch", service, {"entity_id": switch_id}, blocking=False
                )


class AdaptiveSecurityAllSwitch(_HubSwitchBase):
    """Switch that enables/disables security mode for all tracked covers."""

    _attr_translation_key = "hub_security_mode"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, tracked: list[str]) -> None:
        super().__init__(hass, entry, tracked)
        self._attr_unique_id = f"{entry.entry_id}_hub_security_mode"
        self._is_on = False  # security defaults off

    async def _propagate(self, state: bool) -> None:
        service = "turn_on" if state else "turn_off"
        for entity_id in self._tracked:
            switch_id = entity_id.replace("cover.", "switch.").replace(
                "_cover", "_security_mode"
            )
            if self._hass.states.get(switch_id) is not None:
                await self._hass.services.async_call(
                    "switch", service, {"entity_id": switch_id}, blocking=False
                )
