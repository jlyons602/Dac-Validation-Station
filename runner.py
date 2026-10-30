"""
runner.py
Runs a list of test modules on one bench session. Each test saves its own Excel file,
then an overall SUMMARY file is written. Hardware is always shut down safely.

Each test module provides:
    NAME, TAG, DESCRIPTION, run(bench, ctx, res)
    optional: MANUAL_SETUP (text shown before the test), MANUAL_TEARDOWN (text shown after)
"""

import os
import traceback
from datetime import datetime
from hardware import Bench
from limits import SPECS, judge
from report import write_workbook, write_overall


class StopRequested(Exception):
    pass


class Context:
    """Passed to every test: logging, progress, stop checks, user prompts, and settings."""

    def __init__(self, settings, log, progress, stop_evt, confirm, result):
        self.settings = settings
        self.log = log
        self.progress = progress
        self.stop_evt = stop_evt
        self.confirm = confirm          # confirm(text) -> True/False
        self.result = result            # result(spec_id, value)

    def check(self):
        if self.stop_evt.is_set():
            raise StopRequested()


def _fmt(v):
    return f"{v:.5g}" if isinstance(v, float) else str(v)


def _path(settings, tag, stamp):
    os.makedirs(settings["folder"], exist_ok=True)
    name = settings["run_name"]
    suffix = f"_{stamp}" if settings["stamp"] else ""
    return os.path.join(settings["folder"], f"{name}_{tag}{suffix}.xlsx")


def _meta(settings, mod_name, started, status):
    return [("Test", mod_name), ("Run name", settings["run_name"]), ("Started", started),
            ("Part", settings.get("part_found", settings.get("part", "Auto"))),
            ("Status", status), ("VDD nominal (V)", settings["vdd"]),
            ("VDD SMU", settings["vdd_smu"]), ("VOUT SMU", settings["vout_smu"]),
            ("VOUT remote sense", settings["remote_sense"]),
            ("Static sweep mode", settings["sweep"]),
            ("I2C address", f"0x{settings.get('i2c_addr', 0x48):02X}"),
            ("I2C read-back", "OFF (write-only mode)" if settings.get("write_only") else "ON"),
            ("Temperature", "Room temperature")]


def run_module(mod, bench, ctx, stamp):
    ctx.log(f"\n=== {mod.NAME} ===")
    res = {"specs": {}, "tabs": []}
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "Complete"
    stop = False
    try:
        mod.run(bench, ctx, res)
    except StopRequested:
        status, stop = "Stopped by user", True
        ctx.log("Stopped by user")
    except Exception as e:
        status = f"Error: {e}"
        ctx.log(f"ERROR: {e}")
        ctx.log(traceback.format_exc())

    path = _path(ctx.settings, mod.TAG, stamp)
    try:
        write_workbook(path, _meta(ctx.settings, mod.NAME, started, status), res["specs"], res["tabs"])
        ctx.log(f"Saved: {path}")
    except Exception as e:
        ctx.log(f"Could not save {path} (is it open in Excel?): {e}")
    for sid, val in res["specs"].items():
        ctx.log(f"  {SPECS[sid]['name']}: {_fmt(val)} {SPECS[sid]['unit']}  [{judge(sid, val)}]")
        ctx.result(sid, val)
    return res, status, path, stop


def run_suite(mods, ctx):
    s = ctx.settings
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bench = Bench(s)
    all_specs, spec_files, statuses = {}, {}, []
    try:
        bench.open(ctx.log)
        s["part_found"] = bench.part.name
        for k, mod in enumerate(mods, start=1):
            if ctx.stop_evt.is_set():
                break
            ctx.progress("test", k, len(mods), mod.NAME)
            if s.get("write_only") and getattr(mod, "NEEDS_READ", False):
                statuses.append((mod.NAME, "Skipped (needs I2C read-back, write-only mode is on)"))
                ctx.log(f"Skipped: {mod.NAME} (needs I2C read-back)")
                continue
            setup = getattr(mod, "MANUAL_SETUP", None)
            if setup and not ctx.confirm(setup):
                statuses.append((mod.NAME, "Skipped by user"))
                ctx.log(f"Skipped: {mod.NAME}")
                continue
            try:
                bench.restore()
            except Exception as e:
                ctx.log(f"Could not reset the bench, stopping: {e}")
                statuses.append((mod.NAME, f"Not run: {e}"))
                break
            res, status, path, stop = run_module(mod, bench, ctx, stamp)
            statuses.append((mod.NAME, status))
            all_specs.update(res["specs"])
            for sid in res["specs"]:
                spec_files[sid] = os.path.basename(path)
            teardown = getattr(mod, "MANUAL_TEARDOWN", None)
            if teardown:
                ctx.confirm(teardown)
            if stop:
                break
    except Exception as e:
        ctx.log(f"ERROR: {e}")
        statuses.append(("Bench setup", f"Error: {e}"))
    finally:
        bench.close(ctx.log)
        if all_specs:
            meta = [("Run name", s["run_name"]), ("Started", started), ("Part", bench.part.name),
                    ("VDD nominal (V)", s["vdd"]), ("Temperature", "Room temperature")]
            meta += [(f"Test: {n}", st) for n, st in statuses]
            path = _path(s, "SUMMARY", stamp)
            try:
                write_overall(path, meta, all_specs, spec_files)
                ctx.log(f"\nOverall summary saved: {path}")
            except Exception as e:
                ctx.log(f"Could not save overall summary: {e}")
    return all_specs, statuses
