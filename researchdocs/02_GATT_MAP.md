# CYC X1 Pro Gen4 — Complete GATT Map
**Date:** 2026-05-28  
**Source:** Local probe via `gatttool` + BlueZ `bluetoothctl`  
**Target:** `CYCMOTOR` @ `<CYCMOTOR_ADDRESS>` (random address)

---

## GATT Database Summary

| Handle | Group End | UUID | Type |
|---|---|---|---|
| `0x0001` | `0x0009` | `00001800-0000-1000-8000-00805f9b34fb` | GAP Service |
| `0x000a` | `0x000a` | `00001801-0000-1000-8000-00805f9b34fb` | GATT Service |
| `0x000b` | `0xffff` | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | Nordic UART Service |

---

## GAP Service — Handle 0x0001

### Device Name Characteristic
| Field | Value |
|---|---|
| Characteristic Handle | `0x0002` |
| Value Handle | `0x0003` |
| Properties | `0x0a` (Read + Notify) |
| UUID | `00002a00-0000-1000-8000-00805f9b34fb` |
| **Read Value** | `43 59 43 4d 4f 54 4f 52` = `CYCMOTOR` |

### Appearance Characteristic
| Field | Value |
|---|---|
| Characteristic Handle | `0x0004` |
| Value Handle | `0x0005` |
| Properties | `0x02` (Read) |
| UUID | `00002a01-0000-1000-8000-00805f9b34fb` |
| **Read Value** | `00 00` = `0x0000` (unknown category) |

### Peripheral Preferred Connection Parameters Characteristic
| Field | Value |
|---|---|
| Characteristic Handle | `0x0006` |
| Value Handle | `0x0007` |
| Properties | `0x02` (Read) |
| UUID | `00002a04-0000-1000-8000-00805f9b34fb` |
| **Read Value** | `06 00 10 00 00 00 90 01` |

Decoded:
| Field | Value |
|---|---|
| Min Connection Interval | `0x0006` × 1.25ms = **7.5 ms** |
| Max Connection Interval | `0x0010` × 1.25ms = **20 ms** |
| Peripheral Latency | `0x0000` = **0 latency** |
| Supervision Timeout | `0x0190` × 10ms = **4000 ms** |

### Central Address Resolution Characteristic
| Field | Value |
|---|---|
| Characteristic Handle | `0x0008` |
| Value Handle | `0x0009` |
| Properties | `0x02` (Read) |
| UUID | `00002aa6-0000-1000-8000-00805f9b34fb` |
| **Read Value** | `01` = supported |

---

## GATT Service (Generic Attribute Profile) — Handle 0x000a

| Handle | UUID | Notes |
|---|---|---|
| `0x000a` | `00001801-...` | GATT Service declaration |

No additional characteristics in this service.

---

## Nordic UART Service (NUS) — Handle 0x000b

| Field | Value |
|---|---|
| UUID | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` |
| Group end handle | `0xffff` (variable, extends to all remaining handles) |

### NUS TX Characteristic (Host → Device)
| Field | Value |
|---|---|
| Characteristic Handle | `0x000c` |
| Value Handle | `0x000d` |
| Properties | `0x0c` (Write + Write Without Response) |
| UUID | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` |
| BlueZ Flags | `"write-without-response" "write"` |
| ATT MTU | **247 bytes** |
| **Read Value** | *empty* (write-only, no read value) |

### NUS RX Characteristic (Device → Host)
| Field | Value |
|---|---|
| Characteristic Handle | `0x000e` |
| Value Handle | `0x000f` |
| Properties | `0x10` (Notify) |
| UUID | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` |
| BlueZ Flags | `"notify"` |
| ATT MTU | **247 bytes** |
| **Read Value** | *empty* (notifications only, no read value) |

### Client Characteristic Configuration Descriptor (CCC)
| Field | Value |
|---|---|
| Descriptor Handle | `0x0010` |
| UUID | `00002902-0000-1000-8000-00805f9b34fb` |
| **Read Value** | `00 00` (notifications disabled) |
| **To enable notifications** | Write `01 00` |
| **To disable notifications** | Write `00 00` |

---

## BLE Connection Parameters

| Parameter | Value |
|---|---|
| MTU | 247 bytes |
| Connection role | Unknown (device is peripheral) |
| Connection state | Unconnected in probe |
| PHY | Not confirmed, likely 1M or 2M |

---

## Protocol Implications

### No Standard Telemetry Means Custom Protocol

The complete absence of standard BLE telemetry services (Battery Service, Heart Rate Service, Cycling Speed and Cadence Service, etc.) tells us:

1. **All motor state is proprietary** — no Bluetooth SIG standardized data
2. **Nordic UART is the entire API** — all read/write happens through NUS
3. **Application layer, not ATT layer** — the protocol commands are embedded in raw NUS TX/RX payloads, not in GATT characteristic values
4. **Notifications are the primary push channel** — motor pushes telemetry as BLE notifications from NUS RX; no polling mechanism is provided by the GATT design

### MTU Implication

With MTU 247, the maximum ATT payload per packet is **244 bytes** (247 - 3 bytes ATT header). This is generous — most e-bike command frames are 8–20 bytes, so they fit in a single BLE packet with room to spare.

### CCC Descriptor

The `0x0010` descriptor must be written with `01 00` (little-endian for `0x0001`, the "Notifications enabled" bit) before any telemetry can be received. This is a standard GATT subscription action — not a motor command. The motor should respond to the CCC write with a Write Response, then begin sending notifications.

---

*Last updated: 2026-05-28 by Renarac (OpenClaw agent)*
