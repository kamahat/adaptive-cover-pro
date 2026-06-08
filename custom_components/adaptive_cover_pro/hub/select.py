"""Hub control mode select entity for Adaptive Cover Pro."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..const import CONF_HUB_ENTITIES, DOMAIN

_LOGGER = logging.getLogger(__name__)

OPTIONS = ["auto", "off", "all_open", "all_closed"]


async def async_setup_hub_select(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the hub control mode select."""
    tracked: list[str] = entry.options.get(CONF_HUB_ENTITIES, [])
    async_add_entities([AdaptiveControlModeSelect(hass, entry, tracked)])


class AdaptiveControlModeSelect(SelectEntity):
    """Select entity to control all covers' adaptive mode simultaneously."""

    _attr_has_entity_name = True
    _attr_translation_key = "hub_control_mode"
    _attr_options = OPTIONS

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        tracked: list[str],
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._tracked = tracked
        self._attr_unique_id = f"{entry.entry_id}_hub_control_mode"
        self._current_option = "auto"

    @property
    def current_option(self) -> str:
        return self._current_option

    async def async_select_option(self, option: str) -> None:
        self._current_option = option
        await self._apply_mode(option)
        self.async_write_ha_state()

    async def _apply_mode(self, mode: str) -> None:
        if mode == "all_open":
            for entity_id in self._tracked:
                await self._hass.services.async_call(
                    "cover", "open_cover", {"entity_id": entity_id}, blocking=False
                )
        elif mode == "all_closed":
            for entity_id in self._tracked:
                await self._hass.services.async_call(
                    "cover", "close_cover", {"entity_id": entity_id}, blocking=False
                )
        elif mode in ("auto", "off"):
            # Signal each ACP entry to switch mode via input_select or state
            for entity_id in self._tracked:
                state = self._hass.states.get(entity_id)
                if state is None:
                    continue
                # Try to find a paired control_mode select for this cover
                control_select_id = entity_id.replace("cover.", "select.").replace(
                    "_cover", "_control_mode"
                )
                ctrl_state = self._hass.states.get(control_select_id)
                if ctrl_state is not None:
                    await self._hass.services.async_call(
                        "select",
                        "select_option",
                        {"entity_id": control_select_id, "option": mode},
                        blocking=False,
                    )
