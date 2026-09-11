"""Compare two settings files - an export and its edited copy - and say exactly what differs.

The report is the proof that an edit did only what was intended, and import checks its verdict
before writing anything. Rows are matched by MacAddress. A camera present in only one file, a
difference in a column import ignores or refuses, or a change of structure - different columns,
a different number of heads - makes the pair unsafe to import, whatever else is right.
"""

from __future__ import annotations

import datetime
import difflib
import html
from collections import Counter
from dataclasses import dataclass, field

import camerasettings_columns as columns
import camerasettings_csvfile as csvfile

_TABLE = columns.camerasettings_columns_byName()
_ORDER = {column.name: n for n, column in enumerate(columns.DEVICE_COLUMNS + columns.ANALYTICS_COLUMNS) if column.name}
MASK = "(set)"


@dataclass
class CompareCell:
    camera: str
    mac: str
    ip: str
    column: str
    head: int | None
    old: str
    new: str


@dataclass
class CompareReport:
    original: str
    edited: str
    original_count: int = 0
    edited_count: int = 0
    only_original: list[str] = field(default_factory=list)
    only_edited: list[str] = field(default_factory=list)
    changes: list[CompareCell] = field(default_factory=list)
    forbidden: list[CompareCell] = field(default_factory=list)
    structure: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.only_original or self.only_edited or self.forbidden or self.structure)

    @property
    def cameras_changed(self) -> int:
        return len({cell.mac for cell in self.changes})

    def per_column(self) -> list[tuple[str, int]]:
        counts = Counter(cell.column for cell in self.changes)
        return sorted(counts.items(), key=lambda item: _ORDER.get(item[0], 999))

    def verdict(self) -> str:
        if self.ok:
            if not self.changes:
                return "NOTHING TO IMPORT - the two files hold the same settings"
            return f"SAFE TO IMPORT - {len(self.changes)} changes on {self.cameras_changed} cameras, all in columns import applies"
        reasons = []
        if self.only_original:
            reasons.append(f"{len(self.only_original)} cameras missing from the edited file")
        if self.only_edited:
            reasons.append(f"{len(self.only_edited)} cameras only in the edited file")
        if self.forbidden:
            reasons.append(f"{len(self.forbidden)} changes in columns import ignores or refuses")
        if self.structure:
            reasons.append(f"{len(self.structure)} structural differences")
        return "NOT SAFE TO IMPORT - " + ", ".join(reasons)


def _shown(column: str, value: str) -> str:
    """Passwords are never written into a report; that a value was set is enough."""
    definition = _TABLE.get(column)
    if definition is not None and definition.role is columns.ColumnRole.PASSWORD and value:
        return MASK
    return value


def _cell(settings: csvfile.SettingsFile, camera: csvfile.SettingsCamera, column: str, head: int | None,
          old: str, new: str) -> CompareCell:
    return CompareCell(csvfile.camerasettings_csvfile_label(settings, camera), settings.mac(camera),
                       settings.value(camera, csvfile.IP_COLUMN), column, head, _shown(column, old), _shown(column, new))


def _classify(report: CompareReport, cell: CompareCell) -> None:
    definition = _TABLE.get(cell.column)
    if definition is not None and definition.role is columns.ColumnRole.APPLIED:
        report.changes.append(cell)
    elif definition is not None and definition.role is columns.ColumnRole.PASSWORD:
        report.changes.append(cell)  # applied by import, and shown masked - the import gate asks twice
    else:
        report.forbidden.append(cell)


def _compare_camera(report: CompareReport, original: csvfile.SettingsFile, before: csvfile.SettingsCamera,
                    edited: csvfile.SettingsFile, after: csvfile.SettingsCamera) -> None:
    label = csvfile.camerasettings_csvfile_label(original, before)
    for column in original.device_columns:
        if column not in edited.device_columns:
            continue
        old = csvfile.camerasettings_csvfile_bare(before.device[original.device_index(column)])
        new = csvfile.camerasettings_csvfile_bare(after.device[edited.device_index(column)])
        if old != new:
            _classify(report, _cell(original, before, column, None, old, new))
    if len(before.analytics) != len(after.analytics):
        report.structure.append(f"{label}: {len(before.analytics)} heads in the original, {len(after.analytics)} in the edited file")
        return
    for head, (row_before, row_after) in enumerate(zip(before.analytics, after.analytics, strict=True), 1):
        for column in original.analytics_columns:
            if column not in edited.analytics_columns:
                continue
            old = row_before[original.analytics_index(column)]
            new = row_after[edited.analytics_index(column)]
            if old != new:
                _classify(report, _cell(original, before, column, head, old, new))


