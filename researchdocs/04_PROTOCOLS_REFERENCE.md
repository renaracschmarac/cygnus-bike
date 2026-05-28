# Related BLE E-Bike Protocol Reference
**Date:** 2026-05-28  
**Purpose:** Documented protocol patterns from similar e-bike BLE devices to inform reverse engineering hypotheses

---

## 1. oBike Lock Protocol — Signature + Length + Command + Checksum

**Source:** GitHub `antoinet/obike` — reverse-engineered from lock BLE communication

**Finding:** The oBike lock uses a CC2541 (TI) BLE SoC and communicates via BLE with a mobile app over a proprietary framed protocol.

### 1.1 Frame Structure

```
67 74 [len] [cmd_type] [payload...] [check_byte]
 |    |     |        |            |
 |    |     |        |            +-- XOR: cmd_type ^ payload[0] ^ payload[1] ^ ...
 |    |     |        +-- Command type (top 2 bits encode direction)
 |    |     +-- Payload length in bytes (excludes header and check byte)
 |    +-- ASCII 'gt' signature (2 bytes)
 +-- ASCII 'gt' signature (2 bytes)
```

- **Header signature:** `0x67 0x74` (ASCII "gt") — always the first two bytes
- **Length:** 1 byte — payload length only, excluding header and trailer
- **Command type:** 1 byte — operation; top 2 bits encode message direction
- **Payload:** N bytes — variable-length operation data
- **Check byte:** XOR of command_type XOR all payload bytes

### 1.2 Direction Encoding

Top 2 bits of command_type indicate direction:
| Direction | Mask | Example |
|---|---|---|
| obike → mobile | `0100_0101` | `0x45` |
| mobile → obike | `1000_0101` | `0x85` |

So `cmd_type & 0xC0` distinguishes inbound vs outbound. This is a clever trick to reuse the same command types for both directions.

### 1.3 Sample Frames

**Query lock record (no payload):**
```
67 74 00 86 86
 |  |  |  |  +-- checksum: 0x86 ^ 0x00 = 0x86
 |  |  |  +-- cmd_type: 0x86 (mobile→obike, cmd type 6)
 |  |  +-- length: 0 (no payload)
 |  +-- signature: 'gt'
 +-- signature: 'gt'
```

**Response:**
```
67 74 00 46 46
 |  |  |  |  +-- checksum: 0x46 ^ 0x00 = 0x46
 |  |  |  +-- cmd_type: 0x46 (obike→mobile, cmd type 6)
 |  |  +-- length: 0
 |  +-- signature: 'gt'
 +-- signature: 'gt'
```

**Delete lock record:**
```
67 74 0d 86 59 d5 ff a4 36 33 39 38 37 37 31 33 43 14
 |  |     |  |                                          
 |  |     |  +-- check_byte (XOR of 0x86 and all payload bytes)
 |  |     +-- cmd_type: 0x86 (mobile→obike, cmd type 6)
 |  |     +-- length: 0x0d = 13 bytes payload
 |  +-- signature
 +-- signature
```

### 1.4 Relevance to CYC

The oBike framing schema (signature + length + cmd + payload + XOR checksum) is **extremely common** in embedded BLE protocols and is a strong first hypothesis for the CYC motor protocol. Key things to look for:
1. A fixed 2-byte signature marker at frame start (could be any fixed pair, not necessarily ASCII)
2. A length byte immediately following the signature
3. A command type byte
4. An XOR or CRC checksum at frame end
5. Command type that recurs in responses (mirrored or with direction bit toggled)

---

## 2. Eq3 Eqiva BLE Protocol — Typed Binary Commands (EBNF Reference)

**Source:** https://reverse-engineering-ble-devices.readthedocs.io/

A well-documented radiator valve protocol with typed binary commands. Not an e-bike, but the methodology and framing style are directly applicable.

### 2.1 Protocol Structure

- **BLE service:** Custom UUID `3e135142-654f-9090-134a-a6ff5bb77046`
- **Command characteristic:** UUID `3fa4585a-ce4a-3bad-db4b-b8df8179ea09`, handle `0x0411`
- **Notify characteristic:** UUID `d0e8434d-cd29-0996-af41-6c90f4e0eb2a`, handle `0x0421`

### 2.2 Command Format Examples

```
set-temp = '41', temperature
  → 4124 (set 18°C: temperature = 0x24 = 36 = 18*2)

set-date-time = '03', year, month, day, hour, minutes, seconds
  → 0310 05 19 0B 1B 1C (25/05/2016 11:27:28)
```

### 2.3 Temperature Encoding

Temperature is encoded as `temperature * 2`, allowing 0.5°C resolution in a single byte (0x00–0xFF = 0–127.5°C). This is a common pattern in e-bike protocols for encoding decimal values without floating point:
- `0x24` = 36 = 18.0°C (when divided by 2)
- `0x4B` = 75 = 37.5°C (when divided by 2)

### 2.4 Relevance to CYC

The e-bike equivalent of "set temperature" might be "set assist level" or "set speed limit" — look for single-byte parameters encoded as `value * N` for scaling (e.g., speed in 0.1 km/h units = `value * 10`).

---

## 3. ASI BAC Controller — MODBUS Protocol

**Source:** Endless Sphere DIY EV Forum — programming ASI BAC 8000 thread

