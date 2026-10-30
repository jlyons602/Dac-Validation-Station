"""
report.py
Excel output. Each test writes its own workbook: Summary, Run_Info, then one tab per spec.
Charts are plain Excel line charts (no markers, no styling, no legend).
"""

from openpyxl import Workbook
from openpyxl.chart import ScatterChart, Reference, Series
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from limits import SPECS, judge

SUMMARY_COLS = ["Spec", "Condition", "Min", "Typ", "Max", "Measured", "Unit", "Result"]
HEADER_FILL = PatternFill("solid", fgColor="500000")      # A&M maroon
HEADER_FONT = Font(bold=True, color="FFFFFF")
RESULT_FILL = {"PASS": "C6EFCE", "FAIL": "FFC7CE", "WARN": "FFEB9C"}


def linfit(xs, ys):
    n = len(xs)
    sx, sy = sum(xs), sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    return slope, (sy - slope * sx) / n


def _num(v, nd=6):
    return round(v, nd) if isinstance(v, float) else v


def _style_header(ws, row, ncols):
    for j in range(1, ncols + 1):
        c = ws.cell(row=row, column=j)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT


def _chart(ws, tab, header_row, n):
    c = tab["chart"]
    ch = ScatterChart()
    ch.title = c["title"]
    ch.x_axis.title = c["x_title"]
    ch.y_axis.title = c["y_title"]
    ch.x_axis.delete = False
    ch.y_axis.delete = False
    ch.legend = None
    ch.height, ch.width = 8, 16
    x = Reference(ws, min_col=c["x"], min_row=header_row + 1, max_row=header_row + n)
    y = Reference(ws, min_col=c["y"], min_row=header_row + 1, max_row=header_row + n)
    s = Series(y, x)
    s.marker.symbol = "none"
    s.smooth = False
    ch.series.append(s)
    ws.add_chart(ch, f"{get_column_letter(len(tab['columns']) + 2)}2")


def _write_tab(wb, tab):
    ws = wb.create_sheet(tab["name"][:31])
    r = 1
    for label, value in tab.get("notes", []):
        ws.cell(row=r, column=1, value=label).font = Font(bold=True)
        ws.cell(row=r, column=2, value=_num(value))
        r += 1
    if tab.get("columns"):
        if r > 1:
            r += 1
        header = r
        for j, col in enumerate(tab["columns"], start=1):
            ws.cell(row=header, column=j, value=col)
        _style_header(ws, header, len(tab["columns"]))
        for i, row in enumerate(tab["rows"], start=1):
            for j, val in enumerate(row, start=1):
                ws.cell(row=header + i, column=j, value=_num(val))
        if tab.get("chart") and tab["rows"]:
            _chart(ws, tab, header, len(tab["rows"]))
    ws.column_dimensions["A"].width = 34
    for col in range(2, 10):
        ws.column_dimensions[get_column_letter(col)].width = 15


def _summary_sheet(ws, specs, extra_col=None):
    head = SUMMARY_COLS + ([extra_col[0]] if extra_col else [])
    ws.append(head)
    _style_header(ws, 1, len(head))
    for sid, s in SPECS.items():
        if sid not in specs:
            continue
        val = specs[sid]
        result = judge(sid, val)
        row = [s["name"], s["cond"], s["min"], s["typ"], s["max"],
               _num(val, 5), s["unit"], result]
        if extra_col:
            row.append(extra_col[1].get(sid, ""))
        ws.append(row)
        if result in RESULT_FILL:
            ws.cell(row=ws.max_row, column=8).fill = PatternFill("solid", fgColor=RESULT_FILL[result])
    widths = [36, 50, 8, 8, 8, 12, 8, 9, 50]
    for i, w in enumerate(widths[:len(head)], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _info_sheet(wb, meta):
    info = wb.create_sheet("Run_Info")
    for label, value in meta:
        info.append([label, value])
        info.cell(row=info.max_row, column=1).font = Font(bold=True)
    info.column_dimensions["A"].width = 26
    info.column_dimensions["B"].width = 60


def write_workbook(path, meta, specs, tabs):
    wb = Workbook()
    sm = wb.active
    sm.title = "Summary"
    _summary_sheet(sm, specs)
    _info_sheet(wb, meta)
    for tab in tabs:
        _write_tab(wb, tab)
    wb.save(path)


def write_overall(path, meta, specs, spec_files):
    """One summary of every spec from a suite run, with the file each result came from."""
    wb = Workbook()
    sm = wb.active
    sm.title = "Summary"
    _summary_sheet(sm, specs, extra_col=("File", spec_files))
    _info_sheet(wb, meta)
    wb.save(path)
