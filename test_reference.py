"""
test_reference.py
Internal reference: VREF back-calculated at each gain setting (1.5x, 2x, 3x, 4x),
plus zero-code error with internal reference at 4x.
"""

import time
from hardware import GEN_ON, GEN_DEFAULT, REF_EN, SPAN

NAME = "Internal reference"
TAG = "reference"
DESCRIPTION = "VREF at gains 1.5x/2x/3x/4x, zero-code error (internal ref 4x)"

GAINS = [(1.5, "VREF_1P5X"), (2.0, "VREF_2X"), (3.0, "VREF_3X"), (4.0, "VREF_4X")]
REF_SETTLE_S = 0.2


def run(bench, ctx, res):
    dac, vout = bench.dac, bench.vout
    vdd = bench.vdd_set
    MID, SIZE = bench.part.mid, bench.part.size
    rows = []
    zce_notes = []
    steps = len(GAINS) + 1
    try:
        dac.soft_reset()
        for k, (gain, sid) in enumerate(GAINS, start=1):
            ctx.check()
            if vdd < 1.21 * gain + 0.2:
                ctx.log(f"  Gain {gain}x skipped: needs VDD >= {1.21 * gain + 0.2:.2f} V")
                continue
            dac.set_config(GEN_ON | REF_EN | SPAN[gain])
            dac.set_code(MID)
            time.sleep(REF_SETTLE_S)
            v, _ = vout.measure(4)
            vref = v / (MID / SIZE * gain)
            res["specs"][sid] = vref
            rows.append([f"{gain}x", f"{SPAN[gain]:02b}", MID, v, vref])
            ctx.log(f"  Gain {gain}x: VOUT = {v:.5f} V, VREF = {vref:.5f} V")
            ctx.progress("step", k, steps, f"Gain {gain}x")

        if vdd >= 1.21 * 4 + 0.2:
            dac.set_config(GEN_ON | REF_EN | SPAN[4.0])
            dac.set_code(0)
            time.sleep(REF_SETTLE_S)
            v0, _ = vout.measure(4)
            res["specs"]["ZCE_INT4X"] = v0 * 1e3
            zce_notes = [("Condition", "Code 0, internal reference, gain 4x"), ("VDD (V)", vdd),
                         ("VOUT (mV)", v0 * 1e3), ("Limit (mV)", "15 max, 6 typ")]
            ctx.log(f"  Zero-code error (int ref, 4x) = {v0 * 1e3:.2f} mV")
        ctx.progress("step", steps, steps, "Zero-code 4x")
    finally:
        try:
            dac.set_config(GEN_DEFAULT)
        except Exception:
            pass
        if rows:
            res["tabs"].append({
                "name": "Internal_Reference",
                "notes": [("Method", "VREF = VOUT / (midscale/full scale x gain)"), ("Typical VREF (V)", 1.212),
                          ("Headroom rule", "VDD >= 1.21 x gain + 0.2 V")],
                "columns": ["Gain", "DAC_SPAN", "Code", "VOUT_V", "VREF_V"],
                "rows": rows,
            })
        if zce_notes:
            res["tabs"].append({"name": "Zero_Code_IntRef_4x", "notes": zce_notes})
