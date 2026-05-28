# BLE Reverse Engineering — Methodology Guide
**Date:** 2026-05-28  
**Purpose:** Systematic approach for capturing and decoding the CYC motor BLE protocol

---

## 1. Core Principle

The CYC motor exposes **no structured telemetry in GATT characteristic values**. All communication — commands, responses, and telemetry — flows through the Nordic UART Service (NUS) as raw binary bytes.

This means:
- **There is no shortcut** — you cannot read motor state from any GATT handle
- **You must capture real traffic** — either from the official CYC Ride Control app or from controlled probe interactions
- **The protocol is application-layer** — entirely custom and unknown until captured and analyzed

---

## 2. Two Modes of Operation

### 2.1 Passive Capture (Recommended First)

**Goal:** Capture the CYC app's BLE traffic to the motor while performing normal app operations.

**Steps:**
1. Install CYC Ride Control app on an Android device
2. Enable Bluetooth HCI snoop logging on Android:
   - Developer Options → Enable Bluetooth HCI snoop log
   - Some Android versions: `Settings → System → Developer Options → Bluetooth HCI Log`
3. Clear any existing log: `adb shell "rm /sdcard/btsnoop_hci.log"`
4. Pair the motor with the app (forget the motor first to ensure fresh pairing)
5. Use the app normally: change assist levels, view dashboard, adjust settings
6. Pull the log: `adb pull /sdcard/btsnoop_hci.log`
7. Open in Wireshark and filter: `btl2cap.btle and bluetooth.addr == <cycmotor_address>`

**What to look for in Wireshark:**
- `btl2cap.btle.destination == <cycmotor_address>` — packets going to the motor (app → motor commands)
- `btl2cap.btle.source == <cycmotor_address>` — packets coming from the motor (responses/telemetry)

### 2.2 Active Probing (Once Basic Framing is Known)

After capturing enough traffic to hypothesize the frame structure, you can:
1. Send command frames from a Linux box using `gatttool` or a custom Python BLE script
2. Observe responses from the motor
3. Modify individual bytes to identify parameter boundaries

**⚠️ CRITICAL: Do not send random commands.** The EXPOSURE RULE applies. Only send frames derived from captured app traffic, or from well-reasoned protocol hypotheses. Sending arbitrary bytes to an motor controller could cause unexpected motor behavior.

---

## 3. gatttool Walkthrough (Linux Native)

### 3.1 Connect
```bash
# Start bluetoothctl interactive
bluetoothctl

# In bluetoothctl:
scan on
connect <CYCMOTOR_ADDRESS>
pair <CYCMOTOR_ADDRESS>   # if needed
exit
```

### 3.2 Enable Notifications
```bash
# Write CCC descriptor to enable notifications
gatttool -b <CYCMOTOR_ADDRESS> -t random --char-write-req -a 0x0010 -v 0100
# Wait a few seconds — observe any notifications from handle 0x000f
```

### 3.3 Write a Command (after framing is known)
```bash
# Example: Write 8-byte frame (once structure is known)
gatttool -b <CYCMOTOR_ADDRESS> -t random --char-write-req -a 0x000d -v 0102030405060708
```

### 3.4 Monitor Notifications
In a separate terminal:
```bash
# Capture raw HCI events while operating the app
hcidump -X
```

---

## 4. Python BLE Approach (more control)

Using `pybluez` or `bleak` (Linux BLE Python libraries):

### 4.1 bleak Example (recommended)
```python
import asyncio
from bleak import BleakClient

CYCMOTOR_MAC = "<CYCMOTOR_ADDRESS>"
NUS_TX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
CCC_UUID    = "00002902-0000-1000-8000-00805f9b34fb"

async def debug_nus():
    client = BleakClient(CYCMOTOR_MAC, address_type="random")
    await client.connect()
    
    # Enable notifications
    await client.write_gatt_descriptor(CCC_HANDLE_GOES_HERE, bytearray([0x01, 0x00]))
    
    def notification_handler(handle, data):
        print(f"Notification from {handle}: {data.hex()}")
    
    await client.start_notify(NUS_RX_UUID, notification_handler)
    
    # Write a known-safe query (placeholder — fill in once protocol known)
    # await client.write_gatt_char(NUS_TX_UUID, bytes([0x01, 0x03, 0x01, 0x03, 0x00, 0x0a]))
    
    await asyncio.sleep(30)  # collect 30s of notifications
    await client.disconnect()

asyncio.run(debug_nus())
```

