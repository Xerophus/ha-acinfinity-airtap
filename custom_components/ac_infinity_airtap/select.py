"""Mode select for each AIRTAP."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DEFAULT_ON_LEVEL, DOMAIN, MODE_BY_OPTION, MODE_OPTIONS, Mode
from .coordinator import AirtapConfigEntry
from .entity import AirtapEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirtapConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(AirtapModeSelect(coordinator, dev_id) for dev_id in coordinator.data)


class AirtapModeSelect(AirtapEntity, SelectEntity):
    """Fan, Cool, Heat or Temp AI. Advanced (app schedules) is shown but not settable."""

    _attr_translation_key = "mode"
    _attr_options = list(MODE_OPTIONS.values())

    def __init__(self, coordinator, dev_id: str) -> None:
        super().__init__(coordinator, dev_id, "mode")

    @property
    def current_option(self) -> str | None:
        mode = self.device.effective_mode
        try:
            return MODE_OPTIONS[Mode(mode)] if mode is not None else None
        except ValueError:
            return None

    async def async_select_option(self, option: str) -> None:
        mode = MODE_BY_OPTION[option]
        if mode is Mode.ADVANCED:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="advanced_not_settable"
            )
        if mode is Mode.FAN:
            level = self.device.fan_mode_level
            await self.coordinator.async_set_fan_level(
                self._dev_id, level if level else DEFAULT_ON_LEVEL
            )
        else:
            await self.coordinator.async_set_mode(self._dev_id, mode)
