"""Hub entry helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..const import CONF_HUB_ENTITIES, CONF_IS_HUB

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

# Minimal data dict required to create a hub config entry via config_flow.
HUB_ENTRY_DATA = {
    "name": "All Blinds",
    CONF_IS_HUB: True,
}


def is_hub_entry(entry: ConfigEntry) -> bool:
    """Return True when this config entry is a hub aggregator entry."""
    return bool(entry.data.get(CONF_IS_HUB, False))
