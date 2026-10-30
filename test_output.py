"""
test_output.py
Output drive: load regulation at midscale (-10 mA to +10 mA) and DC output impedance
near zero scale, midscale and near full scale (+/-1 mA):
codes 8/512/1016 on the 10-bit part, 2/128/254 on the 8-bit part. The VOUT SMU forces current and measures VOUT.
Positive current = SMU pushing current into OUT (DAC sinking).
"""

import time
from hardware import GEN_ON, GEN_DEFAULT
from report import linfit

NAME = "Output drive"
TAG = "output"
DESCRIPTION = "Load regulation, DC output impedance (low, mid, high code)"

LOAD_STEPS_MA = [-10, -8, -6, -4, -2, 0, 2, 4, 6, 8, 10]
ZOUT_CODES = [(8, "ZOUT_8"), (512, "ZOUT_512"), (1016, "ZOUT_1016")]
ZOUT_I = 1e-3


def _verify_driving(bench, code):
    v, _ = bench.vout.measure(2)
    expected = bench.vdd_set * code / bench.part.size
    if abs(v - expected) > 0.1:
        raise RuntimeError(f"VOUT is {v:.3f} V at code {code}, expected about {expected:.3f} V. "
                           "Output not driving, so no current was forced.")


def run(bench, ctx, res):
    dac, vout = bench.dac, bench.vout
    lrows, zrows = [], []
    steps = len(LOAD_STEPS_MA) + len(ZOUT_CODES)
    k = 0
    try:
        dac.soft_reset()
        dac.set_config(GEN_ON)

        mid = bench.part.mid
        dac.set_code(mid)
        time.sleep(0.05)
        _verify_driving(bench, mid)
        try:
            vout.force_current(0.0, bench.vdd_set, 0.01)
            for ma in LOAD_STEPS_MA:
                ctx.check()
                vout.set_level(ma * 1e-3, verify_tol=2e-4)
                time.sleep(0.05)
                v, i = vout.measure(4)
                lrows.append([ma, i * 1e3, v])
                k += 1
                ctx.progress("step", k, steps, f"Load {ma} mA")
        finally:
            vout.voltmeter()
        slope, _ = linfit([r[1] for r in lrows], [r[2] for r in lrows])
        res["specs"]["LOADREG"] = abs(slope) * 1e3
        ctx.log(f"  Load regulation = {abs(slope) * 1e3:.4f} mV/mA")

        for code10, sid in ZOUT_CODES:
            ctx.check()
            code = bench.part.scale(code10)
            dac.set_code(code)
            time.sleep(0.05)
            _verify_driving(bench, code)
            try:
                vout.force_current(-ZOUT_I, bench.vdd_set, 1e-3)
                time.sleep(0.05)
                v1, i1 = vout.measure(8)
                vout.set_level(ZOUT_I, verify_tol=5e-5)
                time.sleep(0.05)
                v2, i2 = vout.measure(8)
            finally:
                vout.voltmeter()
            z = (v2 - v1) / (i2 - i1)
            res["specs"][sid] = z
            zrows.append([code, v1, i1 * 1e3, v2, i2 * 1e3, z])
            ctx.log(f"  Code {code}: Zout = {z:.4f} Ohm")
            k += 1
            ctx.progress("step", k, steps, f"Zout code {code}")
    finally:
        vout.voltmeter()
        try:
            dac.set_config(GEN_DEFAULT)
        except Exception:
            pass
        if lrows:
            res["tabs"].append({
                "name": "Load_Regulation",
                "notes": [("Condition", "Midscale, VDD reference"),
                          ("Load regulation (mV/mA)", res["specs"].get("LOADREG")),
                          ("Typical (mV/mA)", 0.4),
                          ("Sign", "Positive current = SMU pushing into OUT (DAC sinking)")],
                "columns": ["Set_mA", "Measured_mA", "VOUT_V"],
                "rows": lrows,
                "chart": {"title": "VOUT vs Load Current", "x": 2, "y": 3,
                          "x_title": "Load current (mA)", "y_title": "VOUT (V)"},
            })
        if zrows:
            res["tabs"].append({
                "name": "Output_Impedance",
                "notes": [("Method", "Z = (V2 - V1) / (I2 - I1), +/-1 mA"),
                          ("Typical (Ohm)", "0.25 low and mid code, 0.26 high code"),
                          ("Note", "Local sense includes lead and contact resistance")],
                "columns": ["Code", "V1_V", "I1_mA", "V2_V", "I2_mA", "Zout_Ohm"],
                "rows": zrows,
            })
