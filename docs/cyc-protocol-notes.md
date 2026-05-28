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
