"""Setup, entities, writes and the raw-command service."""

from datetime import timedelta
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.ac_infinity_airtap.api import AirtapApiError, AirtapAuthError
from custom_components.ac_infinity_airtap.const import DOMAIN, Mode

from . import payloads as p
from .conftest import make_device

FAN = "fan.garage_intake"
MODE = "select.garage_intake_mode"


async def setup(hass: HomeAssistant, entry, expect_ok: bool = True) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id) is expect_ok
    await hass.async_block_till_done()


def get_device(hass, entry):
    return dr.async_get(hass).async_get_device_by_identifier((DOMAIN, p.DEV_ID), entry.entry_id)


async def test_setup_creates_entities(hass, entry, mock_client):
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED

    fan = hass.states.get(FAN)
    assert fan.state == "on"
    assert fan.attributes["percentage"] == 40
    assert fan.attributes["level"] == 4
    assert hass.states.get(MODE).state == "temp_ai"
    assert float(hass.states.get("sensor.garage_intake_temperature").state) == 25.6
    assert hass.states.get("sensor.garage_intake_fan_level").state == "4"
    assert hass.states.get("binary_sensor.garage_intake_vent").state == "on"
    assert hass.states.get("binary_sensor.garage_intake_connectivity").state == "on"
    # the test config is metric, so the 80 °F trigger is shown in °C
    cool = hass.states.get("sensor.garage_intake_cool_trigger_temperature")
    assert round(float(cool.state), 1) == 26.7

    device = get_device(hass, entry)
    assert device.model == "AIRTAP"
    assert device.sw_version == "2.0.29"
    assert not device.connections
    assert len(er.async_entries_for_device(er.async_get(hass), device.id)) == 9


async def test_auth_failure_starts_reauth(hass, entry, mock_client):
    mock_client.get_airtaps.side_effect = AirtapAuthError("bad")
    await setup(hass, entry, expect_ok=False)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert any(f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress())


async def test_api_failure_retries_setup(hass, entry, mock_client):
    mock_client.get_airtaps.side_effect = AirtapApiError("down")
    await setup(hass, entry, expect_ok=False)
    assert entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.parametrize(
    ("percentage", "level"), [(100, 10), (50, 5), (45, 5), (1, 1), (10, 1), (11, 2)]
)
async def test_set_percentage(hass, entry, mock_client, percentage, level):
    await setup(hass, entry)
    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": FAN, "percentage": percentage}, blocking=True
    )
    mock_client.set_fan_level.assert_awaited_once_with(p.DEV_ID, level)
    assert hass.states.get(MODE).state == "fan"


async def test_turn_off_powers_down(hass, entry, mock_client):
    await setup(hass, entry)
    await hass.services.async_call("fan", "turn_off", {"entity_id": FAN}, blocking=True)
    mock_client.set_power.assert_awaited_once_with(p.DEV_ID, False)
    mock_client.set_fan_level.assert_not_awaited()
    assert hass.states.get(FAN).state == "off"
    assert hass.states.get(FAN).attributes["percentage"] == 0


async def test_percentage_zero_powers_down(hass, entry, mock_client):
    await setup(hass, entry)
    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": FAN, "percentage": 0}, blocking=True
    )
    mock_client.set_power.assert_awaited_once_with(p.DEV_ID, False)
    mock_client.set_fan_level.assert_not_awaited()


def powered_off(**overrides):
    device = make_device(powerState=0, speak=0, **overrides)
    return device


async def test_turn_on_resumes_saved_mode(hass, entry, mock_client):
    mock_client.get_airtaps.return_value = [powered_off()]
    await setup(hass, entry)
    assert hass.states.get(FAN).state == "off"
    await hass.services.async_call("fan", "turn_on", {"entity_id": FAN}, blocking=True)
    mock_client.set_power.assert_awaited_once_with(p.DEV_ID, True)
    mock_client.set_fan_level.assert_not_awaited()
    assert hass.states.get(FAN).state == "on"


async def test_turn_on_when_already_on_does_nothing(hass, entry, mock_client):
    await setup(hass, entry)
    await hass.services.async_call("fan", "turn_on", {"entity_id": FAN}, blocking=True)
    mock_client.set_power.assert_not_awaited()
    mock_client.set_fan_level.assert_not_awaited()