The ASI BAC controllers use standard MODBUS over wired serial (RS485/UART). The CYC X12 controller may share register definitions.

### 3.1 MODBUS Frame Format

Standard MODBUS RTU frame:
```
[slave_id] [function_code] [address_hi] [address_lo] [data_hi] [data_lo] [crc_hi] [crc_lo]
```

### 3.2 Read Register Example

Read register 129 (field weakening value):
```
01 03 00 81 00 01 d4 22
 |  |  |  |  |  |  |  +-- CRC16 low byte
 |  |  |  |  |  |  +-- CRC16 high byte
 |  |  |  |  |  +-- Number of registers (1)
 |  |  |  |  +-- Starting register address low byte
 |  |  |  +-- Starting register address high byte
 |  |  +-- Function code: READ (0x03)
 |  +-- Slave ID: 0x01
 +-- Broadcast/all-devices
```

### 3.3 Write Register Example

Write 50% field weakening (value = 2048 = 0x0800):
```
01 10 00 81 00 01 02 08 00 bf 81
 |  |  |  |  |  |  |  |  |  +-- CRC16
 |  |  |  |  |  |  |  |  +-- Value high byte (0x08)
 |  |  |  |  |  |  |  +-- Value low byte (0x00)
 |  |  |  |  |  |  +-- Number of bytes (2)
 |  |  |  |  |  +-- Function code: WRITE MULTIPLE (0x10)
 |  |  |  |  +-- Slave ID
```

### 3.4 Telemetry Block (address 259 / 0x0103)

Reading registers from 259 for 10 consecutive registers returns:
| Register offset | Data |
|---|---|
| 0 (0x103) | Battery voltage |
| 1 | Battery current |
| 2 | Battery SOC % |
| 3 | Motor RPM |
| 4 | Motor current |
| 5 | Motor temperature |
| 6 | Controller temperature |
| 7 | Vehicle speed |
| 8 | Battery power |
| 9 | (reserved) |

### 3.5 Relevance to CYC

If CYC X12 reused the ASI register map (plausible since both are e-bike FOC controllers), then:
- A request of `01 03 01 03 00 0a` (read 10 registers from 259) might work
- Over BLE/NUS, this MODBUS binary frame would be sent as raw bytes to the NUS TX characteristic
- The response would come back as a notification from NUS RX

Note: MODBUS uses CRC16 (CRC-16/MODBUS polynomial). If the checksum algorithm is unknown, CRC16 should be among the first hypotheses to test.

---

## 4. Cowboy Bike — nRF Connect BLE Write Example

**Source:** Reddit post on r/cowboybikes — "Disable speed limit"

This confirms the pattern of using nRF Connect to send raw hex over NUS to e-bike controllers.

**Sample command sent via nRF Connect (Write Request on NUS TX):**
```
0110000b000102000166eb
```

Note the structure:
- `01` — type marker or device ID
- `10` — possibly a command type (write?)
- `000b` — some parameter (low byte)
- `00010200` — 4 bytes of data
- `66eb` — last two bytes could be a checksum

Another example:
```
011001ff0001027fffc2ef
```

This is most likely a configuration write to change a parameter. The `01` prefix is common in e-bike protocols as a packet type marker.

### Relevance to CYC

This example demonstrates that the CYC app almost certainly sends binary frames over NUS prefixed with a type byte (`0x01` or otherwise). Any capture should focus on identifying:
1. What first byte values appear in outgoing commands
2. Whether they match values seen in incoming responses
3. Whether bytes at the end of frames are checksum bytes

---

## 5. Bafang BBS02/HD — UART Protocol Reference

**Note:** Bafang uses wired UART, but the protocol conventions are widely relevant in e-bike reverse engineering.

### 5.1 Typical Bafang UART Frame

Most Bafang displays and controllers use a simple protocol:
- Speed in 0.1 km/h units (e.g., `0x15 0x03` = 78.5 km/h?)
- Battery voltage: 2 bytes, 0.1V resolution
- Error codes: 1 byte
- Assist level: 1 byte (0–5)
- Controller temp: 1 byte, °C

### 5.2 Relevance

Bafang's UART protocol is well-documented online and widely analyzed. Many e-bike controllers follow similar conventions because the underlying needs (speed, voltage, temperature, assist level) are universal.

---

## 6. Common Patterns Across All Protocols

| Pattern | Notes |
|---|---|
| **Two-byte signature prefix** | Helps identify valid frame start; e.g., `0x67 0x74` (oBike), `0x55 0xAA` (common alt) |
| **Length byte** | Immediately after signature; counts payload bytes (may or may not include header/crc) |
| **Command type byte** | Frame function; often mirrored in response with direction bit toggled |
| **Scaling** | Multiply by 2 or 10 for decimal resolution (avoids floating point) |
| **XOR checksum** | `cmd ^ payload[0] ^ ... ^ payload[N-1]` — used in oBike; common in embedded protocols |
| **CRC16 MODBUS** | Polynomial `0x8005` — standard in industrial/MODBUS; used in ASI BAC |
| **Periodic telemetry** | Motors send status every 0.5–2s once notifications are enabled |
| **Request-response pairing** | Response includes same command type as request (often XOR'd with 0x80 for direction) |

---

*Last updated: 2026-05-28 by Renarac (OpenClaw agent)*
