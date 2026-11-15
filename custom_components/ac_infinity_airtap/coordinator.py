"""Polling coordinator for AIRTAP fans."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AirtapApiError, AirtapAuthError, AirtapClient, AirtapDevice
from .const import (
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    PENDING_WRITE_SECONDS,
    Mode,
)

_LOGGER = logging.getLogger(__name__)

type AirtapConfigEntry = ConfigEntry[AirtapCoordinator]


@dataclass
class _PendingWrite:
    """Values just written, shown until the cloud reports them (or they expire)."""

    values: dict[str, Any]
    expires: float


class AirtapCoordinator(DataUpdateCoordinator[dict[str, AirtapDevice]]):
    """Fetches every AIRTAP on the account in one refresh."""

    config_entry: AirtapConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: AirtapConfigEntry, client: AirtapClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
            ),
        )
        self.client = client
        self._pending: dict[str, _PendingWrite] = {}

    async def _async_update_data(self) -> dict[str, AirtapDevice]:
        try:
            devices = await self.client.get_airtaps()
        except AirtapAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except AirtapApiError as err:
            raise UpdateFailed(str(err)) from err
        return {d.dev_id: self._apply_pending(d) for d in devices}

    def _apply_pending(self, device: AirtapDevice) -> AirtapDevice:
        pending = self._pending.get(device.dev_id)
        if pending is None:
            return device
        reported = all(getattr(device, k) == v for k, v in pending.values.items())
        if reported or time.monotonic() > pending.expires:
            del self._pending[device.dev_id]
            return device
        return replace(device, **pending.values)

    def _remember(self, dev_id: str, **values: Any) -> None:
        self._pending[dev_id] = _PendingWrite(
            values, time.monotonic() + PENDING_WRITE_SECONDS
        )
        if self.data and dev_id in self.data:
            self.async_set_updated_data(
                {**self.data, dev_id: replace(self.data[dev_id], **values)}
            )

    async def async_set_power(self, dev_id: str, on: bool) -> None:
        """Power the unit on (resuming its saved mode and level) or off."""
        await self._write(self.client.set_power(dev_id, on))
        if on:
            self._remember(dev_id, power_on=True)
        else:
            self._remember(dev_id, power_on=False, level=0)

    async def async_set_fan_level(self, dev_id: str, level: int) -> None:
        """Fan mode at a fixed level (0 = stopped). Powers the unit on first if needed."""
        device = self.data.get(dev_id) if self.data else None
        if device is not None and device.power_on is False:
            await self._write(self.client.set_power(dev_id, True))
        await self._write(self.client.set_fan_level(dev_id, level))
        self._remember(dev_id, power_on=True, mode=int(Mode.FAN),
                       current_mode=int(Mode.FAN), level=level, fan_mode_level=level)

    async def async_set_mode(self, dev_id: str, mode: Mode) -> None:
        """Cool, Heat or Temp AI, with that mode's saved settings."""
        await self._write(self.client.set_mode(dev_id, mode))
        self._remember(dev_id, mode=int(mode), current_mode=int(mode))

    async def async_send_raw_command(
        self, dev_id: str, params: dict[str, Any], field_ids: list[int]
    ) -> dict[str, Any]:
        body = await self._write(self.client.send_command(dev_id, params, field_ids))
        await self.async_request_refresh()
        return body

    async def _write(self, call) -> dict[str, Any]:
        try:
            return await call
        except AirtapAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(f"AC Infinity rejected the login: {err}") from err
        except AirtapApiError as err:
            raise HomeAssistantError(f"AC Infinity command failed: {err}") from err
