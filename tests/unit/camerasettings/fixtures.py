"""Settings files built to CCT's own shape, and the real one when a site export sits beside the
scripts. Client data never enters the repository: the real file is read out of a gitignored zip
and the tests that need it skip when there is none."""

from __future__ import annotations

import zipfile
from pathlib import Path

import camerasettings_columns as columns

ROOT = Path(__file__).resolve().parents[3]

DEVICE_HEADER = "\t".join(c.name for c in columns.DEVICE_COLUMNS)
ANALYTICS_HEADER = "\t".join(c.name for c in columns.ANALYTICS_COLUMNS)


def device_row(mac: str, name: str, ip: str, *, location: str = "acc/", model: str = "6.0C-H5A-BO1-IR",
               heads: int = 1, quality: str = "6", resolution: str = "2592 x 1944") -> str:
    values = {
        "DeviceHeader": "Device", "MacAddress": mac, "Name": f'"{name}"', "Location": f'"{location}"',
        "SerialNumber": "'1000000" + mac[-2:] + "'", "FirmwareVersion": '"5.20.0.24"', "Model": model,
        "Manufacturer": "Avigilon", "Date": "2026-09-09 12:53:00Z", "CameraLedDisabled": "False",
        "DHCPEnabled": "True", "IpAddress": ip, "SubnetMask": "255.255.255.0",
        "DefaultGateway": ip.rsplit(".", 1)[0] + ".1", "Hostname": f"C6-0C-H5A-BO1-IR-{mac[-2:]}.AVIGILON",
        "AdminUserName": "administrator", "AdminPassword": "", "SecondaryAdminUserName": "",
        "SecondaryAdminPassword": "", "Encoding": "H264", "FlickerControl": "50Hz", "WDREnabled": "True",
        "ImageRate": "25", "Quality": quality, "MaxBitrate": "5000", "Resolution": resolution,
        "KeyframeInterval": "50", "NumberOfCameraHeads": str(heads), "CameraMode": "Full Feature",
        "NtpServerModeDhcp": "DHCP", "ManualNtpServer": "", "CertificateId": "default",
        "CertificateSubjectCommonName": f"AVIGILON-CAMERA-{mac[-2:]}", "EnableHttp": "True", "HttpPort": "80",
        "HttpsPort": "443", "EnableAnalyticsMetadata": "True", "EnableImageStabilization": "",
        "LegacyAnalyticsConfiguration": "True",
    }
    return "\t".join(values[c.name] for c in columns.DEVICE_COLUMNS)


def analytics_row(head: int, *, sensitivity: str = "8") -> str:
    values = {
        "AnalyticsHeader": "Analytics", "Head": str(head), "CameraType": "", "AnalyticsSceneMode": "0",
        "EnableNoiseFilter": "", "TamperSensitivity": sensitivity, "TamperTriggerDelay": "8",
        "EnableSelfLearning": "True", "VideoAnalyticsMode": "0", "EnableTamper": "True", "TamperThreshold": "",
        "": "",
    }
    return "\t".join(values[c.name] for c in columns.ANALYTICS_COLUMNS)


def sample_lines() -> list[str]:
    """Four cameras: two plain, one three-head multisensor, one with no C-number in its name."""
    return [
        DEVICE_HEADER,
        ANALYTICS_HEADER,
        device_row("00-18-85-00-00-01", "acc/C1061 - Loading dock", "10.20.19.128"),
        analytics_row(1),
        device_row("00-18-85-00-00-02", "acc/C1062 - Path to the lobby", "10.20.19.131", quality="10"),
        analytics_row(1),
        device_row("00-18-85-00-00-03", "acc/C1090, C1091, C1092 - Multisensor", "10.20.19.132", heads=3,
                   model="9C-H4A-3MH-180"),
        analytics_row(1),
        analytics_row(2),
        analytics_row(3),
        device_row("00-18-85-00-00-04", "acc/Back gate", "10.20.3.130"),
        analytics_row(1),
    ]


def sample_bytes(lines: list[str] | None = None) -> bytes:
    text = "\r\n".join(lines if lines is not None else sample_lines()) + "\r\n"
    return b"\xff\xfe" + text.encode("utf-16-le")


def real_export_bytes() -> bytes | None:
    """settings.csv from the newest site export zip beside the scripts, or None when there is none."""
    zips = sorted(ROOT.glob("*_ACC_Camera_Settings_*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips:
        return None
    with zipfile.ZipFile(zips[-1]) as archive:
        if "settings.csv" not in archive.namelist():
            return None
        return archive.read("settings.csv")
