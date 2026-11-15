"""Tests for the HA-independent API client, against a scripted fake session."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import aiohttp
import pytest

from custom_components.ac_infinity_airtap.api import (
    PATH_DEVICES,
    PATH_LOGIN,
    PATH_MODE_AND_SETTING,
    PATH_MODE_SETTINGS,
    AirtapApiError,
    AirtapAuthError,
    AirtapClient,
    AirtapConnectionError,
    AirtapDevice,
)
from custom_components.ac_infinity_airtap.const import Mode

from . import payloads as p


@dataclass
class Call:
    method: str
    path: str
    query: dict[str, str]
    data: dict[str, Any] | None
    headers: dict[str, str]


class _Response:
    def __init__(self, status: int, body: Any) -> None:
        self.status = status
        self._body = body

    async def json(self, content_type=None):
        return self._body

    async def __aenter__(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    """Answers each (method, path) from a queue and records every call."""

    def __init__(self) -> None:
        self._answers: dict[tuple[str, str], deque] = defaultdict(deque)
        self.calls: list[Call] = []

    def add(self, method: str, path: str, body: Any, status: int = 200) -> None:
        self._answers[(method, path)].append((status, body))

    def request(self, method, url, data=None, headers=None):
        parts = urlsplit(url)
        assert f"{parts.scheme}://{parts.netloc}" == p.HOST
        self.calls.append(
            Call(method, parts.path, dict(parse_qsl(parts.query)), data, dict(headers or {}))
        )
        queue = self._answers[(method, parts.path)]
        assert queue, f"unexpected {method} {parts.path}"
        return _Response(*queue.popleft())

    def made(self, method: str, path: str) -> list[Call]:
        return [c for c in self.calls if c.method == method and c.path == path]


@pytest.fixture
def session() -> FakeSession:
    s = FakeSession()
    s.add("POST", PATH_LOGIN, p.LOGIN_OK)
    return s


@pytest.fixture
def client(session) -> AirtapClient:
    return AirtapClient(session, "me@example.com", "pw")  # type: ignore[arg-type]


async def test_login_truncates_password_and_sends_app_field_names(session):
    client = AirtapClient(session, "me@example.com", "x" * 40)  # type: ignore[arg-type]
    await client.login()
    (call,) = session.made("POST", PATH_LOGIN)
    assert call.data == {"appEmail": "me@example.com", "appPasswordl": "x" * 25}
    assert "token" not in call.headers
    assert call.headers["User-Agent"] == "okhttp/4.12.0"
    assert client.logged_in


async def test_login_rejected():
    session = FakeSession()
    session.add("POST", PATH_LOGIN, p.LOGIN_BAD)
    with pytest.raises(AirtapAuthError):
        await AirtapClient(session, "me@example.com", "bad").login()  # type: ignore[arg-type]


async def test_get_airtaps_parses_t6_and_skips_other_controllers(session, client):
    session.add("POST", PATH_DEVICES, p.DEVICES)
    session.add("POST", PATH_MODE_SETTINGS, p.MODE_SETTINGS)
    devices = await client.get_airtaps()

    (listing,) = session.made("POST", PATH_DEVICES)
    assert listing.data == {"userId": p.TOKEN}
    assert listing.headers["token"] == p.TOKEN
    (settings,) = session.made("POST", PATH_MODE_SETTINGS)  # none for the UIS controller
    assert settings.data == {"devId": p.DEV_ID, "port": 0}
    assert settings.headers["minversion"] == "3.5"

    (d,) = devices
    assert d.dev_id == p.DEV_ID
    assert d.name == "Garage Intake"
    assert d.firmware == "2.0.29"
    assert d.online is True
    assert d.temperature_c == 25.6
    assert d.temperature_f == 78.08
    assert d.level == 4
    assert d.current_mode == 3
    assert d.vent_open is True
    assert d.power_on is True
    assert d.mode == Mode.TEMP_AI
    assert d.fan_mode_level == 7
    assert d.cool_trigger_f == 80
    assert d.heat_trigger_f == 60
    assert d.ai_deviation_f == 3


async def test_settings_retry_without_min_version_when_no_data(session, client):
    session.add("POST", PATH_DEVICES, p.DEVICES)
    session.add("POST", PATH_MODE_SETTINGS, p.NO_DATA)
    session.add("POST", PATH_MODE_SETTINGS, p.MODE_SETTINGS)
    (d,) = await client.get_airtaps()
    first, second = session.made("POST", PATH_MODE_SETTINGS)
    assert "minversion" in first.headers
    assert "minversion" not in second.headers
    assert d.mode == Mode.TEMP_AI


async def test_settings_failure_still_returns_status(session, client):
    session.add("POST", PATH_DEVICES, p.DEVICES)
    session.add("POST", PATH_MODE_SETTINGS, {"code": 999999, "msg": "boom"})
    (d,) = await client.get_airtaps()
    assert d.level == 4
    assert d.mode is None
    assert d.effective_mode == 3


async def test_expired_session_logs_in_again_and_retries(session, client):
    session.add("POST", PATH_DEVICES, p.EXPIRED)
    session.add("POST", PATH_LOGIN, {"code": 200, "data": {"appId": "fresh"}})
    session.add("POST", PATH_DEVICES, {"code": 200, "data": []})
    assert await client.get_airtaps() == []
    _, retry = session.made("POST", PATH_DEVICES)
    assert retry.headers["token"] == "fresh"
    assert retry.data == {"userId": "fresh"}


async def test_still_expired_after_relogin_is_auth_error(session, client):
    session.add("POST", PATH_DEVICES, p.EXPIRED)
    session.add("POST", PATH_LOGIN, p.LOGIN_OK)
    session.add("POST", PATH_DEVICES, p.EXPIRED)
    with pytest.raises(AirtapAuthError):
        await client.get_airtaps()


async def test_set_fan_level_uses_api_spelling(session, client):
    session.add("PUT", PATH_MODE_AND_SETTING, p.UPDATE_OK)
    await client.set_fan_level(p.DEV_ID, 6)
    (put,) = session.made("PUT", PATH_MODE_AND_SETTING)
    assert put.query == {
        "devId": p.DEV_ID,
        "port": "0",
        "atType": "0",
        "onSpead": "6",
        "modeAndSettingIdStr": "[16,18]",
    }
    assert put.data is None
    assert put.headers["minversion"] == "3.5"
    assert put.headers["token"] == p.TOKEN


@pytest.mark.parametrize(("on", "value"), [(True, "1"), (False, "0")])
async def test_set_power(session, client, on, value):
    session.add("PUT", PATH_MODE_AND_SETTING, p.UPDATE_OK)
    await client.set_power(p.DEV_ID, on)
    (put,) = session.made("PUT", PATH_MODE_AND_SETTING)
    assert put.query == {
        "devId": p.DEV_ID,
        "port": "0",
        "powerState": value,
        "modeAndSettingIdStr": "[22]",
    }


@pytest.mark.parametrize("level", [-1, 11])
async def test_set_fan_level_range(client, level):
    with pytest.raises(ValueError):
        await client.set_fan_level(p.DEV_ID, level)


async def test_set_mode_sends_only_the_mode(session, client):
    session.add("PUT", PATH_MODE_AND_SETTING, p.UPDATE_OK)
    await client.set_mode(p.DEV_ID, Mode.COOL)
    (put,) = session.made("PUT", PATH_MODE_AND_SETTING)
    assert put.query == {
        "devId": p.DEV_ID,
        "port": "0",
        "atType": "1",
        "modeAndSettingIdStr": "[16]",
    }


@pytest.mark.parametrize("mode", [Mode.FAN, Mode.ADVANCED])
async def test_set_mode_refuses_fan_and_advanced(client, mode):
    with pytest.raises(ValueError):
        await client.set_mode(p.DEV_ID, mode)


async def test_command_error_raises(session, client):
    session.add("PUT", PATH_MODE_AND_SETTING, {"code": 100001, "msg": "param error"})
    with pytest.raises(AirtapApiError, match="100001"):
        await client.set_mode(p.DEV_ID, Mode.HEAT)


async def test_http_error_is_connection_error():
    session = FakeSession()
    session.add("POST", PATH_LOGIN, None, status=502)
    with pytest.raises(AirtapConnectionError, match="502"):
        await AirtapClient(session, "a@b.c", "pw").login()  # type: ignore[arg-type]


async def test_network_error_is_connection_error():
    session = FakeSession()
    session.add("POST", PATH_LOGIN, aiohttp.ClientConnectionError("refused"))
    with pytest.raises(AirtapConnectionError):
        await AirtapClient(session, "a@b.c", "pw").login()  # type: ignore[arg-type]


def test_unknown_values_parse_to_none():
    d = AirtapDevice.from_api({"devId": 5, "deviceInfo": {"speak": "x"}}, None)
    assert d.dev_id == "5"
    assert d.level is None
    assert d.vent_open is None
    assert d.power_on is None
    assert d.online is False
