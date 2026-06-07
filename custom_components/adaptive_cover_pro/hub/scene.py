"""Hub scene entities for Adaptive Cover Pro — Alexa-friendly scenes."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.scene import Scene
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..const import CONF_HUB_ENTITIES, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_hub_scene(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Alexa-friendly hub scenes."""
    tracked: list[str] = entry.options.get(CONF_HUB_ENTITIES, [])
    async_add_entities(
        [
            AdaptiveCoverOpenScene(hass, entry, tracked),
            AdaptiveCoverClosedScene(hass, entry, tracked),
        ]
    )


class _HubSceneBase(Scene):
    """Base class for hub scenes."""

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

    async def async_activate(self, **kwargs: Any) -> None:
        raise NotImplementedError


class AdaptiveCoverOpenScene(_HubSceneBase):
    """Scene: open all blinds (Alexa: 'Volets ouverts')."""

    _attr_translation_key = "hub_scene_open"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, tracked: list[str]) -> None:
        super().__init__(hass, entry, tracked)
        self._attr_unique_id = f"{entry.entry_id}_hub_scene_open"
        self._attr_name = "Volets ouverts"

    async def async_activate(self, **kwargs: Any) -> None:
        for entity_id in self._tracked:
            await self._hass.services.async_call(
                "cover", "open_cover", {"entity_id": entity_id}, blocking=False
            )


class AdaptiveCoverClosedScene(_HubSceneBase):
    """Scene: close all blinds (Alexa: 'Volets fermés')."""

    _attr_translation_key = "hub_scene_closed"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, tracked: list[str]) -> None:
        super().__init__(hass, entry, tracked)
        self._attr_unique_id = f"{entry.entry_id}_hub_scene_closed"
        self._attr_name = "Volets fermés"

    async def async_activate(self, **kwargs: Any) -> None:
        for entity_id in self._tracked:
            await self._hass.services.async_call(
                "cover", "close_cover", {"entity_id": entity_id}, blocking=False
            )
