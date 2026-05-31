#!/usr/bin/env python3
"""Read CYC/VESC telemetry over Nordic UART.

By default this sends only a VESC COMM_GET_VALUES request and subscribes to
NUS notifications. Other commands can be supplied for read-only probing; this
script does not write motor/app configuration.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import select
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Iterable


NUS_TX_HANDLE = "0x000d"
NUS_CCC_HANDLE = "0x0010"
DEVICE_NAME = "CYCMOTOR"
LOCAL_SETTINGS = ".cygnus-bike.local.json"
GET_VALUES = 4
GET_MCCONF = 0x0E
GET_APPCONF = 0x11

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SETTINGS_PATH = os.path.join(ROOT, LOCAL_SETTINGS)
ASSET_DIR = os.path.join(
    ROOT,
    "data",
)


CRC16_TAB = [
    0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50A5, 0x60C6, 0x70E7,
    0x8108, 0x9129, 0xA14A, 0xB16B, 0xC18C, 0xD1AD, 0xE1CE, 0xF1EF,
    0x1231, 0x0210, 0x3273, 0x2252, 0x52B5, 0x4294, 0x72F7, 0x62D6,
    0x9339, 0x8318, 0xB37B, 0xA35A, 0xD3BD, 0xC39C, 0xF3FF, 0xE3DE,
    0x2462, 0x3443, 0x0420, 0x1401, 0x64E6, 0x74C7, 0x44A4, 0x5485,
    0xA56A, 0xB54B, 0x8528, 0x9509, 0xE5EE, 0xF5CF, 0xC5AC, 0xD58D,
    0x3653, 0x2672, 0x1611, 0x0630, 0x76D7, 0x66F6, 0x5695, 0x46B4,
    0xB75B, 0xA77A, 0x9719, 0x8738, 0xF7DF, 0xE7FE, 0xD79D, 0xC7BC,
    0x48C4, 0x58E5, 0x6886, 0x78A7, 0x0840, 0x1861, 0x2802, 0x3823,
    0xC9CC, 0xD9ED, 0xE98E, 0xF9AF, 0x8948, 0x9969, 0xA90A, 0xB92B,
    0x5AF5, 0x4AD4, 0x7AB7, 0x6A96, 0x1A71, 0x0A50, 0x3A33, 0x2A12,
    0xDBFD, 0xCBDC, 0xFBBF, 0xEB9E, 0x9B79, 0x8B58, 0xBB3B, 0xAB1A,
    0x6CA6, 0x7C87, 0x4CE4, 0x5CC5, 0x2C22, 0x3C03, 0x0C60, 0x1C41,
    0xEDAE, 0xFD8F, 0xCDEC, 0xDDCD, 0xAD2A, 0xBD0B, 0x8D68, 0x9D49,
    0x7E97, 0x6EB6, 0x5ED5, 0x4EF4, 0x3E13, 0x2E32, 0x1E51, 0x0E70,
    0xFF9F, 0xEFBE, 0xDFDD, 0xCFFC, 0xBF1B, 0xAF3A, 0x9F59, 0x8F78,
    0x9188, 0x81A9, 0xB1CA, 0xA1EB, 0xD10C, 0xC12D, 0xF14E, 0xE16F,
    0x1080, 0x00A1, 0x30C2, 0x20E3, 0x5004, 0x4025, 0x7046, 0x6067,
    0x83B9, 0x9398, 0xA3FB, 0xB3DA, 0xC33D, 0xD31C, 0xE37F, 0xF35E,
    0x02B1, 0x1290, 0x22F3, 0x32D2, 0x4235, 0x5214, 0x6277, 0x7256,
    0xB5EA, 0xA5CB, 0x95A8, 0x8589, 0xF56E, 0xE54F, 0xD52C, 0xC50D,
    0x34E2, 0x24C3, 0x14A0, 0x0481, 0x7466, 0x6447, 0x5424, 0x4405,
    0xA7DB, 0xB7FA, 0x8799, 0x97B8, 0xE75F, 0xF77E, 0xC71D, 0xD73C,
    0x26D3, 0x36F2, 0x0691, 0x16B0, 0x6657, 0x7676, 0x4615, 0x5634,
    0xD94C, 0xC96D, 0xF90E, 0xE92F, 0x99C8, 0x89E9, 0xB98A, 0xA9AB,
    0x5844, 0x4865, 0x7806, 0x6827, 0x18C0, 0x08E1, 0x3882, 0x28A3,
    0xCB7D, 0xDB5C, 0xEB3F, 0xFB1E, 0x8BF9, 0x9BD8, 0xABBB, 0xBB9A,
    0x4A75, 0x5A54, 0x6A37, 0x7A16, 0x0AF1, 0x1AD0, 0x2AB3, 0x3A92,
    0xFD2E, 0xED0F, 0xDD6C, 0xCD4D, 0xBDAA, 0xAD8B, 0x9DE8, 0x8DC9,
    0x7C26, 0x6C07, 0x5C64, 0x4C45, 0x3CA2, 0x2C83, 0x1CE0, 0x0CC1,
    0xEF1F, 0xFF3E, 0xCF5D, 0xDF7C, 0xAF9B, 0xBFBA, 0x8FD9, 0x9FF8,
    0x6E17, 0x7E36, 0x4E55, 0x5E74, 0x2E93, 0x3EB2, 0x0ED1, 0x1EF0,
]


@dataclass(frozen=True)
class Field:
    key: str
    offset: int
    length: int
    scale: float
    type: str


@dataclass(frozen=True)
class ConfigField:
    key: str
    offset: int
    length: int
    type: str


COMMAND_NAMES = {
    GET_VALUES: "COMM_GET_VALUES",
    GET_MCCONF: "COMM_GET_MCCONF",
    GET_APPCONF: "COMM_GET_APPCONF",
}

APP_CONFIG_FIELDS = [
    ConfigField("signature", 0, 4, "uint"),
    ConfigField("controller_id", 4, 1, "uint"),
    ConfigField("timeout_msec", 5, 4, "uint"),
    ConfigField("timeout_brake_current", 9, 4, "float"),
    ConfigField("send_can_status", 13, 1, "uint"),
    ConfigField("send_can_status_rate_hz", 14, 2, "uint"),
    ConfigField("can_baud_rate", 16, 1, "uint"),
    ConfigField("pairing_done", 17, 1, "bool"),
    ConfigField("permanent_uart_enabled", 18, 1, "bool"),
    ConfigField("shutdown_mode", 19, 1, "uint"),
    ConfigField("can_mode", 20, 1, "uint"),
    ConfigField("uavcan_esc_index", 21, 1, "uint"),
    ConfigField("uavcan_raw_mode", 22, 1, "uint"),
    ConfigField("uavcan_raw_rpm_max", 23, 4, "float"),
    ConfigField("kill_sw_mode", 28, 1, "uint"),
    ConfigField("app_to_use", 29, 1, "uint"),
    ConfigField("app_ppm_conf.ctrl_type", 30, 1, "uint"),
    ConfigField("app_adc_conf.ctrl_type", 86, 1, "uint"),
    ConfigField("app_uart_baudrate", 142, 4, "uint"),
    ConfigField("app_chuk_conf.ctrl_type", 146, 1, "uint"),
    ConfigField("app_pas_conf.ctrl_type", 402, 1, "uint"),
    ConfigField("app_pas_conf.sensor_type", 403, 1, "uint"),
    ConfigField("imu_conf.type", 420, 1, "uint"),
    ConfigField("imu_conf.mode", 421, 1, "uint"),
]

MOTOR_CONFIG_FIELDS = [
    ConfigField("pwm_mode", 4, 1, "uint"),
    ConfigField("comm_mode", 5, 1, "uint"),
    ConfigField("motor_type", 6, 1, "uint"),
    ConfigField("sensor_mode", 7, 1, "uint"),
    ConfigField("foc_sensor_mode", 172, 1, "uint"),
    ConfigField("foc_observer_type", 263, 1, "uint"),
    ConfigField("foc_mtpa_mode", 317, 1, "uint"),
    ConfigField("m_sensor_port_mode", 428, 1, "uint"),
    ConfigField("m_drv8301_oc_mode", 430, 1, "uint"),
    ConfigField("m_out_aux_mode", 448, 1, "uint"),
    ConfigField("m_motor_temp_sens_type", 449, 1, "uint"),
    ConfigField("si_battery_type", 464, 1, "uint"),
    ConfigField("bms.type", 474, 1, "uint"),
    ConfigField("bms.fwd_can_mode", 483, 1, "uint"),
]

CONFIG_LAYOUTS = {
    GET_APPCONF: ("cyc_app_0503", APP_CONFIG_FIELDS),
    GET_MCCONF: ("cyc_motor_0503", MOTOR_CONFIG_FIELDS),
}

ENUM_LABELS = {
    "app_adc_conf.ctrl_type": {
        0: "ADC_CTRL_TYPE_NONE",
        1: "ADC_CTRL_TYPE_CURRENT",
        2: "ADC_CTRL_TYPE_CURRENT_REV_CENTER",
        3: "ADC_CTRL_TYPE_CURRENT_REV_BUTTON",
        4: "ADC_CTRL_TYPE_CURRENT_REV_BUTTON_BRAKE_ADC",
        5: "ADC_CTRL_TYPE_CURRENT_REV_BUTTON_BRAKE_CENTER",
        6: "ADC_CTRL_TYPE_CURRENT_NOREV_BRAKE_CENTER",
        7: "ADC_CTRL_TYPE_CURRENT_NOREV_BRAKE_BUTTON",
        8: "ADC_CTRL_TYPE_CURRENT_NOREV_BRAKE_ADC",
        9: "ADC_CTRL_TYPE_DUTY",
        10: "ADC_CTRL_TYPE_DUTY_REV_CENTER",
        11: "ADC_CTRL_TYPE_DUTY_REV_BUTTON",
        12: "ADC_CTRL_TYPE_PID",
        13: "ADC_CTRL_TYPE_PID_REV_CENTER",
        14: "ADC_CTRL_TYPE_PID_REV_BUTTON",
    },
    "app_chuk_conf.ctrl_type": {
        0: "CHUK_CTRL_TYPE_NONE",
        1: "CHUK_CTRL_TYPE_CURRENT",
        2: "CHUK_CTRL_TYPE_CURRENT_NOREV",
        3: "CHUK_CTRL_TYPE_CURRENT_BIDIRECTIONAL",
    },
    "app_pas_conf.ctrl_type": {
        0: "PAS_CTRL_TYPE_NONE",
        1: "PAS_CTRL_TYPE_CADENCE",
    },
    "app_pas_conf.sensor_type": {
        0: "PAS_SENSOR_TYPE_QUADRATURE",
    },
    "app_ppm_conf.ctrl_type": {
        0: "PPM_CTRL_TYPE_NONE",
        1: "PPM_CTRL_TYPE_CURRENT",
        2: "PPM_CTRL_TYPE_CURRENT_NOREV",
        3: "PPM_CTRL_TYPE_CURRENT_NOREV_BRAKE",
        4: "PPM_CTRL_TYPE_DUTY",
        5: "PPM_CTRL_TYPE_DUTY_NOREV",
        6: "PPM_CTRL_TYPE_PID",
        7: "PPM_CTRL_TYPE_PID_NOREV",
        8: "PPM_CTRL_TYPE_CURRENT_BRAKE_REV_HYST",
        9: "PPM_CTRL_TYPE_CURRENT_SMART_REV",
    },
    "app_to_use": {
        0: "APP_NONE",
        1: "APP_PPM",
        2: "APP_ADC",
        3: "APP_UART",
        4: "APP_PPM_UART",
        5: "APP_ADC_UART",
        6: "APP_NUNCHUK",
        7: "APP_NRF",
        8: "APP_CUSTOM",
        9: "APP_BALANCE",
        10: "APP_PAS",
        11: "APP_ADC_PAS",
    },
    "bms.fwd_can_mode": {
        0: "BMS_FWD_CAN_MODE_DISABLED",
        1: "BMS_FWD_CAN_MODE_USB_ONLY",
        2: "BMS_FWD_CAN_MODE_ANY",
    },
    "bms.type": {
        0: "BMS_TYPE_NONE",
        1: "BMS_TYPE_VESC",
    },
    "can_baud_rate": {
        0: "CAN_BAUD_125K",
        1: "CAN_BAUD_250K",
        2: "CAN_BAUD_500K",
        3: "CAN_BAUD_1M",
        4: "CAN_BAUD_10K",
        5: "CAN_BAUD_20K",
        6: "CAN_BAUD_50K",
        7: "CAN_BAUD_75K",
        8: "CAN_BAUD_100K",
        255: "CAN_BAUD_INVALID",
    },
    "can_mode": {
        0: "CAN_MODE_VESC",
        1: "CAN_MODE_UAVCAN",
        2: "CAN_MODE_COMM_BRIDGE",
    },
    "comm_mode": {
        0: "COMM_MODE_INTEGRATE",
        1: "COMM_MODE_DELAY",
    },
    "foc_mtpa_mode": {
        0: "MTPA_MODE_OFF",
        1: "MTPA_MODE_IQ_TARGET",
        2: "MTPA_MODE_IQ_MEASURED",
    },
    "foc_observer_type": {
        0: "FOC_OBSERVER_ORTEGA_ORIGINAL",
        1: "FOC_OBSERVER_MXLEMMING",
        2: "FOC_OBSERVER_ORTEGA_LAMBDA_COMP",
        3: "FOC_OBSERVER_MXLEMMING_LAMBDA_COMP",
        4: "FOC_OBSERVER_MXV",
        5: "FOC_OBSERVER_MXV_LAMBDA_COMP",
        6: "FOC_OBSERVER_MXV_LAMBDA_COMP_LIN",
    },
    "foc_sensor_mode": {
        0: "FOC_SENSOR_MODE_SENSORLESS",
        1: "FOC_SENSOR_MODE_ENCODER",
        2: "FOC_SENSOR_MODE_HALL",
        3: "FOC_SENSOR_MODE_HFI",
        4: "FOC_SENSOR_MODE_HFI_START",
        5: "FOC_SENSOR_MODE_HFI_V2",
        6: "FOC_SENSOR_MODE_HFI_V3",
        7: "FOC_SENSOR_MODE_HFI_V4",
        8: "FOC_SENSOR_MODE_HFI_V5",
        9: "FOC_SENSOR_MODE_ENCODER_AB",
    },
    "imu_conf.mode": {
        0: "AHRS_MODE_MADGWICK",
        1: "AHRS_MODE_MAHONY",
    },
    "imu_conf.type": {
        0: "IMU_TYPE_OFF",
        1: "IMU_TYPE_INTERNAL",
        2: "IMU_TYPE_EXTERNAL_MPU9X50",
        3: "IMU_TYPE_EXTERNAL_ICM20948",
        4: "IMU_TYPE_EXTERNAL_BMI160",
        5: "IMU_TYPE_EXTERNAL_LSM6DS3",
    },
    "kill_sw_mode": {
        0: "KILL_SW_MODE_DISABLED",
        1: "KILL_SW_MODE_PPM_LOW",
        2: "KILL_SW_MODE_PPM_HIGH",
        3: "KILL_SW_MODE_ADC2_LOW",
        4: "KILL_SW_MODE_ADC2_HIGH",
    },
    "m_drv8301_oc_mode": {
        0: "DRV8301_OC_LIMIT",
        1: "DRV8301_OC_LATCH_SHUTDOWN",
        2: "DRV8301_OC_REPORT_ONLY",
        3: "DRV8301_OC_DISABLED",
    },
    "m_motor_temp_sens_type": {
        0: "TEMP_SENSOR_NTC_10K_25C",
        1: "TEMP_SENSOR_PTC_1K_100C",
        2: "TEMP_SENSOR_KTY83_122",
        3: "TEMP_SENSOR_NTC_100K_25C",
        4: "TEMP_SENSOR_KTY84_130",
        5: "TEMP_SENSOR_NTCX",
        6: "TEMP_SENSOR_PTCX",
        7: "TEMP_SENSOR_PT1000",
        8: "TEMP_SENSOR_DISABLED",
    },
    "m_out_aux_mode": {
        0: "OUT_AUX_MODE_OFF",
        1: "OUT_AUX_MODE_ON_AFTER_2S",
        2: "OUT_AUX_MODE_ON_AFTER_5S",
        3: "OUT_AUX_MODE_ON_AFTER_10S",
        4: "OUT_AUX_MODE_UNUSED",
        5: "OUT_AUX_MODE_ON_WHEN_RUNNING",
        6: "OUT_AUX_MODE_ON_WHEN_NOT_RUNNING",
        7: "OUT_AUX_MODE_MOTOR_50",
        8: "OUT_AUX_MODE_MOSFET_50",
        9: "OUT_AUX_MODE_MOTOR_70",
        10: "OUT_AUX_MODE_MOSFET_70",
        11: "OUT_AUX_MODE_MOTOR_MOSFET_50",
        12: "OUT_AUX_MODE_MOTOR_MOSFET_70",
    },
    "m_sensor_port_mode": {
        0: "SENSOR_PORT_MODE_HALL",
        1: "SENSOR_PORT_MODE_ABI",
        2: "SENSOR_PORT_MODE_AS5047_SPI",
        3: "SENSOR_PORT_MODE_AD2S1205",
        4: "SENSOR_PORT_MODE_SINCOS",
        5: "SENSOR_PORT_MODE_TS5700N8501",
        6: "SENSOR_PORT_MODE_TS5700N8501_MULTITURN",
        7: "SENSOR_PORT_MODE_MT6816_SPI_HW",
        8: "SENSOR_PORT_MODE_AS5x47U_SPI",
        9: "SENSOR_PORT_MODE_BISSC",
        10: "SENSOR_PORT_MODE_TLE5012_SSC_SW",
        11: "SENSOR_PORT_MODE_TLE5012_SSC_HW",
        12: "SENSOR_PORT_MODE_CUSTOM_ENCODER",
        13: "SENSOR_PORT_MODE_PWM",
        14: "SENSOR_PORT_MODE_PWM_ABI",
        15: "SENSOR_PORT_MODE_MA782",
        16: "SENSOR_PORT_MODE_AMT22",
    },
    "motor_type": {
        0: "MOTOR_TYPE_BLDC",
        1: "MOTOR_TYPE_DC",
        2: "MOTOR_TYPE_FOC",
    },
    "pwm_mode": {
        0: "PWM_MODE_NONSYNCHRONOUS_HISW",
        1: "PWM_MODE_SYNCHRONOUS",
        2: "PWM_MODE_BIPOLAR",
    },
    "send_can_status": {
        0: "CAN_STATUS_DISABLED",
        1: "CAN_STATUS_1",
        2: "CAN_STATUS_1_2",
        3: "CAN_STATUS_1_2_3",
        4: "CAN_STATUS_1_2_3_4",
        5: "CAN_STATUS_1_2_3_4_5",
    },
    "sensor_mode": {
        0: "SENSOR_MODE_SENSORLESS",
        1: "SENSOR_MODE_SENSORED",
        2: "SENSOR_MODE_HYBRID",
    },
    "shutdown_mode": {
        0: "SHUTDOWN_MODE_ALWAYS_OFF",
        1: "SHUTDOWN_MODE_ALWAYS_ON",
        2: "SHUTDOWN_MODE_TOGGLE_BUTTON_ONLY",
        3: "SHUTDOWN_MODE_OFF_AFTER_10S",
        4: "SHUTDOWN_MODE_OFF_AFTER_1M",
        5: "SHUTDOWN_MODE_OFF_AFTER_5M",
        6: "SHUTDOWN_MODE_OFF_AFTER_10M",
        7: "SHUTDOWN_MODE_OFF_AFTER_30M",
        8: "SHUTDOWN_MODE_OFF_AFTER_1H",
        9: "SHUTDOWN_MODE_OFF_AFTER_5H",
    },
    "si_battery_type": {
        0: "BATTERY_TYPE_LIION_3_0__4_2",
        1: "BATTERY_TYPE_LIIRON_2_6__3_6",
        2: "BATTERY_TYPE_LEAD_ACID",
    },
    "uavcan_raw_mode": {
        0: "UAVCAN_RAW_MODE_CURRENT",
        1: "UAVCAN_RAW_MODE_CURRENT_NO_REV_BRAKE",
        2: "UAVCAN_RAW_MODE_DUTY",
    },
}


def crc16(data: bytes) -> int:
    cksum = 0
    for byte in data:
        cksum = CRC16_TAB[((cksum >> 8) ^ byte) & 0xFF] ^ ((cksum << 8) & 0xFFFF)
    return cksum & 0xFFFF


def encode_packet(payload: bytes) -> bytes:
    crc = crc16(payload)
    if len(payload) <= 255:
        return bytes([0x02, len(payload)]) + payload + crc.to_bytes(2, "big") + b"\x03"
    return bytes([0x03]) + len(payload).to_bytes(2, "big") + payload + crc.to_bytes(2, "big") + b"\x03"


def iter_packets(buffer: bytearray) -> Iterable[bytes]:
    while buffer:
        if buffer[0] not in (0x02, 0x03):
            del buffer[0]
            continue

        start = buffer[0]
        if start == 0x02:
            if len(buffer) < 5:
                return
            length = buffer[1]
            header = 2
        else:
            if len(buffer) < 6:
                return
            length = int.from_bytes(buffer[1:3], "big")
            header = 3

        total = header + length + 2 + 1
        if len(buffer) < total:
            return
        raw = bytes(buffer[:total])
        del buffer[:total]
        if raw[-1] != 0x03:
            continue
        payload = raw[header : header + length]
        got_crc = int.from_bytes(raw[header + length : header + length + 2], "big")
        if crc16(payload) != got_crc:
            print(f"crc mismatch: {raw.hex(' ')}", file=sys.stderr)
            continue
        yield payload


def load_layout(name: str) -> list[Field]:
    path = os.path.join(ASSET_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return [
        Field(
            key=item["key"],
            offset=int(item["offset"]),
            length=int(item["length"]),
            scale=float(item.get("scale", 1)),
            type=item["type"],
        )
        for item in raw
    ]


def layout_size(layout: list[Field]) -> int:
    return max(field.offset + field.length for field in layout)


def decode_value(data: bytes, field: Field) -> float | int:
    raw = data[field.offset : field.offset + field.length]
    if field.type == "float":
        import struct

        value = struct.unpack(">f", raw)[0]
    else:
        signed = field.type == "int"
        value = int.from_bytes(raw, "big", signed=signed)
    if field.scale and field.scale != 1:
        return value / field.scale
    return value


def decode_config_value(data: bytes, field: ConfigField) -> bool | float | int:
    raw = data[field.offset : field.offset + field.length]
    if len(raw) != field.length:
        raise ValueError(f"not enough bytes for {field.key}")
    if field.type == "float":
        import struct

        return struct.unpack(">f", raw)[0]
    if field.type == "bool":
        return bool(int.from_bytes(raw, "big"))
    signed = field.type == "int"
    return int.from_bytes(raw, "big", signed=signed)


def command_name(command: int) -> str:
    return COMMAND_NAMES.get(command, f"COMM_0x{command:02x}")


def enum_label(key: str, value: bool | float | int) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return ENUM_LABELS.get(key, {}).get(value)


def format_config_value(key: str, value: bool | float | int) -> str:
    if isinstance(value, bool):
        return f"{int(value)} ({'enabled' if value else 'disabled'})"
    label = enum_label(key, value)
    if label:
        return f"{value} ({label})"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def decode_config(payload: bytes) -> tuple[str, int, dict[str, bool | float | int]] | None:
    if not payload:
        return None
    response_command = payload[0]
    config = CONFIG_LAYOUTS.get(response_command)
    if not config:
        return None

    layout_name, fields = config
    data = payload[1:]
    if len(data) < max(field.offset + field.length for field in fields):
        return None

    values = {field.key: decode_config_value(data, field) for field in fields}
    return layout_name, response_command, values


def decode_telemetry(payload: bytes, layouts: dict[str, list[Field]]) -> tuple[str, dict[str, float | int]] | None:
    candidates = []
    for name, layout in layouts.items():
        size = layout_size(layout)
        if len(payload) == size:
            candidates.append((name, payload, False))
        if len(payload) == size + 1 and payload[0] in (GET_VALUES, 0x00):
            candidates.append((name, payload[1:], True))

    if not candidates:
        return None

    name, data, _stripped_command = max(
        candidates,
        # Prefer the largest fitting layout, then prefer stripping the VESC
        # command byte. CYC GET_VALUES notifications are 0x04 + telemetry.
        key=lambda item: (layout_size(layouts[item[0]]), item[2]),
    )
    values = {field.key: decode_value(data, field) for field in layouts[name]}
    return name, values


def payload_decode_lengths(payload: bytes) -> tuple[int, int | None]:
    data_len = len(payload)
    stripped_data_len = None
    if payload and payload[0] in (GET_VALUES, 0x00):
        stripped_data_len = len(payload) - 1
    return data_len, stripped_data_len


def print_decoded(
    layout_name: str,
    values: dict[str, float | int],
    raw_payload: bytes,
    *,
    all_fields: bool,
    json_output: bool,
) -> None:
    if json_output:
        print(
            json.dumps(
                {
                    "type": "telemetry",
                    "layout": layout_name,
                    "payload_len": len(raw_payload),
                    "values": values,
                },
                separators=(",", ":"),
            ),
            flush=True,
        )
        return

    def fahrenheit(celsius: float | int) -> float:
        return float(celsius) * 9 / 5 + 32

    def km_to_miles(km: float | int) -> float:
        return float(km) * 0.621371

    ui_parts = []
    if "temp_fet_filtered" in values:
        ui_parts.append(f"Controller={fahrenheit(values['temp_fet_filtered']):.1f}F")
    if "temp_motor_filtered" in values:
        ui_parts.append(f"Motor={fahrenheit(values['temp_motor_filtered']):.1f}F")
    if "Speed" in values:
        ui_parts.append(f"Speed={values['Speed']:.2f} mph")
    if "Input_V" in values:
        ui_parts.append(f"Battery={values['Input_V']:.1f}V")
    if "ODO" in values:
        ui_parts.append(f"ODO={km_to_miles(values['ODO']):.1f} mi")
        ui_parts.append(f"ODO_km={values['ODO']}")

    keys = [
        "Input_V",
        "batteryPercentage",
        "Speed",
        "rpm",
        "temp_motor_filtered",
        "temp_fet_filtered",
        "reset_avg_input_current",
        "reset_avg_motor_current",
        "duty cycle",
        "Throttle",
        "Cadence Torque",
        "Human Power",
        "Assist Level",
        "Race/Street Mode",
        "Mode",
        "fault",
    ]
    parts = [f"layout={layout_name}", f"payload_len={len(raw_payload)}", *ui_parts]
    output_keys = values.keys() if all_fields else keys
    for key in output_keys:
        if key in values:
            parts.append(f"{key}={values[key]}")
    print(" | ".join(parts), flush=True)


def print_config_decoded(
    layout_name: str,
    response_command: int,
    values: dict[str, bool | float | int],
    raw_payload: bytes,
    *,
    json_output: bool,
) -> None:
    if json_output:
        print(
            json.dumps(
                {
                    "type": "config",
                    "layout": layout_name,
                    "command": response_command,
                    "command_name": command_name(response_command),
                    "payload_len": len(raw_payload),
                    "values": {
                        key: {
                            "value": value,
                            "label": enum_label(key, value),
                            "display": format_config_value(key, value),
                        }
                        for key, value in values.items()
                    },
                },
                separators=(",", ":"),
            ),
            flush=True,
        )
        return

    print(
        " | ".join(
            [
                "type=config",
                f"layout={layout_name}",
                f"command={response_command} ({command_name(response_command)})",
                f"payload_len={len(raw_payload)}",
            ]
        ),
        flush=True,
    )
    key_width = max(len(key) for key in values)
    for key, value in values.items():
        print(f"  {key:<{key_width}}  {format_config_value(key, value)}", flush=True)


def send(proc: subprocess.Popen[str], command: str) -> None:
    assert proc.stdin is not None
    proc.stdin.write(command + "\n")
    proc.stdin.flush()


def load_saved_device() -> dict[str, str] | None:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Ignoring unreadable local settings file {LOCAL_SETTINGS}: {exc}", file=sys.stderr)
        return None

    address = data.get("address")
    address_type = data.get("address_type", "random")
    if isinstance(address, str) and address and address_type in {"public", "random"}:
        return {"address": address, "address_type": address_type}
    return None


def save_device(address: str, address_type: str) -> None:
    data = {
        "device_name": DEVICE_NAME,
        "address": address,
        "address_type": address_type,
    }
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.chmod(SETTINGS_PATH, 0o600)


def bluetoothctl(*args: str, timeout: int = 30) -> str:
    proc = subprocess.run(
        ["bluetoothctl", *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return proc.stdout


def discover_cycmotor(scan_seconds: int) -> list[dict[str, str]]:
    bluetoothctl("--timeout", str(scan_seconds), "scan", "on", timeout=scan_seconds + 5)
    devices_output = bluetoothctl("devices", timeout=10)
    info_by_address: dict[str, dict[str, str]] = {}
    pattern = re.compile(r"^Device\s+([0-9A-Fa-f:]{17})\s+(.+)$")

    for line in devices_output.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        address, name = match.groups()
        if name.strip() != DEVICE_NAME:
            continue
        info = bluetoothctl("info", address, timeout=10)
        first_line = info.splitlines()[0] if info.splitlines() else ""
        address_type = "random" if "(random)" in first_line else "public"
        info_by_address[address.upper()] = {
            "address": address.upper(),
            "address_type": address_type,
            "name": name.strip(),
        }

    return sorted(info_by_address.values(), key=lambda item: item["address"])


def choose_device(scan_seconds: int, force_scan: bool) -> dict[str, str]:
    if not force_scan:
        saved = load_saved_device()
        if saved:
            print(f"Using saved {DEVICE_NAME} device from {LOCAL_SETTINGS}", file=sys.stderr)
            return saved

    devices = discover_cycmotor(scan_seconds)
    if not devices:
        raise RuntimeError(f"No BLE devices named {DEVICE_NAME} found")

    if len(devices) == 1:
        selected = devices[0]
        save_device(selected["address"], selected["address_type"])
        print(f"Saved discovered {DEVICE_NAME} device to {LOCAL_SETTINGS}", file=sys.stderr)
        return selected

    print(f"Found multiple {DEVICE_NAME} devices:", file=sys.stderr)
    for index, device in enumerate(devices, start=1):
        print(f"  {index}. {device['address']} ({device['address_type']})", file=sys.stderr)

    while True:
        choice = input(f"Select {DEVICE_NAME} device [1-{len(devices)}]: ").strip()
        try:
            selected = devices[int(choice) - 1]
        except (ValueError, IndexError):
            print("Invalid selection", file=sys.stderr)
            continue
        save_device(selected["address"], selected["address_type"])
        return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", help="BLE address; overrides discovery/local settings")
    parser.add_argument("--addr-type", default="random", choices=["public", "random"])
    parser.add_argument("--scan", action="store_true", help="ignore saved settings and scan for CYCMOTOR")
    parser.add_argument("--scan-seconds", type=int, default=15)
    parser.add_argument("--interval", type=float, default=1.0, help="GET_VALUES polling interval")
    parser.add_argument("--command", type=lambda x: int(x, 0), default=GET_VALUES)
    parser.add_argument("--count", type=int, default=0, help="stop after N decoded telemetry frames")
    parser.add_argument("--packet-count", type=int, default=0, help="stop after N validated VESC packets")
    parser.add_argument("--raw", action="store_true", help="print raw validated VESC payloads")
    parser.add_argument(
        "--layout",
        default="auto",
        choices=["auto", "cyc_uart", "xSeries_uart"],
        help="telemetry layout to decode; auto chooses the largest layout that fits",
    )
    parser.add_argument("--all-fields", action="store_true", help="print every decoded field from the selected layout")
    parser.add_argument("--json", action="store_true", help="print decoded telemetry as JSON lines with every field")
    args = parser.parse_args()

    if args.address:
        device = {"address": args.address.upper(), "address_type": args.addr_type}
    else:
        device = choose_device(args.scan_seconds, args.scan)

    all_layouts = {
        "cyc_uart": load_layout("cyc_uart.json"),
        "xSeries_uart": load_layout("xSeries_uart.json"),
    }
    layouts = all_layouts if args.layout == "auto" else {args.layout: all_layouts[args.layout]}
    request = encode_packet(bytes([args.command])).hex()

    proc = subprocess.Popen(
        ["gatttool", "-b", device["address"], "-t", device["address_type"], "-I"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    def stop(_signum=None, _frame=None) -> None:
        try:
            send(proc, f"char-write-req {NUS_CCC_HANDLE} 0000")
            send(proc, "disconnect")
            send(proc, "exit")
        finally:
            proc.terminate()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    send(proc, "connect")
    time.sleep(2)
    send(proc, f"char-write-req {NUS_CCC_HANDLE} 0100")
    time.sleep(0.5)

    rx = bytearray()
    next_poll = 0.0
    notify_re = re.compile(r"value:\s*([0-9a-fA-F ]+)")
    decoded_count = 0
    packet_count = 0
    warned_lengths: set[int] = set()

    assert proc.stdout is not None
    while proc.poll() is None:
        now = time.monotonic()
        if now >= next_poll:
            send(proc, f"char-write-req {NUS_TX_HANDLE} {request}")
            next_poll = now + args.interval

        readable, _, _ = select.select([proc.stdout], [], [], 0.2)
        if not readable:
            continue
        line = proc.stdout.readline()
        if not line:
            continue
        if "Notification handle" not in line:
            if "Error" in line or "failed" in line.lower():
                print(line.strip(), file=sys.stderr)
            continue
        match = notify_re.search(line)
        if not match:
            continue
        rx.extend(bytes.fromhex(match.group(1)))
        for payload in iter_packets(rx):
            packet_count += 1
            if args.raw:
                print(f"payload: {payload.hex(' ')}", flush=True)
            decoded = decode_telemetry(payload, layouts)
            if decoded:
                print_decoded(
                    decoded[0],
                    decoded[1],
                    payload,
                    all_fields=args.all_fields,
                    json_output=args.json,
                )
                decoded_count += 1
                if args.count and decoded_count >= args.count:
                    stop()
                    return 0
            else:
                config_decoded = decode_config(payload)
                if config_decoded:
                    print_config_decoded(
                        config_decoded[0],
                        config_decoded[1],
                        config_decoded[2],
                        payload,
                        json_output=args.json,
                    )
                elif args.layout != "auto" and len(payload) not in warned_lengths:
                    warned_lengths.add(len(payload))
                    required = layout_size(layouts[args.layout])
                    data_len, stripped_data_len = payload_decode_lengths(payload)
                    detail = f"payload_len={len(payload)}, data_len={data_len}"
                    if stripped_data_len is not None:
                        detail += f", command_stripped_data_len={stripped_data_len}"
                    print(
                        f"validated packet does not fit layout={args.layout}: "
                        f"{detail}, required_data_len={required}",
                        file=sys.stderr,
                        flush=True,
                    )
            if args.packet_count and packet_count >= args.packet_count:
                stop()
                return 0

    return proc.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
