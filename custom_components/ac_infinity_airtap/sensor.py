"""Sensors for each AIRTAP."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import AirtapDevice
from .coordinator import AirtapConfigEntry
from .entity import AirtapEntity


@dataclass(frozen=True, kw_only=True)
class AirtapSensorDescription(SensorEntityDescription):
    value_fn: Callable[[AirtapDevice], float | int | None]


SENSORS: tuple[AirtapSensorDescription, ...] = (
    AirtapSensorDescription(
        key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda d: d.temperature_c,
    ),
    AirtapSensorDescription(
        key="level",
        translation_key="level",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.level,
    ),
    # Mode settings, read-only until their write fields are verified.
    AirtapSensorDescription(
        key="cool_trigger",
        translation_key="cool_trigger",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.cool_trigger_f,
    ),
    AirtapSensorDescription(
        key="heat_trigger",
        translation_key="heat_trigger",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.heat_trigger_f,
    ),
    AirtapSensorDescription(
        key="ai_deviation",
        translation_key="ai_deviation",
        device_class=SensorDeviceClass.TEMPERATURE_DELTA,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.ai_deviation_f,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirtapConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        AirtapSensor(coordinator, dev_id, description)
        for dev_id in coordinator.data
        for description in SENSORS
    )


class AirtapSensor(AirtapEntity, SensorEntity):
    entity_description: AirtapSensorDescription

    def __init__(self, coordinator, dev_id: str, description: AirtapSensorDescription) -> None:
        super().__init__(coordinator, dev_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | None:
        return self.entity_description.value_fn(self.device)
