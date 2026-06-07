"""Hub aggregate cover entity for Adaptive Cover Pro."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from ..const import CONF_HUB_ENTITIES, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_hub_cover(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the hub aggregate cover."""
    tracked: list[str] = entry.options.get(CONF_HUB_ENTITIES, [])
    async_add_entities([AdaptiveCoverAll(hass, entry, tracked)])


class AdaptiveCoverAll(CoverEntity):
    """Aggregate cover that controls all tracked adaptive cover entities."""

    _attr_has_entity_name = True
    _attr_translation_key = "hub_cover"
    _attr_device_class = CoverDeviceClass.BLIND
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.SET_POSITION
        | CoverEntityFeature.STOP
    )

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        tracked: list[str],
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._tracked = tracked
        self._attr_unique_id = f"{entry.entry_id}_hub_cover"
        self._attr_name = entry.data.get("name", "All Blinds")

    @property
    def is_closed(self) -> bool | None:
        positions = self._get_positions()
        if not positions:
            return None
        return all(p == 0 for p in positions)

    @property
    def current_cover_position(self) -> int | None:
        positions = self._get_positions()
        if not positions:
            return None
        return round(sum(positions) / len(positions))

    def _get_positions(self) -> list[int]:
        result = []
        for entity_id in self._tracked:
            state = self._hass.states.get(entity_id)
            if state and state.attributes.get(ATTR_POSITION) is not None:
                result.append(int(state.attributes[ATTR_POSITION]))
        return result

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._call_service("open_cover")

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._call_service("close_cover")

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._call_service("stop_cover")

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        position = kwargs.get(ATTR_POSITION, 50)
        await self._call_service("set_cover_position", {ATTR_POSITION: position})

    async def _call_service(self, service: str, data: dict | None = None) -> None:
        for entity_id in self._tracked:
            svc_data = {"entity_id": entity_id, **(data or {})}
            await self._hass.services.async_call("cover", service, svc_data, blocking=False)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_track_state_change_event(
                self._hass,
                self._tracked,
                self._handle_state_change,
            )
        )

    @callback
    def _handle_state_change(self, event: Any) -> None:
        self.async_write_ha_state()
