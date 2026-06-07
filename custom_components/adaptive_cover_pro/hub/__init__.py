"""Hub subpackage for Adaptive Cover Pro.

A hub config entry (identified by CONF_IS_HUB=True in entry.data) aggregates
all cover entities configured in CONF_HUB_ENTITIES and exposes:
- One aggregate cover (avg position, dispatches to all children)
- One 4-state control select (Auto / Off / All open / All closed)
- Alexa-compatible scenes (open all / close all)

Hub entries do NOT use the normal ACP coordinator; they track child cover
entity states directly via async_track_state_change_event.
"""

from .config import HUB_ENTRY_DATA, is_hub_entry

__all__ = ["HUB_ENTRY_DATA", "is_hub_entry"]
