"""API payloads shaped like real AIRTAP T6 responses.

Field names and values follow a T6 (devType 48, fw 2.0.29, hw 3.0) as reported in
dalinicus/homeassistant-acinfinity PR #154 and its review comments.
"""

DEV_ID = "1424979258063709332"
TOKEN = "app-token-123"
HOST = "https://www.acinfinityserver.com"

LOGIN_OK = {"msg": "success.", "code": 200, "data": {"appId": TOKEN}}
LOGIN_BAD = {"msg": "Incorrect password", "code": 10001}
EXPIRED = {"msg": "Login Expired Please login again!", "code": 403}
UPDATE_OK = {"msg": "success.", "code": 200}

AIRTAP_T6 = {
    "devId": DEV_ID,
    "devCode": "WQA13",
    "devName": "Garage Intake",
    "devType": 48,
    "devPortCount": 0,
    "devMacAddr": "E8F60AF1BBAC",
    "online": 1,
    "deviceInfo": {
        "devMacAddr": "E8F60AF1BBAC",
        "devId": int(DEV_ID),
        "temperature": 2560,
        "temperatureF": 7808,
        "humidity": None,
        "unit": 0,
        "speak": 4,
        "curMode": 3,
        "remainTime": 0,
        "online": 1,
        "ports": [],
        "sensors": None,
        "isWindSteering": 1,
        "aiTriggerSta": 1,
        "powerState": 1,
    },
    "firmwareVersion": "2.0.29",
    "hardwareVersion": "3.0",
    "airTap": True,
    "homeDev": True,
    "newFrameworkDevice": True,
}

UIS_CONTROLLER = {
    "devId": "999",
    "devName": "Tent",
    "devType": 11,
    "devPortCount": 4,
    "online": 1,
    "deviceInfo": {"temperature": 2400, "ports": []},
}

DEVICES = {"msg": "success.", "code": 200, "data": [UIS_CONTROLLER, AIRTAP_T6]}

MODE_SETTINGS = {
    "msg": "success.",
    "code": 200,
    "data": {
        "devId": DEV_ID,
        "externalPort": 0,
        "atType": 3,
        "onSpead": 7,
        "offSpead": 0,
        "targetTempF": 80,
        "targetTemp": 27,
        "waterTempHighValueF": 60,
        "waterTempHighValue": 16,
        "devLtf": 3,
        "devLt": 2,
        "isWindSteering": 1,
    },
}
NO_DATA = {"msg": "success.", "code": 200}
