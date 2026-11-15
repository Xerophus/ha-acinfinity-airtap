"""AC Infinity AIRTAP register fans, controlled through the AC Infinity cloud."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import AirtapClient
from .const import ATTR_FIELD_IDS, ATTR_PARAMS, DOMAIN, SERVICE_SEND_RAW_COMMAND
from .coordinator import AirtapConfigEntry, AirtapCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.FAN, Platform.SELECT, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

ATTR_DEVICE_ID = "device_id"
RAW_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_PARAMS): vol.Schema({cv.string: vol.Any(int, str)}),
        vol.Required(ATTR_FIELD_IDS): [vol.Coerce(int)],
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def send_raw_command(call: ServiceCall) -> ServiceResponse:
        device = dr.async_get(hass).async_get(call.data[ATTR_DEVICE_ID])
        dev_id = next(
            (i for d, i in (device.identifiers if device else ()) if d == DOMAIN), None
        )
        entry = next(
            (
                e
                for e in hass.config_entries.async_loaded_entries(DOMAIN)
                if device and e.entry_id in device.config_entries
            ),
            None,
        )
        if dev_id is None or entry is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="unknown_device"
            )
        coordinator: AirtapCoordinator = entry.runtime_data
        body = await coordinator.async_send_raw_command(
            dev_id, call.data[ATTR_PARAMS], call.data[ATTR_FIELD_IDS]
        )
        return {"response": body}

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_RAW_COMMAND,
        send_raw_command,
        schema=RAW_COMMAND_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AirtapConfigEntry) -> bool:
    client = AirtapClient(
        async_get_clientsession(hass), entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD]
    )
    coordinator = AirtapCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: AirtapConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: AirtapConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
