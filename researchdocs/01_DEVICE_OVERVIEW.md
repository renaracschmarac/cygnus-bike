# CYC X1 Pro Gen4 — BLE Protocol Research Dossier
**Date:** 2026-05-27  
**Status:** Discovery Phase — Protocol Unknown  
**Target:** CYC X1 Pro Gen4 mid-drive motor, BLE name `CYCMOTOR`, MAC `<CYCMOTOR_ADDRESS>`

---

## 1. Device Overview

### 1.1 Hardware Context

- **Motor:** CYC X1 Pro Gen 4 mid-driveconversion kit
- **Controller:** X12 Controller (successor to X6, compatible with Gen 2/3/4 motors)
- **Supported torque sensors:** Gen 2 and Gen 3 torque sensors
- **Nominal voltage:** 36–72V
- **Peak phase current:** 180A
- **Peak battery current:** 100A
- **Waterproof rating:** IP66
- **Connectivity:** Bluetooth LE (mobile app), speed sensor (Bluetooth module embedded in speed sensor)
- **Official app:** CYC Ride Control (Android/iOS)

### 1.2 BLE Identity (Confirmed from local probe)

| Property | Value |
|---|---|
| BLE Name | `CYCMOTOR` |
| MAC Address | `<CYCMOTOR_ADDRESS>` |
| Address Type | Random |
| Security | No pairing/bonding required for GATT discovery |

---

## 2. GATT Structure (Confirmed Locally)

### 2.1 Services

| Handle Range | UUID | Name |
|---|---|---|
| `0x0001`–`0x0009` | `00001800-0000-1000-8000-00805f9b34fb` | Generic Access Profile (GAP) |
| `0x000a` | `00001801-0000-1000-8000-00805f9b34fb` | Generic Attribute Profile (GATT) |
| `0x000b`–`0xffff` | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | **Nordic UART Service (NUS)** |

### 2.2 GAP Characteristics

| Char Handle | Value Handle | Properties | UUID | Description | Raw Value |
|---|---|---|---|---|---|
| `0x0002` | `0x0003` | `0x0a` (read+notify) | `00002a00-...` | Device Name | `CYCMOTOR` |
| `0x0004` | `0x0005` | `0x02` (read) | `00002a01-...` | Appearance | `0x0000` |
| `0x0006` | `0x0007` | `0x02` (read) | `00002a04-...` | Peripheral Preferred Connection Parameters | Min 7.5ms, Max 20ms, Latency 0, Timeout 4000ms |
| `0x0008` | `0x0009` | `0x02` (read) | `00002aa6-...` | Central Address Resolution | `0x01` (supported) |

### 2.3 Nordic UART Service (NUS) Characteristics

| Char Handle | Value Handle | Properties | UUID | Description |
|---|---|---|---|---|
| `0x000c` | `0x000d` | `0x0c` (write+write-without-response) | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | NUS TX (host→device) — Write only |
| `0x000e` | `0x000f` | `0x10` (notify) | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | NUS RX (device→host) — Notifications only |
| — | `0x0010` | CCC descriptor | `00002902-0000-1000-8000-00805f9b34fb` | Client Characteristic Configuration (notify enable) |

**Effective MTU:** 247 bytes (confirmed via BlueZ D-Bus introspection)

### 2.4 Key Observations

1. **No telemetry characteristics** — standard GAP/GATT characteristics expose nothing useful (Device Name read returns `CYCMOTOR`, other reads are zeros or empty values)
2. **All motor communication goes through NUS** — the entire command/telemetry protocol runs over the Nordic UART Service as a raw byte pipe
3. **No read characteristic for motor data** — motor state is sent exclusively as BLE notifications from the NUS RX characteristic
4. **Notifications must be enabled** — CCC descriptor at `0x0010` must be written with `01 00` to subscribe to notifications

---

## 3. Nordic UART Service (NUS) — Reference Architecture

The NUS is a **raw byte pipe**, not a structured telemetry protocol. It emulates a UART bridge over BLE:

- **Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
- **TX (Host→Device) UUID:** `6e400002-b5a3-f393-e0a9-e50e24dcca9e` (write, write-without-response)
- **RX (Device→Host) UUID:** `6e400003-b5a3-f393-e0a9-e50e24dcca9e` (notify)

