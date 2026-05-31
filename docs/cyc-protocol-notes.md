# CYC Telemetry Protocol Notes

The CYC Ride Control APK includes Flutter assets that define the telemetry payload layouts:

- `assets/json/cyc_uart.json`
- `assets/json/xSeries_uart.json`
- `assets/json/ebmx_uart.json`

These layouts confirm that dashboard telemetry is a VESC-style values payload carried over Nordic UART Service.

## BLE Transport

- Service: `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
- Host-to-motor write characteristic: `6e400002-b5a3-f393-e0a9-e50e24dcca9e`, value handle `0x000d`
- Motor-to-host notify characteristic: `6e400003-b5a3-f393-e0a9-e50e24dcca9e`, value handle `0x000f`
- Notification CCC descriptor: handle `0x0010`

Do not publish real BLE addresses. Discover by device name `CYCMOTOR` and keep the selected address in the ignored `.cygnus-bike.local.json` file.

## Packet Framing

The app contains `Uint8ListExtension|crc16`, `parseRxFrame`, `isCycRxData`, and VESC command strings. Use standard VESC packet framing:

```text
short: 02 <payload_len> <payload...> <crc_hi> <crc_lo> 03
long:  03 <payload_len_hi> <payload_len_lo> <payload...> <crc_hi> <crc_lo> 03
```

CRC is VESC CRC16 over the payload bytes. This is the VESC/CCITT table implementation with initial value `0`, not Modbus RTU CRC byte order.

## Telemetry Request

The read-only telemetry request is `COMM_GET_VALUES`, command `0x04` in common VESC firmware:

```text
payload: 04
packet:  02 01 04 40 84 03
```

This is confirmed by the Android CYC Ride Control capture:

```text
ATT Write Command to handle 0x000d: 02 01 04 ...
ATT Notification from handle 0x000f: 02 57 04 ...
```

The bugreport-contained `btsnooz_hci.log` only kept the first bytes of each ACL packet, but those bytes are enough to prove:

- The app uses ATT Write Command (`0x52`) to the NUS write handle.
- The request payload starts as a VESC short packet with length `0x01` and command `0x04`.
- The response starts as a VESC short packet with payload length `0x57` = 87 bytes.
- The first response payload byte is `0x04`, followed by 86 telemetry bytes, matching `cyc_uart.json`.

The reader in `scripts/cyc_telemetry.py` sends only this request, subscribes to notifications, validates VESC frames, and decodes values using the APK-provided JSON layouts.

## Telemetry Layouts

`cyc_uart.json` is 86 bytes and includes:

- FET and motor temperature
- motor/input current
- duty cycle
- RPM
- input voltage
- battery consumption / watt-hours
- cadence, throttle, torque
- fault code
- odometer
- speed
- mode and assist level

`xSeries_uart.json` is 156 bytes and extends that with:

- additional rails and PCB temperatures
- hall states
- throttle and regen percentages
- wheelie angle
- battery percentage
- power percentage
- phase-current/torque percentage

The decoder auto-selects the largest layout that fits the received payload. If the VESC command byte is present as the first payload byte, it is skipped before applying the JSON offsets.

For live reads, let the decoder select the layout from the packet length:

```sh
scripts/cyc_telemetry.py --all-fields --raw --count 1
```

On the tested CYC X1 Pro Gen4/X12 controller, `COMM_GET_VALUES` returns an 87-byte VESC payload: command byte `0x04` plus 86 bytes matching `cyc_uart.json`. The APK version `2.5.44` still contains the extended `xSeries_uart.json` asset, but this controller did not return the 156-byte extended block during live testing. Use `--layout xSeries_uart` only when packet length confirms the extended payload is actually being emitted.

The Android CYC Ride Control app was also tested against the same controller on
2026-05-31. While connected to the dashboard it repeatedly sent only
`COMM_GET_VALUES` (`02 01 04 ...`) and received the same 87-byte response. After
opening Settings > General, the app additionally sent two read-only config
requests:

```text
COMM_GET_APPCONF: 02 01 11 02 10 03 -> payload_len=477, response command 0x11
COMM_GET_MCCONF: 02 01 0e e1 ce 03 -> payload_len=485, response command 0x0e
```

Those config payloads match the APK layouts `cyc_app_0503.json` and
`cyc_motor_0503.json` exactly after stripping the leading response command byte.
The transport/status fields decoded from the live controller were:

| Field | Value | Layout |
| --- | ---: | --- |
| `controller_id` | 62 | `cyc_app_0503.json` |
| `send_can_status` | `0 (CAN_STATUS_DISABLED)` | `cyc_app_0503.json` |
| `send_can_status_rate_hz` | 50 | `cyc_app_0503.json` |
| `can_baud_rate` | `2 (CAN_BAUD_500K)` | `cyc_app_0503.json` |
| `permanent_uart_enabled` | `1 (enabled)` | `cyc_app_0503.json` |
| `can_mode` | `0 (CAN_MODE_VESC)` | `cyc_app_0503.json` |
| `app_uart_baudrate` | 9600 | `cyc_app_0503.json` |
| `comm_mode` | `0 (COMM_MODE_INTEGRATE)` | `cyc_motor_0503.json` |
| `bms.fwd_can_mode` | `0 (BMS_FWD_CAN_MODE_DISABLED)` | `cyc_motor_0503.json` |

`scripts/cyc_telemetry.py` decodes these known `0x11` and `0x0e` config fields
and prints enum labels automatically:

```sh
scripts/cyc_telemetry.py --command 0x11 --packet-count 1
scripts/cyc_telemetry.py --command 0x0e --packet-count 1
```

None of the observed app commands or decoded config fields select
`xSeries_uart.json` for BLE dashboard telemetry. The closest flag is
`send_can_status`, but it is a CAN status broadcast setting, not evidence of a
larger NUS `COMM_GET_VALUES` response. Do not set config values without an
explicit write plan and backup, because that requires `COMM_SET_APPCONF` or
`COMM_SET_MCCONF`.

`xSeries_uart.json` contains 52 fields and spans byte offsets `0` through `155`:

| Key | Offset | Length | Scale | Type |
| --- | ---: | ---: | ---: | --- |
| `temp_fet_filtered` | 0 | 2 | 10 | `int` |
| `temp_motor_filtered` | 2 | 2 | 10 | `int` |
| `reset_avg_motor_current` | 4 | 4 | 100 | `int` |
| `reset_avg_input_current` | 8 | 4 | 100 | `int` |
| `reset_avg_id` | 12 | 4 | 100 | `int` |
| `reset_avg_iq` | 16 | 4 | 100 | `int` |
| `duty cycle` | 20 | 2 | 1000 | `int` |
| `rpm` | 22 | 4 | 1 | `int` |
| `Input_V` | 26 | 2 | 10 | `int` |
| `Battery Consumption` | 28 | 4 | 10000 | `int` |
| `Total Trip Time` | 32 | 4 | 1 | `uint` |
| `Total Watt Hour Draw` | 36 | 4 | 10000 | `int` |
| `6v Analog 3` | 40 | 4 | 100 | `int` |
| `Throttle` | 44 | 4 | 100 | `int` |
| `Regen` | 48 | 4 | 100 | `int` |
| `fault` | 52 | 1 | 1 | `uint` |
| `Digital_Inputs` | 53 | 1 | 1 | `uint` |
| `current_controller_id` | 54 | 1 | 1 | `uint` |
| `NTC_TEMP_MOS1` | 55 | 2 | 10 | `int` |
| `NTC_TEMP_MOS2` | 57 | 2 | 10 | `int` |
| `NTC_TEMP_MOS3` | 59 | 2 | 10 | `int` |
| `reset_avg_vd` | 61 | 4 | 1000 | `int` |
| `reset_avg_vq` | 65 | 4 | 1000 | `int` |
| `ODO` | 72 | 4 | 1 | `uint` |
| `6v Analog 4` | 76 | 4 | 100 | `int` |
| `Speed` | 80 | 4 | 100 | `int` |
| `Race/Street Mode` | 84 | 1 | 1 | `uint` |
| `Assist Level` | 85 | 1 | 1 | `int` |
| `voltage36v` | 86 | 4 | 10000 | `int` |
| `voltage5v5a` | 90 | 4 | 10000 | `int` |
| `temp36v` | 94 | 4 | 10000 | `int` |
| `temp5v5a` | 98 | 4 | 10000 | `int` |
| `voltage5vIn` | 102 | 4 | 10000 | `int` |
| `voltage5vExt` | 106 | 4 | 10000 | `int` |
| `voltage14v` | 110 | 4 | 10000 | `int` |
| `tempPcb` | 114 | 4 | 10000 | `int` |
| `tempBp` | 118 | 4 | 10000 | `int` |
| `io8` | 122 | 2 | 1 | `uint` |
| `ioBts` | 124 | 1 | 1 | `uint` |
| `currentBp` | 125 | 4 | 10000 | `int` |
| `hallA` | 129 | 1 | 1 | `uint` |
| `hallB` | 130 | 1 | 1 | `uint` |
| `hallCi` | 131 | 1 | 1 | `uint` |
| `pwm` | 132 | 1 | 1 | `uint` |
| `button` | 133 | 1 | 1 | `uint` |
| `throttle1` | 134 | 4 | 100 | `int` |
| `batteryPercentage` | 138 | 2 | 1 | `uint` |
| `throttleInPercentage` | 140 | 4 | 1 | `int` |
| `regenInPercentage` | 144 | 4 | 1 | `int` |
| `wheelieModeAngle` | 148 | 4 | 100 | `int` |
| `powerPercentage` | 152 | 2 | 1 | `uint` |
| `phaseCurrentOrTorquePercentage` | 154 | 2 | 1 | `int` |

## Current UI Mapping

Captured payloads from the example motor currently decode as:

- Controller temperature: `temp_fet_filtered`, Celsius, display as Fahrenheit when the app is in imperial units.
- Motor temperature: `temp_motor_filtered`, Celsius, display as Fahrenheit when the app is in imperial units.
- Battery voltage: `Input_V`, volts.
- Speed: `Speed`, already scaled by `100`; with app units set to MPH, display as MPH.
- Odometer: `ODO`, raw unsigned integer at telemetry offset `72`; current evidence indicates this is kilometers.

Example:

```text
01 09 / 10 = 26.5 C = 79.7 F controller
00 eb / 10 = 23.5 C = 74.3 F motor
02 29 / 10 = 55.3 V battery
ODO = 48 km = 29.8 mi
Speed = 0.00 mph
```

The `ODO` unit was correlated against the CYC app showing about 30 miles on a recently reset odometer. `48 km * 0.621371 = 29.8 mi`, so display `ODO` as kilometers internally and convert to miles in imperial UI.
