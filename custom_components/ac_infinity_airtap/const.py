"""Constants for the AC Infinity AIRTAP integration."""

from __future__ import annotations

from enum import IntEnum

DOMAIN = "ac_infinity_airtap"
MANUFACTURER = "AC Infinity"
API_HOST = "https://www.acinfinityserver.com"

CONF_POLL_INTERVAL = "poll_interval"
DEFAULT_POLL_INTERVAL = 10  # seconds
MIN_POLL_INTERVAL = 5
MAX_POLL_INTERVAL = 300

# AIRTAP fans report this devType in /api/user/devInfoListAll (alongside "airTap": true).
AIRTAP_DEV_TYPE = 48

# Fan levels as the AIRTAP and the app use them: 0 (stopped) to 10.
MAX_LEVEL = 10
DEFAULT_ON_LEVEL = 5

# After a write, the cloud can take ~20 s to report the new values. Until it does
# (or this many seconds pass) the coordinator keeps showing what was written.
PENDING_WRITE_SECONDS = 45


class Mode(IntEnum):
    """AIRTAP T4/T6 modes (the "atType" field).

    Mapped on a T6 (fw 2.0.29) and a T4 (fw 5.0.26) by polling the API while
    switching modes in the app (dalinicus/homeassistant-acinfinity PR #154).
    These do NOT match the UIS controllers' AtType numbering.
    """

    FAN = 0  # fixed level, from "onSpead"; level 0 = stopped
    COOL = 1  # runs when room temperature is above a trigger ("targetTempF")
    HEAT = 2  # runs when room temperature is below a trigger ("waterTempHighValueF")
    TEMP_AI = 3  # the default; follows a temperature deviation ("devLtf")
    ADVANCED = 15  # app schedules ("devAdvGroups"); not editable from HA


MODE_OPTIONS: dict[Mode, str] = {
    Mode.FAN: "fan",
    Mode.COOL: "cool",
    Mode.HEAT: "heat",
    Mode.TEMP_AI: "temp_ai",
    Mode.ADVANCED: "advanced",
}
MODE_BY_OPTION: dict[str, Mode] = {v: k for k, v in MODE_OPTIONS.items()}

# modeAndSettingIdStr lists the ids of the fields a PUT changes.
FIELD_AT_TYPE = 16
FIELD_ON_SPEED = 18
FIELD_POWER = 22  # powerState; same id as AC Infinity's room-to-room fans use

SERVICE_SEND_RAW_COMMAND = "send_raw_command"
ATTR_PARAMS = "params"
ATTR_FIELD_IDS = "field_ids"