The Nordic Semiconductor reference implementation:
- Treats all data as **UTF-8 encoded text** (default), but accepts **binary** — e-bike protocols typically use binary frames
- Uses **no framing/checksum at the BLE layer** — any framing is application-defined
- Notifications are sent asynchronously by the peripheral whenever it has data
- Maximum payload per BLE packet: **MTU - 3 bytes** (244 bytes with MTU 247)

### Important for CYC Protocol

Since NUS is a raw pipe, the CYC motor controller is free to implement **any custom framing** on top of it. The protocol command bytes below are sent as raw binary writes to the NUS TX characteristic and responses come back as notifications on the NUS RX characteristic.

---

## 4. Known Protocol Patterns from Related Devices

### 4.1 Reference: oBike BLE Protocol (for framing structure insight)

The oBike lock (CC2541 SoC) uses a similar signature-prefixed framing:

```
67 74 [len] [cmd_type] [payload...] [check_byte]
 |    |     |        |           |
 |    |     |        |           +-- XOR of cmd_type + all payload bytes
 |    |     |        +-- Command type (top 2 bits = direction)
 |    |     +-- Payload length bytes (not counting header/trailer)
 |    +-- ASCII 'gt' signature
 +-- ASCII 'gt' signature
```

Pattern:
- **Signature:** 2 bytes (`0x67 0x74` = "gt") header marker
- **Length:** 1 byte (payload only, excludes header/trailer)
- **Command type:** 1 byte (direction encoded in top 2 bits)
- **Payload:** N bytes
- **Check byte:** XOR of cmd_type ^ b[0] ^ b[1] ^ ... ^ b[N-1]

This kind of structure (signature + length + command + payload + checksum) is **extremely common** in BLE e-bike protocols and should be the first hypothesis for the CYC protocol.

### 4.2 Reference: Eq3 Eqiva BLE Protocol (EBNF command framing)

A well-documented BLE protocol with typed binary commands:

```
command = set-date-time | set-temp | set-comfort | ...
set-temp = '41', temperature   # temperature = byte (typically temperature*2)
```

Notable conventions:
- Commands start with a **type code byte**
- Temperatures encoded as `temperature * 2` (allowing 0.5°C resolution)
- Date/time values use BCD or simple byte encoding
- Responses are status notifications with prefixed type bytes

### 4.3 Reference: ASI BAC Controller MODBUS Protocol

The ASI BAC controllers use standard MODBUS over UART. The CYC X12 may share some register definitions with ASI controllers (both are e-bike controllers):

**MODBUS frame format:**
```
[slave_id] [function_code] [address_hi] [address_lo] [count_hi] [count_lo] [CRC_hi] [CRC_lo]
```

**Example: Read register 129 (field weakening):**
```
01 03 00 81 00 01 d4 22
```

**Example: Write register 129:**
```
01 10 00 81 00 01 02 08 00 bf 81
```

**Telemetry block (address 259, 11 registers):**
- Battery voltage, current, SOC
- Motor RPM, speed, temperature, current
- Vehicle speed

This is for the serial/wired MODBUS interface. The CYC BLE protocol may expose similar registers over NUS.

### 4.4 Reference: Cowboy Bike BLE (nRF Connect demo — similar app interface)

Reddit post describes using nRF Connect to send raw hex to a Cowboy bike's Nordic UART:

```
0110000b000102000166eb  (speed limit command)
011001ff0001027fffc2ef  (configuration write)
```

Note the prefix `01` (likely a packet type marker). The Cowboyprotocol is unrelated to CYC but confirms the pattern: e-bike apps send binary command packets prefixed with a type/length marker over NUS.

### 4.5 Reference: Generic e-bike UART protocols

Most e-bike displays (Bafang 500C, C965, SW102) communicate via UART with the controller using simple binary frames:

**Typical telemetry fields:**
- Current speed (2 bytes, 0.1 km/h or mph resolution)
- Battery voltage (2 bytes)
- Battery SOC percentage
- Error codes
- Assist level
- Motor temperature
- Controller temperature

The CYC motor likely uses similar fields but over BLE/NUS rather than wired UART.

---

## 5. BLE Reverse Engineering Methodology

### 5.1 Recommended Capture Workflow

1. **Install nRF Connect for Android** (or iOS)
   - Free, supports BLE GATT operations
   - Allows writing hex values to characteristics and capturing notifications
   
2. **Pair the CYC Ride Control app with the motor**
   - The app will generate the actual protocol frames during normal operation
   - Use the app to change settings, toggle assist levels, read dashboard data

