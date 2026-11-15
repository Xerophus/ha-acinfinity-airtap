"""Binary sensors for each AIRTAP."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AirtapConfigEntry
from .entity import AirtapEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirtapConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    for dev_id in coordinator.data:
        entities.append(AirtapOnline(coordinator, dev_id))
        entities.append(AirtapVent(coordinator, dev_id))
    async_add_entities(entities)


class AirtapOnline(AirtapEntity, BinarySensorEntity):
    """Whether the cloud can reach the fan. Stays available when it can't."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, dev_id: str) -> None:
        super().__init__(coordinator, dev_id, "online")

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._dev_id in self.coordinator.data

    @property
    def is_on(self) -> bool:
        return self.device.online


class AirtapVent(AirtapEntity, BinarySensorEntity):
    """deviceInfo.isWindSteering: on a T4 it follows the louvers (open while running,
    closed at level 0); on a T6 with the vent set to "Open" it stays on."""

    _attr_device_class = BinarySensorDeviceClass.OPENING
    _attr_translation_key = "vent"

    def __init__(self, coordinator, dev_id: str) -> None:
        super().__init__(coordinator, dev_id, "vent")

    @property
    def is_on(self) -> bool | None:
        return self.device.vent_open
