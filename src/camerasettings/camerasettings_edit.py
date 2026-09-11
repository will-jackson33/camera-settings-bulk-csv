"""Apply an edit sheet to a settings file: match every row to its camera, check every value, and
produce the edited copy with a log of each change - or nothing at all, with every refusal listed,
when any row cannot be applied.

All or nothing, because half an edit is how the wrong name lands on the wrong camera. The sheet
contract: one key column (MacAddress, IpAddress or Camera), every other column
named as in the CSV, blank meaning no change.
"""

from __future__ import annotations

import copy
import datetime
from collections import Counter
from dataclasses import dataclass, field

import camerasettings_columns as columns
import camerasettings_csvfile as csvfile
from camerasettings_sheet import EditSheet, SheetRow

KEY_COLUMNS = ("MacAddress", "IpAddress", "Camera")
_TABLE = columns.camerasettings_columns_byName()


@dataclass
class EditChange:
    camera: str  # the label: C-numbers or name, then address
    mac: str
    column: str
    head: int | None
    old: str
    new: str


@dataclass
class EditRefusal:
    row: int  # the sheet row, or 0 when the sheet as a whole is the problem
    key: str
    reason: str


@dataclass
class EditResult:
    settings: csvfile.SettingsFile
    key_column: str
    changes: list[EditChange] = field(default_factory=list)
    refusals: list[EditRefusal] = field(default_factory=list)
    already: int = 0  # cells that asked for the value the camera already had
    rows: int = 0
    passwords: int = 0  # password cells written - the output is then a credential file

    @property
    def ok(self) -> bool:
        return not self.refusals


def _sheet_problems(sheet: EditSheet, settings: csvfile.SettingsFile, allow_passwords: bool) -> tuple[str, list[EditRefusal]]:
    """The key column and every reason the sheet as a whole cannot be applied."""
    keys = [name for name in KEY_COLUMNS if name in sheet.columns]
    refusals: list[EditRefusal] = []
    if len(keys) != 1:
        found = ", ".join(keys) if keys else "none of them"
        refusals.append(EditRefusal(0, "", f"the sheet needs exactly one key column - MacAddress, IpAddress or Camera - and has {found}"))
    key = keys[0] if len(keys) == 1 else ""
    for name in sheet.columns:
        if name == key:
            continue
        refusal = _column_problem(name, settings, allow_passwords)
        if refusal:
            refusals.append(EditRefusal(0, name, refusal))
    if key and len(sheet.columns) == 1:
        refusals.append(EditRefusal(0, key, "the sheet has the key column and nothing to change"))
    return key, refusals


def _column_problem(name: str, settings: csvfile.SettingsFile, allow_passwords: bool) -> str:
    column = _TABLE.get(name)
    if column is None:
        near = [known for known in _TABLE if known.lower() == name.lower()]
        hint = f" - did you mean {near[0]}?" if near else ". The names are the file's own column headings"
        return f"no such column in a settings file: {name}{hint}"
    if column.role is columns.ColumnRole.MARKER or column.role is columns.ColumnRole.KEY:
        return f"{name} is the structure of the file, not a setting"
    if column.role is columns.ColumnRole.IDENTITY:
        return f"{name} is read-only: CCT ignores it on import"
    if column.role is columns.ColumnRole.ADMIN_USER:
        return f"{name} cannot change through the file: CCT refuses a different admin user"
    if column.role is columns.ColumnRole.PASSWORD and not allow_passwords:
        return f"{name} sets the camera's password on import. Run again with --allow-passwords if that is the intention"
    present = settings.device_columns if column.row == csvfile.DEVICE else settings.analytics_columns
    if name not in present:
        return f"this settings file has no {name} column - an older CCT wrote it"
    return ""


def _normalize_mac(text: str) -> str:
    return text.strip().upper().replace(":", "-")


class _Index:
    """Every way a row may name a camera, built once."""

    def __init__(self, settings: csvfile.SettingsFile):
        self.settings = settings
        self.by_mac = settings.by_mac()
        self.by_ip: dict[str, list[csvfile.SettingsCamera]] = {}
        self.by_number: dict[str, list[csvfile.SettingsCamera]] = {}
        self.by_name: dict[str, list[csvfile.SettingsCamera]] = {}
        for camera in settings.cameras:
            self.by_ip.setdefault(settings.value(camera, csvfile.IP_COLUMN), []).append(camera)
            name = settings.value(camera, csvfile.NAME_COLUMN)
            self.by_name.setdefault(name.lower(), []).append(camera)
            for number in csvfile.camerasettings_csvfile_cameraNumbers(name):
                self.by_number.setdefault(number, []).append(camera)

    def find(self, key_column: str, text: str) -> list[csvfile.SettingsCamera]:
        if key_column == "MacAddress":
            camera = self.by_mac.get(_normalize_mac(text))
            return [camera] if camera else []
        if key_column == "IpAddress":
            try:
                address = columns.camerasettings_columns_normalize(_TABLE["IpAddress"], text)
            except ValueError:
                return []
            return self.by_ip.get(address, [])
        wanted = text.strip()
        exact = self.by_name.get(wanted.lower(), []) or self.by_name.get(csvfile.camerasettings_csvfile_bare(wanted).lower(), [])
        if exact:
            return exact
        return self.by_number.get(wanted.upper(), [])


