"""Diagnostics: the raw API payloads for each AIRTAP, with identifiers redacted."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .coordinator import AirtapConfigEntry

TO_REDACT = {
    CONF_EMAIL,
    CONF_PASSWORD,
    "devMacAddr",
    "devCode",
    "wifiName",
    "ipAddr",
    "appEmail",
    "userId",
    "token",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AirtapConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "devices": [
            {
                "parsed": {
                    k: v
                    for k, v in vars(device).items()
                    if k not in ("raw_info", "raw_settings", "mac")
                },
                "device_info_list": async_redact_data(device.raw_info, TO_REDACT),
                "mode_settings": async_redact_data(device.raw_settings or {}, TO_REDACT),
            }
            for device in (coordinator.data or {}).values()
        ],
    }