3. **Capture with built-in Android Bluetooth HCI snoop logs**
   ```bash
   # Enable BT snoop on Android:
   # Settings → Developer Options → Enable Bluetooth HCI snoop log
   # Then pair/operate the app, and fetch the log:
   adb shell "cat /sdcard/btsnoop_hci.ip"
   adb pull /sdcard/btsnoop_hci.ip
   ```
   Open in Wireshark, filter by the CYC MAC address `<cycmotor_address>`

4. **Alternatively: Use BLE sniffing hardware** (Nathanor's nRF52840 sniffer)
   - Capture air traffic between the app and motor
   - Gives complete visibility into both directions

5. **Analyze in Wireshark**
   - Filter by `btl2cap.btle and bluetooth.addr == <cycmotor_address>`
   - Look for Write Request packets to `6e400002...` (NUS TX)
   - Look for Notification packets from `6e400003...` (NUS RX)
   - Identify repeated byte patterns → command types

### 5.2 Key Questions to Answer from Capture

1. **What triggers initial notifications?** Does the motor send telemetry periodically or only on request?
2. **Are there fixed-length frames?** Common structures: 8-byte, 16-byte, 20-byte frames
3. **Does a command frame start with a fixed byte/pattern?** (like the oBike `0x67 0x74` signature)
4. **Is there a checksum?** XOR, CRC8, CRC16, or simple SUM?
5. **Which bytes change when you:**
   - Change assist level in the app
   - Accelerate the motor
   - Observe speed increase
   - Observe different battery voltage reading

### 5.3 Safe Initial Probing

**Before any commanding, enable notifications only:**

1. Connect to `CYCMOTOR`
2. Write `01 00` to CCC descriptor at handle `0x0010`
3. Observe any spontaneous notifications from handle `0x000f`
4. **Do not send any command frames until protocol structure is confirmed**

**First safe read hypothesis** — try querying a known-safe address/register (if ASI BAC compatibility):
- Try sending a 2-byte MODBUS-style query for register 0 (manufacturer ID)
- Watch for any response notification

---

## 6. e-Bike Communication Protocols — General Reference

### 6.1 UART vs CAN Bus vs BLE

| Protocol | Media | Typical Use |
|---|---|---|
| UART | Single wire + GND | Basic e-bike displays (Bafang BBS02, C965, SW102), KT controllers |
| CAN Bus | Differential pair | High-end controllers (Kelly, Sevcon, ASI BAC), battery BMS |
| BLE/NUS | Bluetooth LE | Premium systems with mobile app integration (CYC, Cowboy, VanMoof) |
| proprietarily | 2.4GHz transceivers | Some budget systems (direct RF, not BLE) |

### 6.2 Torque Sensor Communication

CYC X1 Pro Gen 4 supports Gen 2 and Gen 3 torque sensors. Torque sensors typically communicate:
- **Via separate signal wire** to the controller (analog voltage proportional to torque)
- **Via BLE*** in some advanced setups (wireless torque sensors)
- The pedal assist (PAS) level is computed by the controller combining cadence + torque

### 6.3 CYC-Specific Notes

- Speed sensor has an **embedded Bluetooth module** — if the speed sensor is disconnected/damaged, the controller BLE connection will not work
- X12 controller supports **real-time monitoring and tuning** via BLE
- All X-series controllers need the speed sensor connected for proper motor operation

---

## 7. Tools & Resources for Protocol Discovery

### 7.1 Software Tools

| Tool | Platform | Purpose |
|---|---|---|
| **nRF Connect** (Nordic Semiconductor) | Android/iOS | BLE GATT exploration, writehex, capture notifications |
| **BLE Explorer** (from Play Store) | Android | Similar to nRF Connect |
| **Wireshark** + **btmon** | Linux | Full BLE HCI capture and protocol analysis |
| **gatttool** (BlueZ) | Linux | Command-line GATT operations |
| **bluetoothctl** (BlueZ) | Linux | Device scanning and connection management |
| **hcitool** / **hcidump** | Linux | Low-level BLE capture |
| **Bettercap** | Linux | BLE reconnaissance and MITM |
| **Adafruit Bluefruit BLE sniffer** | Hardware | Dedicated BLE air capture |

### 7.2 Documentation Resources

| Resource | URL |
|---|---|
| Nordic NUS official documentation | https://docs.nordicsemi.com/bundle/ncs-latest/page/nrf/libraries/bluetooth/services/nus.html |
| CYC Ride Control User Manual | https://www.cycmotor.com/_files/ugd/b1453b_bec86485626448209f0f7c94741e524a.pdf |
| CYC Apps Downloads | https://www.cycmotor.com/cycapps-downloads |
| CYC X12 Controller product page | https://www.cycmotor.com/product-page/x12-controller |
| Reverse Engineering BLE Devices (complete guide) | https://reverse-engineering-ble-devices.readthedocs.io/ |
| ASI BAC MODBUS Protocol document | Endless Sphere forum attachment (ASI_MODBUS_Protocol_Rev_1.21.pdf) |
| BLE Frame specifications (ELA Innovation) | https://elainnovation.com/wp-content/uploads/2020/10/BLE-Frame-specifications-11B-EN.pdf |

### 7.3 Community Resources

| Forum | URL |
|---|---|
| Endless Sphere DIY EV Forum | https://endless-sphere.com/sphere/ |
| Electric Bike Review Forums | https://forums.electricbikereview.com/ |
| CYC MOTOR Support Knowledge Base | https://www.cycmotor-support.com/knowledge/ |
| r/ebikes (Reddit) | https://www.reddit.com/r/ebikes/ |

---

## 8. Known Gaps & Recommended Next Steps

### 8.1 Protocol Status

| Item | Status |
|---|---|
| GATT service discovery | ✅ Complete |
| Handle/UUID map | ✅ Complete |
| NUS identification | ✅ Complete |
| Notification subscription (CCC) | ⚠️ Not yet performed |
| Telemetry capture (real app) | ❌ Not yet done |
| Protocol frame structure | ❌ Unknown |
| Command set identification | ❌ Unknown |
| Checksum algorithm | ❌ Unknown |

### 8.2 Priority Next Steps (for reviewing agent)

1. **Enable notification subscription** — Write `01 00` to handle `0x0010`, observe any spontaneous motor replies
2. **Capture real app traffic** — Use Android HCI snoop log or nRF sniffer while CYC Ride Control app is connected and in use
3. **Identify telemetry packets** — Look for repeating notification frames from the motor (periodic status broadcasts)
4. **Identify command packets** — Isolate Write Request packets from the app → motor, correlate with app actions
5. **Hypothesize frame structure** — Look for signature byte, length field, command type, payload, checksum pattern
6. **Verify with Wireshark** — Filter by device MAC; look at BLE Attribute Protocol PDUs for_HANDLE_VALUE_NOTIFICATION events

### 8.3 Alternative: ASI MODBUS Compatibility

If the X12 controller shares register space with ASI BAC controllers:
- Motor RPM might be at register 0x0103 (259 decimal)
- Battery voltage, current, SOC follow consecutively
- Try a MODBUS-style query: `[01] [03] [01] [03] [00] [0a]` (read 10 registers starting at 259)
- Note: MODBUS is over wired UART; over BLE this would be a raw binary frame — but if the same registers are exposed via NUS, the addressing scheme may be similar

### 8.4 Useful References for Frame Structure

The `obike` protocol as documented in the GitHub repository (`antoinet/obike`) demonstrates the kind of structures to look for:
- 2-byte ASCII signature `"gt"` or similar
- 1-byte payload length
- 1-byte command type (with direction bits in MSB)
- Payloads of variable length
- 1-byte XOR checksum (cmd_type XOR payload[0] XOR ... XOR payload[N-1])

Similar prefixed structures appear in:
- Bafang BBS02/HD UART protocol
- Various KT controller protocols
- oBike lock BLE protocol

---

## 9. File Manifest

```
projects/cygnus-bike/
├── README.md                           # Project overview
├── docs/cycmotor-probe.md             # Local GATT probe findings (2026-05-28)
├── scripts/probe_cycmotor_readonly.sh # Read-only probe script
└── memory/2026-05-28.md              # Session memory

/researchdocs/ (this folder)
├── 01_DEVICE_OVERVIEW.md             # This file
├── 02_GATT_MAP.md                    # Complete GATT structure (from local probe)
├── 03_NUS_REFERENCE.md               # Nordic UART Service reference architecture
├── 04_PROTOCOLS_REFERENCE.md         # Known protocols from related devices
├── 05_REVERSE_ENGINEERING_METHOD.md # Capture/reverse engineering methodology
└── 06_NEXT_STEPS.md                  # Gaps, priorities, hypotheses
```

---

*Last updated: 2026-05-27 by Renarac (OpenClaw agent)*