---

## 5. Analyzing Captured Traffic

### 5.1 Wireshark Filter Cheatsheet

```wireshark
# All BLE traffic to/from CYC motor
btl2cap.btle and bluetooth.addr == <cycmotor_address>

# Only GATT/ATT packets (excludes connection setup)
btl2cap.btle and btl2cap.btle.command == 0x0012

# Write commands to NUS TX (handle 0x000d)
btl2cap.btle.btle_att.opcode == 0x0012 and btl2cap.handover_type == 0x000d

# Notifications from NUS RX (handle 0x000f)
btl2cap.btle.btle_att.opcode == 0x001b and btl2cap.handover_type == 0x000f

# Show only notification payloads from motor
btl2cap.btle.btle_att.opcode == 0x001b and btl2cap.handover_type == 0x000f
```

### 5.2 Identifying Frame Structure

When you have a set of captured packets:

**Step 1 — Find the signature:**
Look at multiple command packets (app → motor). If there's a fixed pattern in the first 1–3 bytes that never changes, that's your signature.

**Step 2 — Find the length field:**
If bytes 0–1 are a signature, byte 2 is often the length. Verify by checking if the length byte equals the number of bytes after it (before any trailing checksum).

**Step 3 — Find the command type:**
Look at packets while performing different app actions. The bytes that change correlating with an action are payload. The byte that changes in a pattern suggesting "which operation" is likely the command type.

**Step 4 — Identify payload boundaries:**
If the length byte = N, then bytes after command type up to byte (2+N+1) are payload. The last 1–2 bytes are likely checksum.

**Step 5 — Find the checksum:**
Try XOR of all bytes from index 2 (after signature) through end. Or CRC16. Or just a SUM mod 256. Test against known-good captures.

### 5.3 Tools for Byte Pattern Analysis

| Tool | Description |
|---|---|
| **Wireshark** | Protocol analyzer; filter by MAC, handle, opcode |
| **CyberChef** (https://gchq.github.io/CyberChef/) | Hex parsing, XOR, CRC calculation — great for protocol dissection |
| **xxd** | Hex dump on Linux |
| **Python + Jupyter** | Iterate through captures, test XOR/CRC hypotheses rapidly |
| **borgar/traffic** | Hex diff/compare tool |

---

## 6. Systematic Iteration

Protocol reverse engineering is iterative. A recommended sequence:

```
Phase 1: Observe (1–2 sessions)
├── Enable notifications on NUS RX
├── Observe any spontaneous motor output (periodic telemetry?)
├── Capture 5 minutes of idle time (no commands sent)
└── Note: does the motor send anything without being asked?

Phase 2: Capture App Traffic (1 session)
├── nRF sniffer or Android HCI snoop
├── Use CYC app for 5 minutes (all features)
└── Identify request/response pairs

Phase 3: Hypothesis (1 session)
├── From captures, hypothesize frame format
├── Verify against multiple captures
├── Build draft packet templates for each operation
└── Identify checksum algorithm

Phase 4: Verification (1 session)
├── Write Python script to send hypothesized commands
├── Verify responses match expected structure
└── Test that known-safe commands produce expected motor behavior
```

---

## 7. Checklist Before Probing

- [ ] Android phone with CYC Ride Control installed
- [ ] Bluetooth HCI snoop log enabled OR nRF52840 BLE sniffer ready
- [ ] gatttool or bleak working on Linux box
- [ ] Wireshark installed and configured for BT captures
- [ ] Safety: motor secured, system safe (EXPOSURE RULE applies)
- [ ] Session logged — all captures saved to `researchdocs/captures/`

---

*Last updated: 2026-05-28 by Renarac (OpenClaw agent)*
