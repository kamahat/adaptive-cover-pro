"""Constants for the opt-in proxy cover feature."""

from __future__ import annotations


def test_proxy_cover_constants_exist() -> None:
    """CONF_ENABLE_PROXY_COVER and DEFAULT_ENABLE_PROXY_COVER are defined."""
    from custom_components.adaptive_cover_pro.const import (
        CONF_ENABLE_PROXY_COVER,
        DEFAULT_ENABLE_PROXY_COVER,
    )

    assert CONF_ENABLE_PROXY_COVER == "enable_proxy_cover"
    assert DEFAULT_ENABLE_PROXY_COVER is False
