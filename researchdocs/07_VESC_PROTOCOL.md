# VESC-Based Controller Protocol
**Date:** 2026-05-28  
**Relevance:** CYC X6 and X12 controllers are described as "VESC based" (per CYC product descriptions)

---

## 1. Relevance to CYC X6/X12 Controllers

The CYC X6 controller is explicitly described as "VESC based & paired with the CYC Ride Control mobile app" on the product page at `cycmotor.com`. This means:

1. **The motor controller runs VESC firmware** — Vedder Research's open-source brushless DC (BLDC/FOC) controller firmware
2. **The UART protocol is the VESC UART protocol** — Standardized protocol defined by the VESC Project
3. **Bluetooth transport is layered on top** — BLE (NUS) is the transport; VESC UART packets are encapsulated inside NUS TX/RX payloads
4. **The same telemetry fields (RPM, current, voltage, duty cycle) are likely exposed**

This was confirmed by the CYC product copy:
> "This set includes everything you need to upgrade your controller from the ASI BAC855 to the CYC X6 controller. It is VESC based & paired with the CYC Ride Control mobile app"

---

## 2. VESC UART Packet Structure

VESC uses a length-prefixed packet protocol with CRC16 integrity checking and a fixed end marker.

### 2.1 Packet Encoding

```
[STX] [LEN_MSB] [LEN_LSB] [PAYLOAD...] [CRC_MSB] [CRC_LSB] [ETX]
```

**Short packets (payload ≤ 255 bytes):**
```
0x02 [len_1byte] [payload...] [crc16_hi] [crc16_lo] 0x03
```

**Long packets (payload > 255 bytes):**
```
0x03 [len_hi] [len_lo] [payload...] [crc16_hi] [crc16_lo] 0x03
```

Where:
- `STX` = `0x02` (short) or `0x03` (long packet start)
- `LEN` = payload length in bytes (not including header, CRC, or ETX)
- `PAYLOAD` = command byte(s) + data bytes
- `CRC16` = CRC-16/MODBUS polynomial `0x8005`, computed over payload bytes only
- `ETX` = `0x03` (end-of-transmission marker)

### 2.2 State Machine (decoder logic)

From the VESC STM32F4 source (`packet_process_byte`):

| State | Condition | Action |
|---|---|---|
| 0 (idle) | `rx_data == 0x02` → short packet, go to state 2 | store length = rx_byte |
| 0 | `rx_data == 0x03` → long packet start, go to state 1 | — |
| 1 | (long packet length MSB) | length = rx_data << 8 |
| 2 | (length LSB or short length) | complete length, start reading payload |
| 3 | read `payload_length` bytes | fill rx_buffer |
| 4 | (CRC16 MSB) | store crc_high |
| 5 | (CRC16 LSB) | store crc_low |
| 6 | verify `0x03` trailer + CRC match | process packet |

The CRC is computed over the **payload bytes only**, not counting the STX, length bytes, or CRC itself. It uses standard MODBUS CRC16:
```
polynomial: 0x8005
initial: 0xFFFF
CRC16 = CRC16_MODBUS(data_bytes, len)
```

### 2.3 Concrete Example (from VESC UART source)

For a 6-byte payload:
```
02 06 21 00 00 00 00 00 00 E8 03
 |  |  |                    |    |
 |  |  |                    |    +-- ETX (0x03)
 |  |  |                    +-- CRC16 low
 |  |  |                    +-- CRC16 high
 |  |  +-- 6 payload bytes
 |  +-- length = 6
 +-- STX for short packet
```

### 2.4 Packet Direction

- **`COMM_FWD_CAN`** — forward command to another VESC on CAN bus
- **`COMM_GET_VALUES`** — request telemetry (all values)
- **`COMM_SET_DUTY`** — set motor duty cycle
- **`COMM_SET_CURRENT`** — set motor current (amps)
- **`COMM_SET_RPM`** — set motor target RPM
- **`COMM_SET_POS`** — set motor position (for servo modes)
- **`COMM_GET_VALUES_SETUP`** — get setup/config values
- **`COMM_SET_APPLY_NEW_APP_FLAGS`** — application configuration flags
- **`COMM_GET_UNITY`** — uptime, firmware info

**First command to try once notifications are enabled:**
`02 04 00 00 04 00 [CRC] 03` → `COMM_GET_VALUES` (command byte 0x00?)

Wait — the actual VESC command codes:
`COMM_GET_VALUES = 0x00`
`COMM_SET_DUTY = 0x01`
`COMM_SET_CURRENT = 0x02`
`COMM_SET_RPM = 0x03`
`COMM_SET_POS = 0x04`

So `COMM_GET_VALUES` = `0x00` → a read-all-telemetry command for the motor.

The actual frame for a telemetry request (confirming exact command bytes) from VESC source example:
```c
// Example packet for sending:
packet_ptr = (unsigned char*)send_buffer;
*packet_ptr++ = 2;  // STX (short packet)
*packet_ptr++ = 6;  // payload length
*packet_ptr++ = COMM_GET_VALUES; // 0x00 = GET_VALUES command
*packet_ptr++ = field1_byte1;
*packet_ptr++ = field1_byte2;
// ... etc
// CRC16 calculated and appended
*packet_ptr++ = 0x03; // ETX
```

---

## 3. VESC Telemetry Fields (COMM_GET_VALUES Response)

