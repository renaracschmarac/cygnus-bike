# Nordic UART Service (NUS) — Reference Architecture
**Date:** 2026-05-28  
**Purpose:** Context for understanding how NUS works as a BLE transport, and implications for the CYC protocol

---

## 1. What is NUS?

The **Nordic UART Service** is a proprietary GATT-based UART bridge over Bluetooth Low Energy, originally defined by Nordic Semiconductor for their nRF SoC line (nRF52832, nRF52840, etc.).

It is not part of the Bluetooth SIG standard — it is a **vendor-specific custom service** maintained by Nordic Semiconductor.

**Key use case:** Rapid prototyping of BLE devices that need to tunnel raw serial (UART) data over BLE without designing a custom GATT service with multiple characteristics.

---

## 2. NUS Service Definition

| Element | UUID | Description |
|---|---|---|
| Service UUID | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | Nordic UART Service |
| TX (Write) Characteristic | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | Host writes commands here |
| RX (Notify) Characteristic | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | Peripheral sends responses here |
| CCC Descriptor | `00002902-0000-1000-8000-00805f9b34fb` | Used to subscribe to RX notifications |

The nomenclature can be confusing:
- **TX (host→peripheral):** Central (phone/host) writes to it → data goes OUT of the central into the peripheral
- **RX (peripheral→host):** Peripheral notifies it → data comes IN to the central from the peripheral

Some vendors call TX "UART RX" because from the peripheral's perspective, the write is RX (it receives data). The CYC motor documentation may use either convention.

---

## 3. Data Flow

```
┌──────────────┐   Write Request (TX char)   ┌──────────────┐
│  Phone/Host  │ ──────────────────────────→ │  CYC Motor   │
│ (CYC App)    │ ←─────────────────────────── │ (Peripheral) │
└──────────────┘   Notification (RX char)     └──────────────┘
```

- The BLE stack handles acknowledgment, retransmission, and flow control
- Application code writes raw bytes to TX characteristic
- Application code reads raw bytes from RX notifications
- **No framing is enforced by the BLE layer** — any byte sequence is valid

---

## 4. BLE Stack Constraints on NUS

### 4.1 MTU (Maximum Transmission Unit)

The MTU defines the largest data packet that can be sent in a single BLE PDU. With typical MTU of 247 (common for iOS and modern Android):

| MTU | ATT Header | Max_payload | Notes |
|---|---|---|---|
| 247 | 3 bytes | **244 bytes** | Standard for modern BLE |
| 185 | 3 bytes | 182 bytes | Older/strict stacks |
| 23 | 3 bytes | **20 bytes** | BLE 4.0 minimum |

**The CYC device advertises MTU 247** (confirmed from BlueZ D-Bus data), so up to 244 bytes per write.

### 4.2 Write Types

NUS TX has two write types available:

| Write Type | Properties Flag | Behavior |
|---|---|---|
| **Write** | `0x04` | Requires response from peripheral; guaranteed delivery |
| **Write Without Response** | `0x08` | No acknowledgment; faster but unconfirmed delivery |

The CYC NUS TX characteristic is marked with properties `0x0c` = `0x04 | 0x08` (both). Typical implementations use Write Without Response for streaming data, and a regular Write for commands requiring confirmation.

### 4.3 Notifications

The NUS RX characteristic uses **notifications** (not indications):
- Notifications are unacknowledged at the ATT layer (faster, no confirmation round-trip)
- If a notification is lost in transit, it is **not retransmitted**
- For critical data, the application must implement its own acknowledgment/resend logic at the application layer

---

## 5. What NUS Does NOT Provide

NUS provides only a **raw byte transport**. It does **not** include:

- **Framing** — no start/end markers, no packet boundaries
- **Addressing** — no source/destination IDs within frames
- **Sequence numbers** — no packet ordering or deduplication
- **Checksums** — no CRC/XOR integrity check at the BLE layer
- **Flow control** — no backpressure mechanism; slow readers lose data
- **Session management** — no pairing/bonding handled by NUS itself

