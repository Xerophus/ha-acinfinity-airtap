"""Fixtures for the AIRTAP tests."""

from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ac_infinity_airtap.api import AirtapDevice
from custom_components.ac_infinity_airtap.const import DOMAIN

from . import payloads as p


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def make_device(**info_overrides) -> AirtapDevice:
    raw = deepcopy(p.AIRTAP_T6)
    raw["deviceInfo"].update(info_overrides)
    return AirtapDevice.from_api(raw, deepcopy(p.MODE_SETTINGS["data"]))


@pytest.fixture
def mock_client():
    """Patch the client class used by the integration and the config flow."""
    with (
        patch("custom_components.ac_infinity_airtap.AirtapClient", autospec=True) as cls,
        patch("custom_components.ac_infinity_airtap.config_flow.AirtapClient", new=cls),
    ):
        client = cls.return_value
        client.get_airtaps = AsyncMock(return_value=[make_device()])
        client.login = AsyncMock()
        client.set_fan_level = AsyncMock(return_value=p.UPDATE_OK)
        client.set_mode = AsyncMock(return_value=p.UPDATE_OK)
        client.send_command = AsyncMock(return_value=p.UPDATE_OK)
        yield client


@pytest.fixture
def entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="AIRTAP (me@example.com)",
        unique_id="me@example.com",
        data={"email": "me@example.com", "password": "pw"},
    )
