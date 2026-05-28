# Next Steps & Open Questions
**Date:** 2026-05-28  
**Status:** Pre-protocol capture phase  
**For:** Reviewing agent tasked with advancing CYC motor BLE protocol work

---

## 1. What We Know vs. What We Don't Know

### ✅ Confirmed (from local probe)

1. BLE name: `CYCMOTOR`, MAC: `<CYCMOTOR_ADDRESS>`, random address
2. GATT: GAP service + GATT service + Nordic UART Service NUS (`6e400001-...`)
3. NUS TX (write): handle `0x000d`, properties `write+write-without-response`
4. NUS RX (notify): handle `0x000f`, properties `notify`
5. CCC descriptor: handle `0x0010`, currently `00 00` (notifications disabled)
6. MTU: 247 bytes (confirmed)
7. All standard GAP characteristics read as zeros/empty (no structured telemetry)
8. All motor state is via NUS raw byte pipe

### ❌ Unknown (blocked on capture)

1. What motor sends spontaneously when notifications are enabled
2. Frame structure (signature, length, command type, payload, checksum)
3. Whether there's a request-response protocol or motor broadcasts telemetry
4. Telemetry update rate (0.5s, 1s, event-driven?)
5. How assist level changes are encoded as commands
6. How battery voltage/speed/torque are encoded in responses
7. Whether the protocol is compatible with ASI BAC MODBUS register addressing

---

## 2. Immediate Next Actions (Priority Order)

### 🔴 P0 — Enable Notifications & Observe

**This is the one safe action that should be done first, before any commanding.**

1. Connect to `CYCMOTOR` with `gatttool`
2. Write `01 00` to descriptor `0x0010` (enable notifications)
3. Wait 10–30 seconds with no further commands
4. Capture any received notifications from handle `0x000f`
5. Document:
   - Do any notifications arrive spontaneously (periodic status broadcast)?
   - What is the frame structure (hex strings)?
   - Do any bytes change over time (idle motor or is it actively sending)?

**Why first:** This is a standard GATT subscription operation, not a motor command. It enables us to receive data from the motor without sending any application-layer commands.

### 🟡 P1 — Capture Official App Traffic

**Best approach: Android Bluetooth HCI snoop log**

1. Android Developer Options → Enable "Bluetooth HCI snoop log"
2. Forget/re-pair the motor with CYC Ride Control app
3. Operate the app for 5 minutes: change assist levels, open dashboard, adjust settings
4. Pull log: `adb pull /sdcard/btsnoop_hci.log`
5. Open in Wireshark
6. Filter by CYC MAC address `<cycmotor_address>`
7. Focus on `ATT Write Request` packets to `6e400002...` (NUS TX) and `Handle Value Notification` from `6e400003...` (NUS RX)

**Alternative: nRF52840 BLE sniffer**
- Nathanor's nRF52840 sniffer firmware + Wireshark
- Captures air traffic — no Android setup needed
- Best quality capture
- Hardware required

### 🟡 P2 — Analyze Captured Packets

After capturing app traffic:

1. **Collect request-response pairs** — look for app → motor command followed by motor → app response within ~500ms
2. **Find the signature** — common patterns: `0x67 0x74` (oBike), `0x55 0xAA`, `0x01 0x**`, ASCII sequence
3. **Identify command types** — the byte(s) that change based on which app action was performed
4. **Identify payload fields** — bytes that encode specific values (speed, voltage, assist level)
5. **Find the checksum** — verify by XORing or running CRC against all captured frames

### 🟡 P3 — Generate Protocol Hypotheses

Document the following for each hypothesis:
- Proposed frame format (byte index → field name)
- Checksum algorithm tested
- Positive evidence (captured packets that fit the hypothesis)
- Negative evidence (packets that don't fit)
- Confidence level

### 🟢 P4 — Send First Safe Commands

**Only after P1–P3 confirm a frame structure and checksum algorithm:**

1. Replicate a simple command frame seen in capture (matching bytes exactly)
2. Send it via `gatttool` or Python/bleak
3. Verify response matches structure from capture
4. Do not attempt to craft new commands until structure + checksum are confirmed

---

## 3. Safe-to-Send Hypotheses (Requiring Minimal Evidence)

### Hypothesis A: MODBUS-like register read

**Hypothesis:** If CYC X12 controller is register-compatible with ASI BAC:
- Send 6-byte MODBUS read query: `01 03 01 03 00 0a` (read 10 registers from 259, ASI BAC telemetry block)
- Check response format fits MODBUS response with expected telemetry fields

**Risk:** Low — this is a read-only operation; worst case is no response or garbled response

### Hypothesis B: oBike-style signature framing

**Hypothesis:** Frames start with `0x67 0x74` (signature) + length + command_type + payload + XOR checksum

**Risk:** Low — purely observational at first; does not send anything new

### Hypothesis C: Periodic telemetry broadcast

**Hypothesis:** Motor sends a status notification every ~1 second automatically once connected and subscribed

**This requires only enabling notifications (P0 action) to test.**

---

## 4. What NOT to Do

| Action | Why Not |
|---|---|
| Do not send arbitrary hex strings to NUS TX | Unknown protocol; random bytes could affect motor behavior |
| Do not write motor config until protocol confirmed | Until checksum is verified, writes could corrupt parameters |
| Do not assume 9600 baud or 115200 UART settings | This is BLE, not wired UART; speed irrelevant |
| Do not assume Bafang UART protocol directly | Different manufacturers; may share conceptual fields but not byte-level compatible |

---

## 5. Open Research Questions

These are genuine unknowns that the capturing agent should look for:

1. **Periodic or event-driven telemetry?** Does the motor send regular status frames at fixed intervals, or only respond when queried?
2. **How is assist level encoded?** As a byte value 0–5? As a percentage? As a bitmask?
3. **How is speed encoded?** As 0.1 km/h units? As raw wheel revolution frequency?
4. **How is battery voltage encoded?** In 0.1V steps? With which precision (8-bit or 16-bit)?
5. **Does the motor support read-once querying?** Can you send a read command and get a response, or must you subscribe to notifications?
6. **Is there a connection keepalive?** Does the app send periodic pings to maintain the BLE connection?
7. **What's the maximum command payload?** Can you send a multi-register write in one frame or must it be fragmented?
8. **Does the protocol include error codes?** Does the motor respond with error bytes if an invalid command is received?

---

## 6. Suggested File Organisation for Reviewing Agent

```
/home/edmund/.openclaw/workspace/researchdocs/
├── 01_DEVICE_OVERVIEW.md              ← start here
├── 02_GATT_MAP.md                     ← confirmed local findings
├── 03_NUS_REFERENCE.md               ← NUS architecture context
├── 04_PROTOCOLS_REFERENCE.md          ← related protocol examples
├── 05_REVERSE_ENGINEERING_METHOD.md  ← workflow & tools
├── 06_NEXT_STEPS.md                   ← this file / action plan
└── captures/                          ← store Wireshark logs, hex dumps
    └── (add capture files here)
```

The `captures/` subdirectory should be used for any HCI snoop logs, hex dumps of notifications, or annotated packet captures the reviewing agent generates.

---

*Last updated: 2026-05-28 by Renarac (OpenClaw agent)*
