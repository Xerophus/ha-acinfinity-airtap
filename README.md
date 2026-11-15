# AC Infinity AIRTAP for Home Assistant

Controls AC Infinity **AIRTAP** register booster fans (tested on a T6, devType 48,
firmware 2.0.29) through the AC Infinity cloud. Other AC Infinity controllers on the
same account are ignored, so this can run alongside
[dalinicus/homeassistant-acinfinity](https://github.com/dalinicus/homeassistant-acinfinity).

## Install (HACS)

1. HACS → ⋮ → **Custom repositories** → add this repository's URL, type **Integration**.
2. Install **AC Infinity AIRTAP** and restart Home Assistant.
3. Settings → Devices & services → **Add integration** → *AC Infinity AIRTAP*, and sign in
   with the AC Infinity app account.

## Entities (per fan)

| Entity | What it does |
|---|---|
| `fan.<name>` | On/off is the unit's power, the same as the app's power button: off fully powers the unit down, and on resumes its saved mode and level. Speed has 10 levels and shows the real level in every mode. Setting a speed switches to **Fan** mode, powering on first if needed. 0 % powers off. |
| `select.<name>_mode` | Fan, Cool, Heat, Temp AI. *Advanced* (schedules made in the app) is shown but can't be selected. Switching to Cool/Heat/Temp AI keeps that mode's saved settings. |
| `sensor.<name>_temperature` | Room temperature from the fan's sensor. |
| `sensor.<name>_fan_level` | Current level, 0–10. |
| `sensor.<name>_cool_trigger_temperature`, `_heat_trigger_temperature`, `_temp_ai_deviation` | Each mode's saved setting (diagnostic, read-only for now). |
| `binary_sensor.<name>_vent` | `isWindSteering`. On a T4 it follows the louvers. On a T6 with the vent set to *Open* it stays on. |
| `binary_sensor.<name>_connectivity` | Whether the cloud can reach the fan. |

A command takes a few seconds to reach the fan, and the cloud can take ~20 s to report
it. Until it does (up to 45 s), the entities show what was just written.

### Advanced: `ac_infinity_airtap.send_raw_command`

Sends a `PUT /api/dev/modeAndSetting` as-is, for trying settings this integration doesn't
write yet. `devId` and `port=0` are added. `field_ids` is the `modeAndSettingIdStr` list
naming the changed fields (16 = mode/`atType`, 18 = Fan mode level/`onSpead`).

```yaml
action: ac_infinity_airtap.send_raw_command
data:
  device_id: <AIRTAP device id>
  params: {atType: 0, onSpead: 3}
  field_ids: [16, 18]
```

The integration's **Download diagnostics** shows the raw payloads, with MAC and account
details redacted.

## API notes

- Modes (`atType`): 0 Fan, 1 Cool, 2 Heat, 3 Temp AI (default), 15 Advanced. These are
  **not** the UIS controllers' numbers.
- The fan level is written as `onSpead` (the API's spelling). `onSpeed` is accepted but ignored.
- Power is `powerState` (1/0) with `modeAndSettingIdStr=[22]`. While the unit is off,
  level and mode writes are saved but don't start it. Verified on a T6 2026-11-14.
- Writes need the `minversion: 3.5` header and the minimal parameter set. AIRTAPs reject
  the full payloads used for controllers.

These came from the testing in
[dalinicus/homeassistant-acinfinity#154](https://github.com/dalinicus/homeassistant-acinfinity/pull/154)
(thanks to @jasonarends and @9qg5f5vy68-crypto).

## Not yet

- Writing the Cool/Heat triggers, the Temp AI deviation and the vent behaviour. Their
  `modeAndSettingIdStr` field ids aren't known yet.
- Cloud only: no control while AC Infinity's servers or the internet are down. (The fan's
  Matter interface pairs but ignores commands on firmware 2.1.)

## Development

```sh
pip install pytest-homeassistant-custom-component
pytest
```
