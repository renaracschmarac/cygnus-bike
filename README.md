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

On first run, the script scans for BLE devices named `CYCMOTOR`. If it finds one, it saves the address locally. If it finds more than one, it prompts for a selection. Later runs use `.cygnus-bike.local.json` by default; delete that file or pass `--scan` to rediscover.

The script sends only the read-only `COMM_GET_VALUES` request (`02 01 04 40 84 03`), subscribes to notifications, validates VESC CRC16 frames, and decodes `data/cyc_uart.json` / `data/xSeries_uart.json`.
