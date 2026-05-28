# CYCMOTOR Read-Only Probe

Date: 2026-05-28

Target:

- Device name: `CYCMOTOR`
- Address: redacted; discover locally by BLE name `CYCMOTOR`
- Address type: random
- Paired: no
- Bonded: no

## Discovery

`bluetoothctl --timeout 15 scan on` found:

```text
Device <CYCMOTOR_ADDRESS> CYCMOTOR
```

`bluetoothctl info <CYCMOTOR_ADDRESS>` initially advertised:

```text
UUID: Nordic UART Service (6e400001-b5a3-f393-e0a9-e50e24dcca9e)
```

After connection and service resolution, BlueZ reported:

```text
UUID: Generic Access Profile    (00001800-0000-1000-8000-00805f9b34fb)
UUID: Generic Attribute Profile (00001801-0000-1000-8000-00805f9b34fb)
UUID: Nordic UART Service       (6e400001-b5a3-f393-e0a9-e50e24dcca9e)
```

## Services

From `gatttool -b <CYCMOTOR_ADDRESS> -t random --primary`:

```text
attr handle = 0x0001, end grp handle = 0x0009 uuid: 00001800-0000-1000-8000-00805f9b34fb
attr handle = 0x000a, end grp handle = 0x000a uuid: 00001801-0000-1000-8000-00805f9b34fb
attr handle = 0x000b, end grp handle = 0xffff uuid: 6e400001-b5a3-f393-e0a9-e50e24dcca9e
```

## Characteristics

From `gatttool -b <CYCMOTOR_ADDRESS> -t random --characteristics`:

| Handle | Value Handle | Properties | UUID | Notes |
| --- | --- | --- | --- | --- |
| `0x0002` | `0x0003` | `0x0a` | `00002a00-0000-1000-8000-00805f9b34fb` | Device Name |
| `0x0004` | `0x0005` | `0x02` | `00002a01-0000-1000-8000-00805f9b34fb` | Appearance |
| `0x0006` | `0x0007` | `0x02` | `00002a04-0000-1000-8000-00805f9b34fb` | Peripheral Preferred Connection Parameters |
| `0x0008` | `0x0009` | `0x02` | `00002aa6-0000-1000-8000-00805f9b34fb` | Central Address Resolution |
| `0x000c` | `0x000d` | `0x0c` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | Nordic UART write/write-without-response |
| `0x000e` | `0x000f` | `0x10` | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | Nordic UART notify |

BlueZ D-Bus introspection confirms the Nordic UART characteristic flags:

```text
6e400002... Flags: "write-without-response" "write", Handle 12, MTU 247
6e400003... Flags: "notify", Handle 14, MTU 247
```

## Read Values

Read-only values captured with `gatttool --char-read`:

| Handle | UUID | Raw bytes | Decoded |
| --- | --- | --- | --- |
| `0x0003` | `2a00` | `43 59 43 4d 4f 54 4f 52` | `CYCMOTOR` |
| `0x0005` | `2a01` | `00 00` | Appearance `0x0000` |
| `0x0007` | `2a04` | `06 00 10 00 00 00 90 01` | Min interval 7.5 ms, max interval 20 ms, latency 0, timeout 4000 ms |
| `0x0009` | `2aa6` | `01` | Central Address Resolution supported |
| `0x0010` | `2902` | `00 00` | Notifications disabled for this client |

Reading the Nordic UART value handles `0x000d` and `0x000f` returned empty values. They are not useful telemetry reads by themselves.

## Interpretation

The motor does not expose telemetry as ordinary readable BLE characteristics. It exposes a Nordic UART-style command channel:

- Host writes commands to `6e400002...` at value handle `0x000d`.
- Motor likely sends responses/telemetry as notifications from `6e400003...` at value handle `0x000f`.
- Enabling notifications requires writing the CCC descriptor `0x0010` to `01 00`. That is a client subscription rather than a motor configuration write, but it is still a BLE write and was intentionally not done in this first pass.

Next protocol work should capture traffic from the official app, or enable notifications and send only known-safe query frames once the CYC UART framing/checksum is identified.
