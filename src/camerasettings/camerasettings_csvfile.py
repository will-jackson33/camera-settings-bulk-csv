"""Read and write the CCT settings CSV exactly as CCT does, so a file that goes through this module
untouched comes out byte for byte the same.

The shape: UTF-16 LE with a byte-order mark, CRLF, tab-separated; header lines until the
first row whose first field is `Device` or `Analytics`; then one `Device` row per camera followed by
one `Analytics` row per head. Rows are matched by MacAddress. Nothing here knows what a column means -
that is camerasettings_columns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

BOM = b"\xff\xfe"
DEVICE = "Device"
ANALYTICS = "Analytics"
MAC_COLUMN = "MacAddress"
NAME_COLUMN = "Name"
IP_COLUMN = "IpAddress"

_CAMERA_NUMBER = re.compile(r"\b[Cc]\d+\b")


class SettingsFileError(ValueError):
    """The file is not a CCT settings CSV, or not one this module can hand back unchanged."""


@dataclass
class SettingsCamera:
    """One camera: its Device row and the Analytics row of each head, as lists of raw fields."""

    device: list[str]
    analytics: list[list[str]] = field(default_factory=list)
    line: int = 0


@dataclass
class SettingsFile:
    header: list[str]
    device_columns: list[str]
    analytics_columns: list[str]
    cameras: list[SettingsCamera]
    newline: str = "\r\n"
    trailing_newline: bool = True

    def device_index(self, column: str) -> int:
        """Position of a Device column in this file, from its header rather than from assumption."""
        try:
            return self.device_columns.index(column)
        except ValueError as error:
            raise SettingsFileError(f"the file has no Device column named {column}") from error

    def analytics_index(self, column: str) -> int:
        try:
            return self.analytics_columns.index(column)
        except ValueError as error:
            raise SettingsFileError(f"the file has no Analytics column named {column}") from error

    def mac(self, camera: SettingsCamera) -> str:
        return camera.device[self.device_index(MAC_COLUMN)].upper()

    def by_mac(self) -> dict[str, SettingsCamera]:
        return {self.mac(camera): camera for camera in self.cameras}

    def value(self, camera: SettingsCamera, column: str) -> str:
        """A Device value without CCT's quotes."""
        return camerasettings_csvfile_bare(camera.device[self.device_index(column)])


def camerasettings_csvfile_bare(value: str) -> str:
    """The value without the one pair of quotes CCT wraps some columns in."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def camerasettings_csvfile_quoted(value: str, quote: str) -> str:
    """The value wrapped the way CCT writes that column."""
    return f"{quote}{value}{quote}" if quote else value


def camerasettings_csvfile_cameraNumbers(name: str) -> tuple[str, ...]:
    """The C-numbers a camera goes by, read from the front of its name.

    Naming convention: `acc/C1061 - Loading dock ...` is C1061; a multisensor named
    `acc/C1090, C1091, C1092 - Multisensor` answers to all three. Anything after the first ` - `
    is description and is not searched, so `CP2` in a description never becomes a number.
    """
    bare = camerasettings_csvfile_bare(name)
    if bare.lower().startswith("acc/"):
        bare = bare[4:]
    front = bare.split(" - ", 1)[0]
    return tuple(number.upper() for number in _CAMERA_NUMBER.findall(front))


def camerasettings_csvfile_label(settings: SettingsFile, camera: SettingsCamera) -> str:
    """How a camera is named in logs and reports: its C-numbers, or its name, then its address."""
    name = settings.value(camera, NAME_COLUMN)
    numbers = camerasettings_csvfile_cameraNumbers(name)
    who = ", ".join(numbers) if numbers else name
    return f"{who} ({settings.value(camera, IP_COLUMN)})"


def _split_lines(data: bytes, source: str) -> tuple[list[str], str, bool]:
    """The file's lines, its newline, and whether it ends with one."""
    if not data.startswith(BOM):
        raise SettingsFileError(f"{source} is not a CCT settings file: it does not start with the UTF-16 byte-order mark")
    text = data[len(BOM):].decode("utf-16-le")
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)
    trailing = lines[-1] == ""
    if trailing:
        lines.pop()
    return lines, newline, trailing


def _read_header(lines: list[str], source: str) -> tuple[list[str], list[str], list[str]]:
    """The header lines - everything before the first Device or Analytics row - and the two column lists."""
    header: list[str] = []
    device_columns: list[str] = []
    analytics_columns: list[str] = []
    for line in lines:
        fields = line.split("\t")
        if fields[0] in (DEVICE, ANALYTICS):
            break
        header.append(line)
        if fields[0] == "DeviceHeader":
            device_columns = fields
        elif fields[0] == "AnalyticsHeader":
            analytics_columns = fields
    if not device_columns or MAC_COLUMN not in device_columns:
        raise SettingsFileError(f"{source} has no DeviceHeader line with a {MAC_COLUMN} column")
    if not analytics_columns:
        raise SettingsFileError(f"{source} has no AnalyticsHeader line")
    return header, device_columns, analytics_columns


def _check_width(fields: list[str], columns: list[str], kind: str, number: int, source: str) -> None:
    if len(fields) != len(columns):
        raise SettingsFileError(
            f"{source} line {number}: {kind} row with {len(fields)} fields where the header has {len(columns)}"
        )


def camerasettings_csvfile_parse(data: bytes, source: str = "settings.csv") -> SettingsFile:
    """Parse the bytes of a CCT settings CSV.

    Raises SettingsFileError, naming the line, for anything CCT would not have written: a missing
    byte-order mark, a row with the wrong number of fields, an Analytics row before any Device row,
    the same MAC twice, or a line that is neither.
    """
    lines, newline, trailing = _split_lines(data, source)
    header, device_columns, analytics_columns = _read_header(lines, source)
    mac_index = device_columns.index(MAC_COLUMN)
    cameras: list[SettingsCamera] = []
    seen: dict[str, int] = {}
    current: SettingsCamera | None = None
    for number, line in enumerate(lines[len(header):], len(header) + 1):
        fields = line.split("\t")
        if fields[0] == DEVICE:
            _check_width(fields, device_columns, "a Device", number, source)
            mac = fields[mac_index].upper()
            if mac in seen:
                raise SettingsFileError(f"{source} line {number}: MAC address {mac} already appeared on line {seen[mac]}")
            seen[mac] = number
            current = SettingsCamera(device=fields, line=number)
            cameras.append(current)
        elif fields[0] == ANALYTICS:
            if current is None:
                raise SettingsFileError(f"{source} line {number}: an Analytics row before any Device row")
            _check_width(fields, analytics_columns, "an Analytics", number, source)
            current.analytics.append(fields)
        else:
            raise SettingsFileError(f"{source} line {number}: expected a Device or Analytics row, found '{line[:40]}'")
    return SettingsFile(header, device_columns, analytics_columns, cameras, newline, trailing)


def camerasettings_csvfile_read(path: Path) -> SettingsFile:
    return camerasettings_csvfile_parse(path.read_bytes(), path.name)


def camerasettings_csvfile_render(settings: SettingsFile) -> bytes:
    """The file as CCT would write it: header, then each camera's rows, UTF-16 with the mark."""
    lines = list(settings.header)
    for camera in settings.cameras:
        lines.append("\t".join(camera.device))
        lines.extend("\t".join(row) for row in camera.analytics)
    text = settings.newline.join(lines)
    if settings.trailing_newline:
        text += settings.newline
    return BOM + text.encode("utf-16-le")


def camerasettings_csvfile_write(settings: SettingsFile, path: Path) -> None:
    path.write_bytes(camerasettings_csvfile_render(settings))