def camerasettings_compare_diff(original: csvfile.SettingsFile, edited: csvfile.SettingsFile,
                                original_name: str = "original", edited_name: str = "edited") -> CompareReport:
    """Every difference between the two files, sorted into what import will apply and what it will not."""
    report = CompareReport(original_name, edited_name, len(original.cameras), len(edited.cameras))
    if original.device_columns != edited.device_columns or original.analytics_columns != edited.analytics_columns:
        report.structure.append("the two files do not have the same columns - one was written by a different CCT, or by hand")
    before_by_mac = original.by_mac()
    after_by_mac = edited.by_mac()
    for mac, camera in before_by_mac.items():
        if mac not in after_by_mac:
            report.only_original.append(csvfile.camerasettings_csvfile_label(original, camera))
    for mac, camera in after_by_mac.items():
        if mac not in before_by_mac:
            report.only_edited.append(csvfile.camerasettings_csvfile_label(edited, camera))
    for mac, camera in before_by_mac.items():
        if mac in after_by_mac:
            _compare_camera(report, original, camera, edited, after_by_mac[mac])
    return report


def _sections(report: CompareReport) -> list[tuple[str, list[CompareCell]]]:
    grouped: dict[str, list[CompareCell]] = {}
    for cell in report.changes:
        grouped.setdefault(cell.column, []).append(cell)
    return sorted(grouped.items(), key=lambda item: _ORDER.get(item[0], 999))


def camerasettings_compare_renderText(report: CompareReport) -> str:
    """compare.log: the verdict and counts first, then every difference, grouped by setting."""
    lines = [
        f"Compare - {report.original} vs {report.edited} - {datetime.datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Verdict            : {report.verdict()}",
        f"Cameras            : {report.original_count} in the original, {report.edited_count} in the edited file, {report.cameras_changed} changed",
        f"Changes            : {len(report.changes)}"
        + (f"   ({', '.join(f'{name} {count}' for name, count in report.per_column())})" if report.changes else ""),
        "",
    ]
    if report.only_original:
        lines.append("MISSING FROM THE EDITED FILE - import would leave these cameras as they are, unproven:")
        lines += [f"  {label}" for label in report.only_original] + [""]
    if report.only_edited:
        lines.append("ONLY IN THE EDITED FILE - CCT will not find these cameras:")
        lines += [f"  {label}" for label in report.only_edited] + [""]
    if report.structure:
        lines.append("STRUCTURE:")
        lines += [f"  {item}" for item in report.structure] + [""]
    if report.forbidden:
        lines.append("CHANGES IMPORT IGNORES OR REFUSES - the edit touched what it must not:")
        for cell in report.forbidden:
            head = f"  head {cell.head}" if cell.head is not None else ""
            lines.append(f"  {cell.camera:<42}{cell.column:<26}{head}  {cell.old!r} -> {cell.new!r}")
        lines.append("")
    for column, cells in _sections(report):
        lines.append(f"{column} ({len(cells)})")
        for cell in cells:
            head = f"  head {cell.head}" if cell.head is not None else ""
            lines.append(f"  {cell.camera:<42}{head}  {cell.old!r} -> {cell.new!r}")
        lines.append("")
    return "\n".join(lines)


def _mark(old: str, new: str) -> tuple[str, str]:
    """The two values as HTML, the characters that differ wrapped in del and ins."""
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    left: list[str] = []
    right: list[str] = []
    for op, a0, a1, b0, b1 in matcher.get_opcodes():
        if op == "equal":
            left.append(html.escape(old[a0:a1]))
            right.append(html.escape(new[b0:b1]))
            continue
        if a1 > a0:
            left.append(f"<del>{html.escape(old[a0:a1])}</del>")
        if b1 > b0:
            right.append(f"<ins>{html.escape(new[b0:b1])}</ins>")
    return "".join(left), "".join(right)


