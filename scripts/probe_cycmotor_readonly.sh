#!/usr/bin/env bash
set -euo pipefail

name="${CYCMOTOR_NAME:-CYCMOTOR}"
settings_file=".cygnus-bike.local.json"
addr="${1:-}"
type="${2:-random}"

discover_device() {
  bluetoothctl --timeout 15 scan on >/dev/null
  mapfile -t devices < <(bluetoothctl devices | awk -v name="$name" '$1 == "Device" && $3 == name { print $2 }')

  if [[ "${#devices[@]}" -eq 0 ]]; then
    echo "No BLE devices named $name found" >&2
    exit 1
  fi

  if [[ "${#devices[@]}" -eq 1 ]]; then
    addr="${devices[0]}"
  else
    echo "Found multiple $name devices:" >&2
    local i
    for i in "${!devices[@]}"; do
      printf '  %d. %s\n' "$((i + 1))" "${devices[$i]}" >&2
    done
    read -r -p "Select $name device [1-${#devices[@]}]: " choice
    addr="${devices[$((choice - 1))]}"
  fi

  if bluetoothctl info "$addr" | head -n 1 | grep -q '(random)'; then
    type="random"
  else
    type="public"
  fi
}

if [[ -z "$addr" && -f "$settings_file" ]]; then
  addr="$(sed -n 's/.*"address"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$settings_file" | head -n 1)"
  type="$(sed -n 's/.*"address_type"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$settings_file" | head -n 1)"
fi

if [[ -z "$addr" ]]; then
  discover_device
fi

printf '{\n  "device_name": "%s",\n  "address": "%s",\n  "address_type": "%s"\n}\n' "$name" "$addr" "$type" > "$settings_file"
chmod 600 "$settings_file"

echo "== Adapter =="
bluetoothctl show

echo
echo "== Device info before scan =="
bluetoothctl info "$addr" || true

echo
echo "== Short scan =="
bluetoothctl --timeout 15 scan on

echo
echo "== Device info after scan =="
bluetoothctl info "$addr" || true

echo
echo "== Primary services =="
gatttool -b "$addr" -t "$type" --primary

echo
echo "== Characteristics =="
gatttool -b "$addr" -t "$type" --characteristics

echo
echo "== Attribute descriptors =="
sleep 2
gatttool -b "$addr" -t "$type" --char-desc

read_handle() {
  local handle="$1"
  echo
  echo "== Read handle $handle =="
  sleep 2
  gatttool -b "$addr" -t "$type" --char-read -a "$handle" || true
}

read_handle 0x0003
read_handle 0x0005
read_handle 0x0007
read_handle 0x0009
read_handle 0x000d
read_handle 0x000f
read_handle 0x0010

echo
echo "== Disconnect =="
bluetoothctl disconnect "$addr" || true
