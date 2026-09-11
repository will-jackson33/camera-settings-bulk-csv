"""The CCT settings CSV column by column, as data: what each column holds, how CCT quotes it, which
values it accepts, and whether an edit may touch it.

This module is the file-format contract made executable, so the editor and the compare tool can
never disagree with it. The camera-specific limits - which resolutions an encoder offers,
the frame-rate range - are not here because the file does not carry them: CCT checks those against
the camera at import.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class ColumnRole(Enum):
    MARKER = "marker"  # the row's first field, and Head: structure, never a setting
    KEY = "key"  # MacAddress - what a row is matched by
    IDENTITY = "identity"  # exported for the record, ignored by import
    APPLIED = "applied"  # written to the camera by import
    ADMIN_USER = "adminUser"  # must match the camera's own; import refuses a change
    PASSWORD = "password"  # noqa: S105 - a role name, not a credential; a value here sets the camera's password on import


class ColumnKind(Enum):
    TEXT = "text"
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    IP = "ip"
    RESOLUTION = "resolution"
    CHOICE = "choice"


@dataclass(frozen=True)
class SettingsColumn:
    name: str
    row: str  # "Device" or "Analytics"
    role: ColumnRole
    kind: ColumnKind = ColumnKind.TEXT
    quote: str = ""  # '"' or "'" when CCT writes the value inside quotes
    choices: tuple[str, ...] = ()
    low: int | None = None
    high: int | None = None


CAMERA_MODES = (
    "Full Feature",
    "High Framerate",
    "No Video Analytics",
    "No Smart Analytics",
    "Dynamic Privacy Masks",
    "Dewarp Streaming 90 x 4",
    "Dewarp Streaming 120 x 3",
    "Dewarp Streaming 180 x 2",
    "None",
)

_D = "Device"
_A = "Analytics"
_R = ColumnRole
_K = ColumnKind

DEVICE_COLUMNS: tuple[SettingsColumn, ...] = (
    SettingsColumn("DeviceHeader", _D, _R.MARKER),
    SettingsColumn("MacAddress", _D, _R.KEY),
    SettingsColumn("Name", _D, _R.APPLIED, quote='"'),
    SettingsColumn("Location", _D, _R.APPLIED, quote='"'),
    SettingsColumn("SerialNumber", _D, _R.IDENTITY, quote="'"),
    SettingsColumn("FirmwareVersion", _D, _R.IDENTITY, quote='"'),
    SettingsColumn("Model", _D, _R.IDENTITY),
    SettingsColumn("Manufacturer", _D, _R.IDENTITY),
    SettingsColumn("Date", _D, _R.IDENTITY),
    SettingsColumn("CameraLedDisabled", _D, _R.APPLIED, _K.BOOL),
    SettingsColumn("DHCPEnabled", _D, _R.APPLIED, _K.BOOL),
    SettingsColumn("IpAddress", _D, _R.APPLIED, _K.IP),
    SettingsColumn("SubnetMask", _D, _R.APPLIED, _K.IP),
    SettingsColumn("DefaultGateway", _D, _R.APPLIED, _K.IP),
    SettingsColumn("Hostname", _D, _R.APPLIED),
    SettingsColumn("AdminUserName", _D, _R.ADMIN_USER),
    SettingsColumn("AdminPassword", _D, _R.PASSWORD),
    SettingsColumn("SecondaryAdminUserName", _D, _R.APPLIED),
    SettingsColumn("SecondaryAdminPassword", _D, _R.PASSWORD),
    SettingsColumn("Encoding", _D, _R.APPLIED, _K.CHOICE, choices=("JPEG", "MPEG4", "H264", "H265")),
    SettingsColumn("FlickerControl", _D, _R.APPLIED, _K.CHOICE, choices=("50Hz", "60Hz")),
    SettingsColumn("WDREnabled", _D, _R.APPLIED, _K.BOOL),
    SettingsColumn("ImageRate", _D, _R.APPLIED, _K.INT, low=1),
    SettingsColumn("Quality", _D, _R.APPLIED, _K.INT, low=1, high=20),
    SettingsColumn("MaxBitrate", _D, _R.APPLIED, _K.INT, low=1),
    SettingsColumn("Resolution", _D, _R.APPLIED, _K.RESOLUTION),
    SettingsColumn("KeyframeInterval", _D, _R.APPLIED, _K.INT, low=1),
    SettingsColumn("NumberOfCameraHeads", _D, _R.IDENTITY, _K.INT),
    SettingsColumn("CameraMode", _D, _R.APPLIED, _K.CHOICE, choices=CAMERA_MODES),
    SettingsColumn("NtpServerModeDhcp", _D, _R.APPLIED, _K.CHOICE, choices=("DHCP", "Manual", "None")),
    SettingsColumn("ManualNtpServer", _D, _R.APPLIED),
    SettingsColumn("CertificateId", _D, _R.APPLIED),
    SettingsColumn("CertificateSubjectCommonName", _D, _R.IDENTITY),
    SettingsColumn("EnableHttp", _D, _R.APPLIED, _K.BOOL),
    SettingsColumn("HttpPort", _D, _R.APPLIED, _K.INT, low=1, high=65535),
    SettingsColumn("HttpsPort", _D, _R.APPLIED, _K.INT, low=1, high=65535),
    SettingsColumn("EnableAnalyticsMetadata", _D, _R.APPLIED, _K.BOOL),
    SettingsColumn("EnableImageStabilization", _D, _R.APPLIED, _K.BOOL),
    SettingsColumn("LegacyAnalyticsConfiguration", _D, _R.IDENTITY, _K.BOOL),
)

ANALYTICS_COLUMNS: tuple[SettingsColumn, ...] = (
    SettingsColumn("AnalyticsHeader", _A, _R.MARKER),
    SettingsColumn("Head", _A, _R.MARKER, _K.INT),
    SettingsColumn("CameraType", _A, _R.APPLIED, _K.CHOICE, choices=("0", "1", "2", "3")),
    SettingsColumn("AnalyticsSceneMode", _A, _R.APPLIED, _K.CHOICE, choices=("0", "1", "2", "3", "4", "8")),
    SettingsColumn("EnableNoiseFilter", _A, _R.APPLIED, _K.BOOL),
    SettingsColumn("TamperSensitivity", _A, _R.APPLIED, _K.INT, low=1, high=10),
    SettingsColumn("TamperTriggerDelay", _A, _R.APPLIED, _K.INT, low=0),
    SettingsColumn("EnableSelfLearning", _A, _R.APPLIED, _K.BOOL),
    SettingsColumn("VideoAnalyticsMode", _A, _R.APPLIED, _K.CHOICE, choices=("0", "1", "2", "3", "4", "5")),
    SettingsColumn("EnableTamper", _A, _R.APPLIED, _K.BOOL),
    SettingsColumn("TamperThreshold", _A, _R.APPLIED, _K.FLOAT),
    SettingsColumn("", _A, _R.MARKER),  # FileHelpers' trailing placeholder - an empty column that must stay
)

# The meanings behind the coded analytics values, for reports. From CCT's StaticItemSources.
CAMERA_TYPES = {"0": "Colour", "1": "Black and White", "2": "Day and Night", "3": "Thermal"}
SCENE_MODES = {
    "0": "Outdoor",
    "1": "Large Indoor Area",
    "2": "Indoor Overhead",
    "3": "Outdoor High Sensitivity",
    "4": "Outdoor Long Range Night",
    "8": "Indoor Close-Up",
}
VIDEO_ANALYTICS_MODES = {
    "0": "VAL - video analytics",
    "1": "UMD - unusual motion detection",
    "2": "Tamper only",
    "3": "PTZ",
    "4": "Classified object detection",
    "5": "MSI tampering",
}

_IP = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")
_RESOLUTION = re.compile(r"^\s*(\d+)\s*[xX]\s*(\d+)\s*$")


def camerasettings_columns_byName() -> dict[str, SettingsColumn]:
    """Every named column, Device and Analytics, keyed by its exact header name."""
    return {c.name: c for c in DEVICE_COLUMNS + ANALYTICS_COLUMNS if c.name}


def _bool(column: SettingsColumn, text: str) -> str:
    if text.lower() in ("true", "false"):
        return "True" if text.lower() == "true" else "False"
    raise ValueError(f"{column.name} takes True or False, not '{text}'")


def _int(column: SettingsColumn, text: str) -> str:
    if not re.fullmatch(r"-?\d+", text):
        raise ValueError(f"{column.name} takes a whole number, not '{text}'")
    number = int(text)
    if column.low is not None and number < column.low:
        raise ValueError(f"{column.name} must be at least {column.low}, not {number}")
    if column.high is not None and number > column.high:
        raise ValueError(f"{column.name} must be at most {column.high}, not {number}")
    return str(number)


def _float(column: SettingsColumn, text: str) -> str:
    try:
        float(text)
    except ValueError as error:
        raise ValueError(f"{column.name} takes a number, not '{text}'") from error
    return text


def _ip(column: SettingsColumn, text: str) -> str:
    match = _IP.match(text)
    if not match or any(int(octet) > 255 for octet in match.groups()):
        raise ValueError(f"{column.name} takes an address like 10.20.3.128, not '{text}'")
    return ".".join(str(int(octet)) for octet in match.groups())


def _resolution(column: SettingsColumn, text: str) -> str:
    match = _RESOLUTION.match(text)
    if not match:
        raise ValueError(f"{column.name} takes width x height like 1920 x 1080, not '{text}'")
    return f"{int(match.group(1))} x {int(match.group(2))}"


def _choice(column: SettingsColumn, text: str) -> str:
    for choice in column.choices:
        if choice.lower() == text.lower():
            return choice
    raise ValueError(f"{column.name} takes one of {', '.join(column.choices)}, not '{text}'")


def _text(column: SettingsColumn, text: str) -> str:
    for forbidden, what in (("\t", "a tab"), ("\n", "a line break"), ("\r", "a line break")):
        if forbidden in text:
            raise ValueError(f"{column.name} cannot contain {what}")
    if column.quote and column.quote in text:
        raise ValueError(f"{column.name} cannot contain the {column.quote} character - CCT uses it to wrap the value")
    return text


_NORMALIZERS = {
    ColumnKind.BOOL: _bool,
    ColumnKind.INT: _int,
    ColumnKind.FLOAT: _float,
    ColumnKind.IP: _ip,
    ColumnKind.RESOLUTION: _resolution,
    ColumnKind.CHOICE: _choice,
    ColumnKind.TEXT: _text,
}


def camerasettings_columns_normalize(column: SettingsColumn, value: str) -> str:
    """Turn a value as a person typed it into the form the CSV holds, or explain why it cannot be.

    Returns the canonical text, without CCT's quotes - `True` not `TRUE`, `1920 x 1080` not
    `1920x1080`, `H264` not `h264`. Raises ValueError with a sentence a technician can act on.
    """
    return _NORMALIZERS[column.kind](column, value.strip())