_STYLE = """
:root { --ink: #1b2430; --muted: #5b6875; --rule: #d3dae2; --panel: #ffffff; --ground: #f2f4f7;
        --good: #1f7a45; --bad: #b3261e; --del: #fde2e0; --ins: #dcf5e3; }
@media (prefers-color-scheme: dark) {
  :root { --ink: #e6eaee; --muted: #98a3ae; --rule: #2b333c; --panel: #1a2027; --ground: #12161b;
          --good: #7fd39a; --bad: #ff8a80; --del: #4a1f1c; --ins: #1d3a27; } }
body { margin: 0; background: var(--ground); color: var(--ink); font: 15px/1.5 "Segoe UI", system-ui, sans-serif; }
main { max-width: 1100px; margin: 0 auto; padding: 32px 24px 64px; }
h1 { font-size: 24px; margin: 0 0 4px; } h2 { font-size: 18px; margin: 32px 0 8px; }
.meta { color: var(--muted); margin: 0 0 20px; }
.verdict { padding: 14px 18px; border-radius: 4px; background: var(--panel); border-left: 4px solid var(--good); font-weight: 600; }
.verdict.bad { border-left-color: var(--bad); }
table { border-collapse: collapse; width: 100%; background: var(--panel); border: 1px solid var(--rule); font-size: 14px; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--rule); vertical-align: top; }
th { font-size: 12px; letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted); font-weight: 500; }
tr:last-child td { border-bottom: 0; }
td.mono, th.mono { font-family: Consolas, "IBM Plex Mono", monospace; font-size: 13px; white-space: nowrap; }
td.val { font-family: Consolas, "IBM Plex Mono", monospace; font-size: 13px; }
del { background: var(--del); text-decoration: none; } ins { background: var(--ins); text-decoration: none; }
ul.flat { columns: 2; padding-left: 20px; }
.summary td:first-child { color: var(--muted); width: 220px; }
"""


def camerasettings_compare_renderHtml(report: CompareReport) -> str:
    """compare.html: the verdict, the counts, then one table per setting, old and new side by side."""
    esc = html.escape
    parts = [
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
        f"<title>Compare - {esc(report.original)} vs {esc(report.edited)}</title>",
        f"<style>{_STYLE}</style></head><body><main>",
        f"<h1>Compare - {esc(report.original)} vs {esc(report.edited)}</h1>",
        f"<p class=\"meta\">{datetime.datetime.now():%Y-%m-%d %H:%M}. Rows matched by MAC address. Old on the left, new on the right; what changed is marked.</p>",
        f"<div class=\"verdict{'' if report.ok else ' bad'}\">{esc(report.verdict())}</div>",
        "<h2>Summary</h2><table class=\"summary\">",
        f"<tr><td>Cameras in the original</td><td>{report.original_count}</td></tr>",
        f"<tr><td>Cameras in the edited file</td><td>{report.edited_count}</td></tr>",
        f"<tr><td>Cameras changed</td><td>{report.cameras_changed}</td></tr>",
        f"<tr><td>Changes</td><td>{len(report.changes)}</td></tr>",
    ]
    for column, count in report.per_column():
        parts.append(f"<tr><td>&nbsp;&nbsp;{esc(column)}</td><td>{count}</td></tr>")
    parts.append("</table>")

    def listing(title: str, items: list[str]) -> None:
        if items:
            parts.append(f"<h2>{esc(title)}</h2><ul class=\"flat\">" + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>")

    listing("Missing from the edited file - import would leave these cameras unproven", report.only_original)
    listing("Only in the edited file - CCT will not find these", report.only_edited)
    listing("Structure", report.structure)

    def table(title: str, cells: list[CompareCell]) -> None:
        with_head = any(cell.head is not None for cell in cells)
        parts.append(f"<h2>{esc(title)} ({len(cells)})</h2><table><tr><th>Camera</th><th class=\"mono\">IP</th>")
        if with_head:
            parts.append("<th>Head</th>")
        parts.append("<th>Old</th><th>New</th></tr>")
        for cell in cells:
            old, new = _mark(cell.old, cell.new)
            parts.append(f"<tr><td>{esc(cell.camera.rsplit(' (', 1)[0])}</td><td class=\"mono\">{esc(cell.ip)}</td>")
            if with_head:
                parts.append(f"<td>{cell.head if cell.head is not None else ''}</td>")
            parts.append(f"<td class=\"val\">{old}</td><td class=\"val\">{new}</td></tr>")
        parts.append("</table>")

    if report.forbidden:
        table("Changes import ignores or refuses - the edit touched what it must not", report.forbidden)
    for column, cells in _sections(report):
        table(column, cells)
    parts.append("</main></body></html>")
    return "\n".join(parts)
