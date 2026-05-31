# Cygnus Bike

Read-only exploration tooling for the CYC X1 Pro Gen4 motor Bluetooth interface.

Target motor type:

- BLE name: `CYCMOTOR`

Current rule: do not write motor configuration unless the protocol and command are understood. The scripts in this repo are intended for discovery and read-only telemetry/GATT inspection.

## Privacy

BLE addresses are treated as private local identifiers. Do not commit real device addresses. The tools discover devices named `CYCMOTOR` and save the selected address to `.cygnus-bike.local.json`, which is ignored by git.

## First Probe

Run:

```sh
scripts/probe_cycmotor_readonly.sh
```

The motor currently advertises Nordic UART Service:

- Service: `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
- Write characteristic: `6e400002-b5a3-f393-e0a9-e50e24dcca9e`, handle `0x000d`
- Notify characteristic: `6e400003-b5a3-f393-e0a9-e50e24dcca9e`, handle `0x000f`
- CCC descriptor: handle `0x0010`

See [docs/cycmotor-probe.md](docs/cycmotor-probe.md) for captured findings.

## Telemetry

The CYC Ride Control APK confirms VESC-style `COMM_GET_VALUES` telemetry over NUS. To read telemetry directly from Linux, disconnect the phone app first, then run:

```sh
scripts/cyc_telemetry.py --raw
```

To print every decoded value from whichever layout the controller actually returns:

```sh
scripts/cyc_telemetry.py --all-fields --raw --count 1
```

For machine-readable output, use:

```sh
scripts/cyc_telemetry.py --json --count 1
```

The tested CYC X1 Pro Gen4/X12 controller currently responds to `COMM_GET_VALUES` with `cyc_uart` length telemetry. The APK also includes `xSeries_uart.json`; force it only when the validated packet length is long enough for that layout:

```sh
scripts/cyc_telemetry.py --layout xSeries_uart --all-fields --raw
```

For read-only command probes that are not telemetry, stop after the first
validated VESC packet instead of waiting for a decoded dashboard frame:

```sh
scripts/cyc_telemetry.py --command 0x11 --packet-count 1
scripts/cyc_telemetry.py --command 0x0e --packet-count 1
```

The official Android app sends those two requests when opening settings:
`0x11` is app config and `0x0e` is motor config. Live reads decoded the candidate
transport flags as `permanent_uart_enabled=1`, `send_can_status=0`,
`send_can_status_rate_hz=50`, `app_uart_baudrate=9600`, `comm_mode=0`, and
`bms.fwd_can_mode=0`. Those are config/status settings, not a confirmed switch
for the extended `xSeries_uart.json` dashboard packet. Known enum fields are
printed with their VESC-style names, for example
`comm_mode=0 (COMM_MODE_INTEGRATE)` and `motor_type=2 (MOTOR_TYPE_FOC)`.

On first run, the script scans for BLE devices named `CYCMOTOR`. If it finds one, it saves the address locally. If it finds more than one, it prompts for a selection. Later runs use `.cygnus-bike.local.json` by default; delete that file or pass `--scan` to rediscover.

By default the script sends only the read-only `COMM_GET_VALUES` request (`02 01 04 40 84 03`), subscribes to notifications, validates VESC CRC16 frames, and decodes `data/cyc_uart.json` / `data/xSeries_uart.json`. Passing `--command` changes the read request; do not use write/config-set commands without a backup and an explicit recovery plan.
