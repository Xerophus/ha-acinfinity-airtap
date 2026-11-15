"""Fan entity: power and level for each AIRTAP."""

from __future__ import annotations

import math
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.percentage import (
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)

from .const import DEFAULT_ON_LEVEL, MAX_LEVEL, Mode
from .coordinator import AirtapConfigEntry
from .entity import AirtapEntity

LEVEL_RANGE = (1, MAX_LEVEL)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirtapConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(AirtapFan(coordinator, dev_id) for dev_id in coordinator.data)


class AirtapFan(AirtapEntity, FanEntity):
    """On/off is the unit's power, as in the app; speed is Fan mode's level.

    Turning on resumes the saved mode and level. Setting a speed switches to
    Fan mode (powering on first if needed). The percentage shows the actual
    level in every mode.
    """

    _attr_name = None  # the device name
    _attr_translation_key = "airtap"
    _attr_speed_count = MAX_LEVEL
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator, dev_id: str) -> None:
        super().__init__(coordinator, dev_id, "fan")

    @property
    def is_on(self) -> bool | None:
        device = self.device
        if device.power_on is not None:
            return device.power_on
        return None if device.level is None else device.level > 0

    @property
    def percentage(self) -> int | None:
        level = self.device.level
        if self.device.power_on is False:
            return 0
        if level is None:
            return None
        return 0 if level == 0 else ranged_value_to_percentage(LEVEL_RANGE, level)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"level": self.device.level}

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self.async_turn_off()
            return
        level = math.ceil(percentage_to_ranged_value(LEVEL_RANGE, percentage))
        await self.coordinator.async_set_fan_level(self._dev_id, level)

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        if percentage is not None:
            await self.async_set_percentage(percentage)
            return
        device = self.device
        if device.effective_mode == Mode.FAN and not device.fan_mode_level:
            # Fan mode at level 0 would power on to a stopped fan.
            await self.coordinator.async_set_fan_level(self._dev_id, DEFAULT_ON_LEVEL)
        elif device.power_on is not True:
            await self.coordinator.async_set_power(self._dev_id, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_power(self._dev_id, False)