def _match(index: _Index, key_column: str, row: SheetRow) -> tuple[csvfile.SettingsCamera | None, str]:
    text = row.values.get(key_column, "")
    if not text:
        return None, f"row {row.number} has no {key_column}"
    found = index.find(key_column, text)
    if not found:
        return None, f"no camera matches {key_column} {text}"
    if len(found) > 1:
        labels = "; ".join(csvfile.camerasettings_csvfile_label(index.settings, camera) for camera in found)
        return None, f"{text} matches more than one camera: {labels}. Use the MacAddress"
    return found[0], ""


def _apply_row(result: EditResult, camera: csvfile.SettingsCamera, row: SheetRow, key_column: str) -> None:
    settings = result.settings
    label = csvfile.camerasettings_csvfile_label(settings, camera)
    mac = settings.mac(camera)
    for name, text in row.values.items():
        if name == key_column or text == "":
            continue
        column = _TABLE[name]
        try:
            new = columns.camerasettings_columns_normalize(column, text)
        except ValueError as error:
            result.refusals.append(EditRefusal(row.number, row.values[key_column], str(error)))
            continue
        if column.row == csvfile.DEVICE:
            position = settings.device_index(name)
            old = csvfile.camerasettings_csvfile_bare(camera.device[position])
            if old == new:
                result.already += 1
                continue
            camera.device[position] = csvfile.camerasettings_csvfile_quoted(new, column.quote)
            result.changes.append(EditChange(label, mac, name, None, old, new))
            if column.role is columns.ColumnRole.PASSWORD:
                result.passwords += 1
        else:
            position = settings.analytics_index(name)
            for head, fields in enumerate(camera.analytics, 1):
                old = fields[position]
                if old == new:
                    result.already += 1
                    continue
                fields[position] = new
                result.changes.append(EditChange(label, mac, name, head, old, new))


def camerasettings_edit_apply(settings: csvfile.SettingsFile, sheet: EditSheet, allow_passwords: bool = False) -> EditResult:
    """Apply the sheet to a copy of the settings and report every change and every refusal.

    The original settings object is never touched. The result's `ok` is False when anything was
    refused, and then the edited copy must not be written - the refusals are the whole answer.
    """
    key, refusals = _sheet_problems(sheet, settings, allow_passwords)
    result = EditResult(copy.deepcopy(settings), key, refusals=refusals, rows=len(sheet.rows))
    if refusals:
        return result
    index = _Index(result.settings)
    used: dict[str, int] = {}
    for row in sheet.rows:
        camera, reason = _match(index, key, row)
        if camera is None:
            result.refusals.append(EditRefusal(row.number, row.values.get(key, ""), reason))
            continue
        mac = result.settings.mac(camera)
        if mac in used:
            result.refusals.append(EditRefusal(row.number, row.values[key], f"the same camera already appeared on row {used[mac]}"))
            continue
        used[mac] = row.number
        _apply_row(result, camera, row, key)
    return result


def camerasettings_edit_renderLog(result: EditResult, settings_name: str, sheet_name: str) -> str:
    """The edit log: what was asked, what changed, what was refused. Written beside the output."""
    per_column = Counter(f"{change.column}" for change in result.changes)
    cameras = len({change.mac for change in result.changes})
    lines = [
        f"Edit log - {sheet_name} applied to {settings_name} - {datetime.datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Key column         : {result.key_column or '-'}",
        f"Rows in the sheet  : {result.rows}",
        f"Cameras changed    : {cameras}",
        f"Changes            : {len(result.changes)}"
        + (f"   ({', '.join(f'{name} {count}' for name, count in per_column.most_common())})" if per_column else ""),
        f"Already as asked   : {result.already}",
        f"Refused            : {len(result.refusals)}",
        "",
    ]
    if result.passwords:
        lines += [
            f"WARNING: {result.passwords} password cells were written. The edited file is a credential list -",
            "handle it as one, and never commit or forward it beyond the import.",
            "",
        ]
    if result.refusals:
        lines.append("REFUSED - nothing was written. Fix the sheet and run again:")
        for refusal in result.refusals:
            where = f"row {refusal.row}" if refusal.row else "sheet"
            key = f"  {refusal.key}" if refusal.key else ""
            lines.append(f"  {where:<8}{key:<22}  {refusal.reason}")
        lines.append("")
    if result.changes:
        lines.append("CHANGES" if result.ok else "CHANGES THAT WOULD HAVE BEEN MADE")
        for change in result.changes:
            head = f"  head {change.head}" if change.head is not None else ""
            lines.append(f"  {change.camera:<42}{change.column:<26}{head}  {change.old!r} -> {change.new!r}")
        lines.append("")
    return "\n".join(lines)
