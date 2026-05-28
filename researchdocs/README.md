# CYC X1 Pro Gen4 — BLE Protocol Research Dossier

## Index

This folder contains exhaustive documentation gathered from local probe data and web research for the purpose of reverse-engineering the CYC X1 Pro Gen4 motor BLE protocol, with emphasis on the Nordic UART Service (NUS) / GAP+GATT control layer.

---

## File Index

| # | File | Contents |
|---|---|---|
| 1 | `01_DEVICE_OVERVIEW.md` | Device identity, hardware context, GATT structure summary, known gaps |
| 2 | `02_GATT_MAP.md` | Complete GATT attribute table — all handles, UUIDs, properties, raw read values |
| 3 | `03_NUS_REFERENCE.md` | Nordic UART Service reference architecture — data flow, MTU, constraints |
| 4 | `04_PROTOCOLS_REFERENCE.md` | Related BLE protocols: oBike (signature+len+cmd+checksum), Eq3 Eqiva, ASI BAC MODBUS, Cowboy bike |
| 5 | `05_REVERSE_ENGINEERING_METHOD.md` | Step-by-step capture workflow, Wireshark filters, gatttool commands |
| 6 | `06_NEXT_STEPS.md` | Gaps, priority actions, hypotheses, what NOT to do |
| 7 | `07_VESC_PROTOCOL.md` | **CRITICAL — VESC UART protocol reference**: CYC X6/X12 is VESC-based; packet framing (STX/ETX/CRC16), telemetry fields, command codes |

---

## Quick Start for Reviewing Agent

### If you only read one file, read `07_VESC_PROTOCOL.md`

The CYC X6 and X12 controllers are **VESC-based** (confirmed from official CYC product pages). This dramatically changes the primary hypothesis from "completely unknown custom protocol" to "VESC UART protocol over BLE/NUS".

**Key prediction:** BLE notification payloads from the motor should contain VESC packet frames:
```
[0x02] [len] [command_byte] [payload...] [crc16_hi] [crc16_lo] [0x03]
```
Where `0x02` = short packet start, `0x03` = end marker, and CRC16 is MODBUS polynomial `0x8005` computed over payload bytes only.

### First action — Enable Notifications

```bash
# Connect and write CCC to enable notifications
gatttool -b <CYCMOTOR_ADDRESS> -t random --char-write-req -a 0x0010 -v 0100
# Then monitor handle 0x000f for any notifications
hcidump -X
```

### Second action — Look for VESC packet signatures

After enabling notifications, any received payload from `0x000f` that starts with `0x02` or `0x03` is a VESC packet.

### Third action — Capture real app traffic

Use Android Bluetooth HCI snoop log or nRF52840 BLE sniffer while operating the CYC Ride Control app.

---

## Additional Resources

| Resource | Where |
|---|---|
| CYC Ride Control App User Manual (PDF) | `https://www.cycmotor.com/_files/ugd/b1453b_bec86485626448209f0f7c94741e524a.pdf` |
| CYC Apps Downloads | `https://www.cycmotor.com/cycapps-downloads` |
| CYC X12 product page | `https://www.cycmotor.com/product-page/x12-controller` |
| CYC X6 Upgrade Kit (VESC-based confirmed) | `https://www.cycmotor.com/product-page/xc6-controller-upgrade-kit` |
| VESC UART protocol documentation | `https://vesc-project.com/node/121` |
| VESC packet structure post | `https://sharehobby.tistory.com/entry/VESC-packetpayload-structure-on-UART-communication` |
| Reverse Engineering BLE guide | `https://reverse-engineering-ble-devices.readthedocs.io/` |
| oBike protocol (GitHub) | `https://github.com/antoinet/obike` |
| ASI BAC MODBUS forum thread | `https://endless-sphere.com/sphere/threads/programming-asi-bac-8000.102828/` |

---

*Last updated: 2026-05-28 by Renarac (OpenClaw agent)*
