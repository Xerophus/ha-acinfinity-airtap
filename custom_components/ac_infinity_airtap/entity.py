"""Base entity for AIRTAP fans."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import AirtapDevice
from .const import DOMAIN, MANUFACTURER
from .coordinator import AirtapCoordinator


class AirtapEntity(CoordinatorEntity[AirtapCoordinator]):
    """An entity belonging to one AIRTAP."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AirtapCoordinator, dev_id: str, key: str) -> None:
        super().__init__(coordinator)
        self._dev_id = dev_id
        self._attr_unique_id = f"{dev_id}_{key}"
        device = coordinator.data[dev_id]
        # No MAC connection on purpose: the device registry merges devices that
        # share one, which would fold this into the Matter or upstream device.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dev_id)},
            name=device.name,
            manufacturer=MANUFACTURER,
            model="AIRTAP",
            sw_version=device.firmware,
            hw_version=device.hardware,
        )

    @property
    def device(self) -> AirtapDevice:
        return self.coordinator.data[self._dev_id]

    @property
    def available(self) -> bool:
        return (
            super().available
            and self._dev_id in self.coordinator.data
            and self.device.online
        )