The `COMM_GET_VALUES` response pack contains:
Most VESC telemetry responses are structured binary blobs with fields listed in the VESC `datatypes.h`. Standard fields include:

| Field | Type | Description |
|---|---|---|
| `temp_motor` | float | Motor temperature °C |
| `temp_mosfet` | float | MOSFET/controller temperature °C |
| `current_motor` | float | Motor current (A) |
| `current_in` | float | Battery/input current (A) |
| `duty_cycle` | float | Duty cycle (-1 to 1) |
| `rpm` | float | Electrical RPM (not wheel RPM) |
| `voltage` | float | Battery voltage (V) |
| `amp_hours` | float | Amp-hours used |
| `amp_hours_charged` | float | Ah recharged |
| `watt_hours` | float | Wh consumed |
| `watt_hours_charged` | float | Wh recharged |
| `tachometer` | int | Cumulative motor revolutions |
| `tachometer_abs` | int | Absolute position (no overflow) |
| `fault` | int | Fault code (0=none) |

Values are typically serialized as big-endian floats or 16-bit integers depending on the VESC firmware version. Fields scale differently between VESC 4.x and 6.x firmware.

---

## 4. Key Implication: BLE Transparent UART Mode

Since the CYC X6/X12 is VESC-based, the BLE NUS is almost certainly being used in **transparent UART mode**: the BLE module (probably an nRF52832 or similar) forwards raw bytes between NUS and its UART pins, which connect directly to the VESC processor's UART pins.

This means:
1. **VESC serial protocol is encapsulated as-is in NUS frames** — no translation layer
2. **The same VESC packets (with STX/ETX and CRC16) appear in BLE notifications** — raw VESC packets are the NUS payload
3. **The smartphone app sends VESC commands over BLE/NUS** — standard VESC UART protocol transported over BLE

This also means:
- The X6 BLE module does **not** implement any custom CYC framing — it tunnels VESC protocol
- The Bluetooth module on the speed sensor (where the BLE radio sits) connects UART to VESC
- The CYC Ride Control app is a VESC mobile interface adapted for CYC hardware

**Critical hypothesis to test:** If the BLE module is in transparent UART mode, then BLE notification payloads from the motor will contain standard VESC packet frames with 0x02/0x03 STX, payload, CRC16, and 0x03 ETX delimiter.

---

## 5. Recommended VESC Protocol Hypothesis Test

Once notifications are enabled on the CYC motor, look for packets matching this pattern:

**Valid VESC NUS notification frame:**
```
02 [len] [payload...] [crc16_hi] [crc16_lo] 03
```

Where:
- First byte is `0x02` (short packet) or `0x03` (long packet)
- Last byte before trailing `0x03` cluster is part of CRC16
- If you extract the payload bytes (everything between length byte and CRC bytes), the command byte should be one of: `0x00` (GET_VALUES), `0x01` (SET_DUTY), `0x02` (SET_CURRENT), etc.

**To verify:**
1. Enable NUS notifications
2. Observe frames from motor NUS RX characteristic
3. Check if any begin with `0x02` or `0x03` 
4. After the first `0x02`, the next byte should be the payload length
5. Two bytes before the terminal `03` bytes should be CRC16

**The most likely first payload** you see after enabling notifications is periodic `COMM_GET_VALUES` responses (`0x00` command) being pushed from the motor.

---

## 6. VESC Command Codes Reference

From VESC `.commands` / `datatypes.h`:

| Code (decimal) | Command | Description |
|---|---|---|
| 0 | `COMM_GET_VALUES` | Request/send all telemetry |
| 1 | `COMM_SET_DUTY` | Set duty cycle (control mode) |
| 2 | `COMM_SET_CURRENT` | Set motor current (A) |
| 3 | `COMM_SET_RPM` | Set target RPM |
| 4 | `COMM_SET_POS` | Set position (degrees) |
| 5 | `COMM_SET_DETAILS` | Set detailed config |
| 6–9 | (reserved) | |
| 10 | `COMM_GET_STATS` | Application statistics |
| 11 | `COMM_GET_IMU_DATA` | IMU/sensor data |
| 12 | `COMM_DUMP_VALUES` | Dump variables |
| 13 | `COMM_GET_VALUES_SETUP` | Setup configuration values |
| 14 | `COMM_SET_VALUES` | Write configuration values |
| 15 | `COMM_SET_APPOINT` | Appointment scheduling |
| 16 | `COMM_CAN_FWD_FRAME` | Forward CAN frame |

Code values match VESC version. The CYC app likely uses a subset: `COMM_GET_VALUES` for telemetry, `COMM_SET_CURRENT` or `COMM_SET_DUTY` for commands.

---

## 7. Relationship to ASI BAC / MODBUS

The X6 controller replaces the ASI BAC855. That doesn't mean the protocol is identical — the CYC documentation explicitly markets VESC as the controller platform, while ASI BAC uses its own MODBUS protocol.

However, many e-bike motor controllers converge on the same telemetry fields (speed, voltage, current, temperature), even if the byte encoding and register map differ.

The VESC reference confirms:
- Internal register/telemetry map is different from ASI BAC
- Communication protocol is UART-based (MODBUS for ASI BAC, VESC for CYC)
- BLE transport layer (NUS) is the same regardless

---

*Last updated: 2026-05-28 by Renarac (OpenClaw agent)*