All of these must be implemented in the **application layer protocol** on top of NUS.

---

## 6. Common Application Layer Patterns on NUS

Since NUS is a raw pipe, most devices implement their own framing on top. Typical patterns:

### 6.1 Signature + Length + Command + Payload + CRC

```
[signature_2bytes] [length_1byte] [cmd_type_1byte] [payload_Nbytes] [crc_?] 
```

- **Signature:** Fixed bytes to identify valid frame start (e.g., ASCII "gt", "YY", 0x55 0xAA)
- **Length:** Number of bytes in payload (may or may not include header/crc)
- **Command type:** Identifies the operation (e.g., 0x01 = read, 0x02 = write)
- **Payload:** Variable-length data
- **CRC:** Optional checksum byte or word

**Reference:** This matches the `obike` protocol framing exactly.

### 6.2 Type-Length-Value (TLV)

```
[type_1byte] [length_1byte] [value_Nbytes]
```

Often chained within a frame. Used where multiple independent fields need to be multiplexed.

### 6.3 MODBUS-like

```
[slave_id] [function] [address_hi] [address_lo] [data...] [crc16]
```

- Slave ID: device address
- Function: read (0x03) or write (0x10)
- Address + data: register-based access
- CRC16: Modbus CRC16

**Reference:** ASI BAC controllers expose MODBUS over wired UART; if CYC reused register addresses, similar packets over NUS would be 8–20 bytes.

### 6.4 Simple Request-Response

```
[cmd_type] [param_bytes...]

Response:
[cmd_type] [status] [response_bytes...]
```

Where responses always mirror the command type in the first byte. Simple and common.

---

## 7. Implications for the CYC Motor Protocol

### What we know:

1. **NUS is a raw byte pipe** — commands and responses are raw binary, not structured GATT payloads
2. **MTU is 247 bytes** — generous size; commands will fit in single BLE packets
3. **Both write types available** — write-without-response is likely used for streaming commands; regular writes for confirmed operations
4. **Notifications are the push channel** — motor telemetry arrives as BLE notifications, not reads
5. **Notifications are disabled by default** — CCC must be written to enable them

### What this means for protocol discovery:

- **Protocol is application-layer** — the CYC app and motor agree on a custom binary protocol that runs over NUS
- **We must capture real traffic** — without understanding the packet format, we cannot meaningfully generate commands
- **Framing patterns to look for:**
  - Two-byte signature at frame start
  - Length byte(s) indicating payload size
  - Command type byte(s) identifying the operation
  - Checksums (XOR, CRC8, or CRC16) at frame end
  - Request → Response correlation (same command type in replies)

### What to capture:

1. **Enable notifications first** — write `01 00` to `0x0010`, then observe motor for any spontaneous data
2. **Capture app interaction traffic** — use nRF sniffer or Android HCI snoop while operating the CYC app
3. **Look for periodic telemetry** — many e-bike motors send a heartbeat/status broadcast every 0.5–2 seconds
4. **Trigger app actions and correlate** — changing assist level, throttle, viewing dashboard → identify which notifications change accordingly

---

## 8. Reference Implementations Using NUS

| Project | Link | Notes |
|---|---|---|
| Nordic SDK peripheral_nus sample | https://docs.zephyrproject.org/latest/samples/bluetooth/peripheral_nus/README.html | Zephyr implementation |
| pybricksdev NUS module | https://docs.pybricks.com/get倭急projects/pybricksdev/en/latest/api/ble/nus.html | Python NUS client library |
| Arduino BLE Serial (senseshift) | https://deepwiki.com/senseshift/arduino-ble-serial/ | NUS serial bridge over Arduino |
| ESPHome NUS component | https://esphome.io/components/ble_nus/ | ESP32 NUS integration |
| NuS-NimBLE-Serial (Arduino) | https://docs.arduino.cc/libraries/nus-nimble-serial/ | Arduino NUS library |

---

*Last updated: 2026-05-28 by Renarac (OpenClaw agent)*
