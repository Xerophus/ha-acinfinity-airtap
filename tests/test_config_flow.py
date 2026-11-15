"""Config, reauth and options flows."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ac_infinity_airtap.api import AirtapAuthError, AirtapConnectionError
from custom_components.ac_infinity_airtap.const import DOMAIN

USER = {"email": " Me@Example.com ", "password": "pw"}


async def start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_user_flow_creates_entry(hass, mock_client):
    result = await start(hass)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"email": "Me@Example.com", "password": "pw"}
    assert result["result"].unique_id == "me@example.com"


async def test_user_flow_errors(hass, mock_client):
    result = await start(hass)
    for side_effect, error in (
        (AirtapAuthError("x"), "invalid_auth"),
        (AirtapConnectionError("x"), "cannot_connect"),
        (RuntimeError("x"), "unknown"),
    ):
        mock_client.login.side_effect = side_effect
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
        assert result["errors"] == {"base": error}

    mock_client.login.side_effect = None
    mock_client.get_airtaps.return_value = []
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["errors"] == {"base": "no_airtaps"}


async def test_duplicate_account_aborts(hass, entry, mock_client):
    entry.add_to_hass(hass)
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(hass, entry, mock_client):
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    mock_client.login.side_effect = AirtapAuthError("x")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"password": "bad"})
    assert result["errors"] == {"base": "invalid_auth"}
    mock_client.login.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"password": "new"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "new"


async def test_options_poll_interval(hass, entry, mock_client):
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"poll_interval": 30}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {"poll_interval": 30}
    assert entry.runtime_data.update_interval.total_seconds() == 30