async def test_turn_on_fan_mode_at_zero_uses_default_level(hass, entry, mock_client):
    device = powered_off(curMode=0)
    device.mode = 0
    device.fan_mode_level = 0
    mock_client.get_airtaps.return_value = [device]
    await setup(hass, entry)
    await hass.services.async_call("fan", "turn_on", {"entity_id": FAN}, blocking=True)
    mock_client.set_power.assert_awaited_once_with(p.DEV_ID, True)
    mock_client.set_fan_level.assert_awaited_once_with(p.DEV_ID, 5)


async def test_set_speed_while_off_powers_on_first(hass, entry, mock_client):
    mock_client.get_airtaps.return_value = [powered_off()]
    await setup(hass, entry)
    calls = []
    mock_client.set_power.side_effect = lambda *a: calls.append(("power", *a)) or p.UPDATE_OK
    mock_client.set_fan_level.side_effect = lambda *a: calls.append(("level", *a)) or p.UPDATE_OK
    await hass.services.async_call(
        "fan", "turn_on", {"entity_id": FAN, "percentage": 60}, blocking=True
    )
    assert calls == [("power", p.DEV_ID, True), ("level", p.DEV_ID, 6)]
    assert hass.states.get(FAN).attributes["percentage"] == 60


async def test_set_speed_while_on_skips_power(hass, entry, mock_client):
    await setup(hass, entry)
    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": FAN, "percentage": 20}, blocking=True
    )
    mock_client.set_power.assert_not_awaited()
    mock_client.set_fan_level.assert_awaited_once_with(p.DEV_ID, 2)


@pytest.mark.parametrize(("option", "mode"), [("cool", Mode.COOL), ("heat", Mode.HEAT), ("temp_ai", Mode.TEMP_AI)])
async def test_select_mode(hass, entry, mock_client, option, mode):
    await setup(hass, entry)
    await hass.services.async_call(
        "select", "select_option", {"entity_id": MODE, "option": option}, blocking=True
    )
    mock_client.set_mode.assert_awaited_once_with(p.DEV_ID, mode)
    assert hass.states.get(MODE).state == option


async def test_select_fan_mode_uses_saved_level(hass, entry, mock_client):
    await setup(hass, entry)
    await hass.services.async_call(
        "select", "select_option", {"entity_id": MODE, "option": "fan"}, blocking=True
    )
    mock_client.set_fan_level.assert_awaited_once_with(p.DEV_ID, 7)


async def test_select_advanced_refused(hass, entry, mock_client):
    await setup(hass, entry)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "select", "select_option", {"entity_id": MODE, "option": "advanced"}, blocking=True
        )
    mock_client.set_mode.assert_not_awaited()


async def test_command_failure_raises(hass, entry, mock_client):
    await setup(hass, entry)
    mock_client.set_power.side_effect = AirtapApiError("100001 param error")
    with pytest.raises(HomeAssistantError, match="command failed"):
        await hass.services.async_call("fan", "turn_off", {"entity_id": FAN}, blocking=True)
    assert hass.states.get(FAN).state == "on"


async def test_offline_fan_unavailable_but_connectivity_reported(hass, entry, mock_client):
    offline = make_device()
    offline.online = False
    mock_client.get_airtaps.return_value = [offline]
    await setup(hass, entry)
    assert hass.states.get(FAN).state == "unavailable"
    assert hass.states.get("binary_sensor.garage_intake_connectivity").state == "off"


async def test_raw_command_service(hass, entry, mock_client):
    await setup(hass, entry)
    device = get_device(hass, entry)
    result = await hass.services.async_call(
        DOMAIN,
        "send_raw_command",
        {"device_id": device.id, "params": {"atType": 1, "targetTempF": 82}, "field_ids": [16, 19]},
        blocking=True,
        return_response=True,
    )
    mock_client.send_command.assert_awaited_once_with(
        p.DEV_ID, {"atType": 1, "targetTempF": 82}, [16, 19]
    )
    assert result == {"response": p.UPDATE_OK}


async def test_raw_command_unknown_device(hass, entry, mock_client):
    await setup(hass, entry)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "send_raw_command",
            {"device_id": "nope", "params": {}, "field_ids": [16]},
            blocking=True,
        )


async def test_unload(hass, entry, mock_client):
    await setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_diagnostics_redacts(hass, entry, mock_client):
    from custom_components.ac_infinity_airtap.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    await setup(hass, entry)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["entry"] == {"email": "**REDACTED**", "password": "**REDACTED**"}
    dev = diag["devices"][0]
    assert dev["device_info_list"]["devMacAddr"] == "**REDACTED**"
    assert dev["device_info_list"]["deviceInfo"]["devMacAddr"] == "**REDACTED**"
    assert dev["mode_settings"]["targetTempF"] == 80
    assert dev["parsed"]["level"] == 4
