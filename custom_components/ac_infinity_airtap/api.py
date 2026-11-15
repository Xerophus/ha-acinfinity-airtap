"""Client for the AC Infinity cloud API, limited to AIRTAP register fans.

Kept free of Home Assistant imports so it can be tested on its own.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import logging
from typing import Any
from urllib.parse import urlencode

import aiohttp

from .const import (
    AIRTAP_DEV_TYPE,
    API_HOST,
    FIELD_AT_TYPE,
    FIELD_ON_SPEED,
    MAX_LEVEL,
    Mode,
)

_LOGGER = logging.getLogger(__name__)

PATH_LOGIN = "/api/user/appUserLogin"
PATH_DEVICES = "/api/user/devInfoListAll"
PATH_MODE_SETTINGS = "/api/dev/getdevModeSettingList"
PATH_MODE_AND_SETTING = "/api/dev/modeAndSetting"

REQUEST_TIMEOUT = 15
# The API rejects passwords over 25 characters; the mobile app truncates them.
MAX_PASSWORD_LENGTH = 25


class AirtapApiError(Exception):
    """The API answered with an error."""


class AirtapAuthError(AirtapApiError):
    """The e-mail or password was rejected."""


class AirtapConnectionError(AirtapApiError):
    """The API could not be reached or returned something unusable."""


def is_airtap(raw: dict[str, Any]) -> bool:
    """Return True for an AIRTAP entry from devInfoListAll."""
    return raw.get("airTap") is True or raw.get("devType") == AIRTAP_DEV_TYPE


def _hundredths(value: Any) -> float | None:
    """Temperatures in deviceInfo are sent as hundredths (1730 = 17.30)."""
    if value is None:
        return None
    try:
        return round(int(value) / 100, 2)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass
class AirtapDevice:
    """One AIRTAP fan: status from devInfoListAll plus its port-0 mode settings."""

    dev_id: str
    name: str
    mac: str | None
    firmware: str | None
    hardware: str | None
    online: bool
    temperature_c: float | None
    temperature_f: float | None
    level: int | None  # current fan level, 0-10 ("speak")
    current_mode: int | None  # deviceInfo.curMode
    vent_open: bool | None  # deviceInfo.isWindSteering
    # From getdevModeSettingList (None until the settings call succeeds):
    mode: int | None = None  # atType
    fan_mode_level: int | None = None  # onSpead, the level used in Fan mode
    cool_trigger_f: int | None = None  # targetTempF
    heat_trigger_f: int | None = None  # waterTempHighValueF
    ai_deviation_f: int | None = None  # devLtf
    raw_info: dict[str, Any] = field(default_factory=dict, repr=False)
    raw_settings: dict[str, Any] | None = field(default=None, repr=False)

    @property
    def effective_mode(self) -> int | None:
        """The mode from the settings, falling back to the status report."""
        return self.mode if self.mode is not None else self.current_mode

    @classmethod
    def from_api(
        cls, raw: dict[str, Any], settings: dict[str, Any] | None
    ) -> AirtapDevice:
        info = raw.get("deviceInfo") or {}
        wind = _int(info.get("isWindSteering"))
        device = cls(
            dev_id=str(raw["devId"]),
            name=raw.get("devName") or f"AIRTAP {raw['devId']}",
            mac=raw.get("devMacAddr") or info.get("devMacAddr"),
            firmware=raw.get("firmwareVersion"),
            hardware=raw.get("hardwareVersion"),
            online=bool(_int(raw.get("online", info.get("online")))),
            temperature_c=_hundredths(info.get("temperature")),
            temperature_f=_hundredths(info.get("temperatureF")),
            level=_int(info.get("speak")),
            current_mode=_int(info.get("curMode")),
            vent_open=None if wind is None else wind == 1,
            raw_info=raw,
            raw_settings=settings,
        )
        if settings:
            device.mode = _int(settings.get("atType"))
            device.fan_mode_level = _int(settings.get("onSpead"))
            device.cool_trigger_f = _int(settings.get("targetTempF"))
            device.heat_trigger_f = _int(settings.get("waterTempHighValueF"))
            device.ai_deviation_f = _int(settings.get("devLtf"))
        return device


class AirtapClient:
    """Talks to the AC Infinity cloud the way the Android app does."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        host: str = API_HOST,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password[:MAX_PASSWORD_LENGTH]
        self._host = host
        self._token: str | None = None
        self._login_lock = asyncio.Lock()

    @property
    def logged_in(self) -> bool:
        return self._token is not None

    async def login(self) -> None:
        """Log in and keep the returned app id, which the API uses as a token."""
        body = await self._send(
            "POST",
            PATH_LOGIN,
            data={"appEmail": self._email, "appPasswordl": self._password},
            auth=False,
        )
        if body.get("code") != 200:
            raise AirtapAuthError(body.get("msg") or "login rejected")
        try:
            self._token = str(body["data"]["appId"])
        except (KeyError, TypeError) as err:
            raise AirtapConnectionError("login response had no appId") from err

    async def get_airtaps(self) -> list[AirtapDevice]:
        """Return every AIRTAP on the account, with its mode settings."""
        body = await self._call("POST", PATH_DEVICES, data={"userId": self._token})
        entries = [d for d in (body.get("data") or []) if is_airtap(d)]
        settings = await asyncio.gather(
            *(self._get_settings(str(d["devId"])) for d in entries),
            return_exceptions=True,
        )
        devices = []
        for raw, result in zip(entries, settings, strict=True):
            if isinstance(result, BaseException):
                if isinstance(result, AirtapAuthError):
                    raise result
                _LOGGER.debug("Settings for %s unavailable: %s", raw["devId"], result)
                result = None
            devices.append(AirtapDevice.from_api(raw, result))
        return devices

    async def _get_settings(self, dev_id: str) -> dict[str, Any] | None:
        data = {"devId": dev_id, "port": 0}
        body = await self._call("POST", PATH_MODE_SETTINGS, data=data, min_version=True)
        if body.get("data") is None:
            # Some firmware answers only without the newer API version header.
            body = await self._call("POST", PATH_MODE_SETTINGS, data=data)
        return body.get("data")

    async def set_fan_level(self, dev_id: str, level: int) -> dict[str, Any]:
        """Switch to Fan mode at a fixed level; level 0 stops the fan."""
        if not 0 <= level <= MAX_LEVEL:
            raise ValueError(f"level must be 0-{MAX_LEVEL}, got {level}")
        return await self.send_command(
            dev_id,
            {"atType": int(Mode.FAN), "onSpead": level},
            [FIELD_AT_TYPE, FIELD_ON_SPEED],
        )

    async def set_mode(self, dev_id: str, mode: Mode) -> dict[str, Any]:
        """Switch to Cool, Heat or Temp AI, keeping that mode's saved settings.

        Fan mode needs a level, so it goes through set_fan_level instead.
        """
        if mode in (Mode.FAN, Mode.ADVANCED):
            raise ValueError(f"set_mode does not handle {mode.name}")
        return await self.send_command(dev_id, {"atType": int(mode)}, [FIELD_AT_TYPE])

    async def send_command(
        self, dev_id: str, params: dict[str, Any], field_ids: list[int]
    ) -> dict[str, Any]:
        """PUT /api/dev/modeAndSetting with the minimal parameters the app sends.

        AIRTAPs reject the full payloads used for UIS controllers. Note the API's
        own spelling: "onSpead"; "onSpeed" is accepted but ignored.
        """
        query = {
            "devId": dev_id,
            "port": 0,
            **params,
            "modeAndSettingIdStr": json.dumps(list(field_ids), separators=(",", ":")),
        }
        return await self._call(
            "PUT", f"{PATH_MODE_AND_SETTING}?{urlencode(query)}", min_version=True
        )

    async def _call(
        self,
        method: str,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        min_version: bool = False,
    ) -> dict[str, Any]:
        """Make an authenticated call, logging in (again) when needed."""
        if not self.logged_in:
            await self._relogin(None)
        token = self._token
        if data is not None and "userId" in data:
            data = {**data, "userId": token}
        body = await self._send(method, path, data=data, min_version=min_version)
        if _is_expired(body):
            await self._relogin(token)
            if data is not None and "userId" in data:
                data = {**data, "userId": self._token}
            body = await self._send(method, path, data=data, min_version=min_version)
        if body.get("code") != 200:
            if _is_expired(body):
                raise AirtapAuthError(body.get("msg") or "session expired")
            raise AirtapApiError(f"{path.split('?')[0]}: {body.get('code')} {body.get('msg')}")
        return body

    async def _relogin(self, stale_token: str | None) -> None:
        async with self._login_lock:
            if self._token is None or self._token == stale_token:
                self._token = None
                await self.login()

    async def _send(
        self,
        method: str,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        auth: bool = True,
        min_version: bool = False,
    ) -> dict[str, Any]:
        headers = {"User-Agent": "okhttp/4.12.0"}
        if auth and self._token:
            headers["token"] = self._token
        if min_version:
            headers["minversion"] = "3.5"
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.request(
                    method, f"{self._host}{path}", data=data, headers=headers
                ) as response:
                    if response.status != 200:
                        raise AirtapConnectionError(f"HTTP {response.status} from {path.split('?')[0]}")
                    body = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise AirtapConnectionError(str(err) or type(err).__name__) from err
        if not isinstance(body, dict):
            raise AirtapConnectionError("unexpected response body")
        return body


def _is_expired(body: dict[str, Any]) -> bool:
    # {'msg': 'Login Expired Please login again!', 'code': 403}
    return body.get("code") == 403 or "expired" in str(body.get("msg", "")).lower()
