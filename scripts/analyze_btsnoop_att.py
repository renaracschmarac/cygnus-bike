#!/usr/bin/env python3
"""Extract ATT write/notification prefixes from a BTSnoop HCI log."""

from __future__ import annotations

import argparse
import struct
from collections import Counter


ATT_NAMES = {
    0x12: "write_req",
    0x13: "write_rsp",
    0x1B: "notify",
    0x52: "write_cmd",
}


def iter_btsnoop(path: str):
    data = open(path, "rb").read()
    if data[:8] != b"btsnoop\x00":
        raise ValueError(f"{path} is not a btsnoop file")
    offset = 16
    while offset + 24 <= len(data):
        orig_len, inc_len, flags, drops = struct.unpack(">IIII", data[offset : offset + 16])
        timestamp = struct.unpack(">Q", data[offset + 16 : offset + 24])[0]
        offset += 24
        packet = data[offset : offset + inc_len]
        offset += inc_len
        yield timestamp, flags, orig_len, inc_len, drops, packet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--handle", type=lambda value: int(value, 0), default=None)
    args = parser.parse_args()

    counts = Counter()
    for timestamp, flags, orig_len, inc_len, _drops, packet in iter_btsnoop(args.path):
        if not packet or packet[0] != 0x02 or len(packet) < 12:
            continue

        acl_header = int.from_bytes(packet[1:3], "little")
        hci_handle = acl_header & 0x0FFF
        pb = (acl_header >> 12) & 0x03
        body = packet[5:]
        if len(body) < 7:
            continue

        l2cap_len, cid = struct.unpack("<HH", body[:4])
        if cid != 0x0004:
            continue

        att = body[4:]
        opcode = att[0]
        counts[opcode] += 1
        if opcode not in ATT_NAMES or len(att) < 3:
            continue

        att_handle = int.from_bytes(att[1:3], "little")
        if args.handle is not None and att_handle != args.handle:
            continue

        value = att[3:]
        trunc = " truncated" if inc_len < orig_len else ""
        print(
            f"flags={flags} hci={hci_handle} pb={pb} "
            f"op=0x{opcode:02x}({ATT_NAMES[opcode]}) "
            f"handle=0x{att_handle:04x} l2cap_len={l2cap_len} "
            f"included={inc_len}/{orig_len}{trunc} value_prefix={value.hex(' ')}"
        )

    print("ATT opcode counts:", {f"0x{k:02x}": v for k, v in sorted(counts.items())})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
