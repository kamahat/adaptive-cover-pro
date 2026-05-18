"""Proxy cover mirroring tests (Phase D Step 14)."""

from __future__ import annotations

import pytest

from custom_components.adaptive_cover_pro.const import (
    CONF_ENABLE_PROXY_COVER,
    CONF_ENTITIES,
    CONF_INVERSE_STATE,
    CONF_SENSOR_TYPE,
    DOMAIN,
    SensorType,
)
from tests.ha_helpers import VERTICAL_OPTIONS, _patch_coordinator_refresh


pytestmark = pytest.mark.integration


async def _setup_single(
    hass,
    *,
    source: str = "cover.living_room",
    entry_id: str = "proxy_mirror_01",
    state: str = "open",
    attrs: dict | None = None,
    extra_options: dict | None = None,
):
    """Set up a single-source proxy and return ``(entry, proxy_entity_id)``."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from homeassistant.helpers import entity_registry as er

    opts = dict(VERTICAL_OPTIONS)
    opts[CONF_ENTITIES] = [source]
    opts[CONF_ENABLE_PROXY_COVER] = True
    if extra_options:
        opts.update(extra_options)

    hass.states.async_set(
        source,
        state,
        attrs or {"current_position": 60, "supported_features": 143},
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Mirror Cover", CONF_SENSOR_TYPE: SensorType.BLIND},
        options=opts,
        entry_id=entry_id,
        title="Mirror Cover",
    )
    entry.add_to_hass(hass)
    with _patch_coordinator_refresh():
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = er.async_get(hass)
    proxy_eid = next(
        e.entity_id
        for e in reg.entities.values()
        if e.config_entry_id == entry.entry_id
        and e.unique_id.startswith(f"{entry.entry_id}_proxy_")
    )
    return entry, proxy_eid


async def test_proxy_mirrors_source_current_position(hass) -> None:
    """``current_position`` from source state appears on the proxy state."""
    _, proxy_eid = await _setup_single(
        hass,
        attrs={"current_position": 42, "supported_features": 143},
        entry_id="proxy_mirror_pos",
    )
    state = hass.states.get(proxy_eid)
    assert state.attributes.get("current_position") == 42


async def test_proxy_mirrors_source_current_tilt_position(hass) -> None:
    """``current_tilt_position`` from source state appears on the proxy state."""
    _, proxy_eid = await _setup_single(
        hass,
        attrs={
            "current_position": 60,
            "current_tilt_position": 30,
            "supported_features": 143 | 128,
        },
        entry_id="proxy_mirror_tilt",
    )
    state = hass.states.get(proxy_eid)
    assert state.attributes.get("current_tilt_position") == 30


async def test_proxy_mirrors_source_supported_features(hass) -> None:
    """``supported_features`` from source state appears on the proxy state."""
    _, proxy_eid = await _setup_single(
        hass,
        attrs={"current_position": 0, "supported_features": 15},
        entry_id="proxy_mirror_feats",
    )
    state = hass.states.get(proxy_eid)
    assert state.attributes.get("supported_features") == 15


async def test_proxy_unavailable_when_source_unavailable(hass) -> None:
    """``state == unavailable`` on source → proxy state is unavailable."""
    _, proxy_eid = await _setup_single(
        hass,
        state="unavailable",
        attrs={},
        entry_id="proxy_mirror_unavail",
    )
    state = hass.states.get(proxy_eid)
    assert state.state == "unavailable"


async def test_proxy_unavailable_when_source_unknown(hass) -> None:
    """``state == unknown`` on source → proxy state is unavailable."""
    _, proxy_eid = await _setup_single(
        hass,
        state="unknown",
        attrs={},
        entry_id="proxy_mirror_unknown",
    )
    state = hass.states.get(proxy_eid)
    assert state.state == "unavailable"


async def test_proxy_state_updates_on_source_state_change(hass) -> None:
    """Updating source state propagates to proxy state attribute."""
    _, proxy_eid = await _setup_single(
        hass,
        attrs={"current_position": 50, "supported_features": 143},
        entry_id="proxy_mirror_changes",
    )
    # Change source position
    hass.states.async_set(
        "cover.living_room",
        "open",
        {"current_position": 25, "supported_features": 143},
    )
    await hass.async_block_till_done()
    state = hass.states.get(proxy_eid)
    assert state.attributes.get("current_position") == 25


async def test_proxy_does_not_double_invert_position(hass) -> None:
    """Even with ``CONF_INVERSE_STATE=True``, the proxy mirrors the source value verbatim.

    The integration's set_position path inverts internally; the proxy must
    not invert on the read side too. If source reports 30%, proxy shows 30%.
    """
    _, proxy_eid = await _setup_single(
        hass,
        attrs={"current_position": 30, "supported_features": 143},
        entry_id="proxy_mirror_no_double_inv",
        extra_options={CONF_INVERSE_STATE: True},
    )
    state = hass.states.get(proxy_eid)
    assert state.attributes.get("current_position") == 30
