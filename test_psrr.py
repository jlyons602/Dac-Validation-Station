"""
test_psrr.py
DC PSRR: internal reference, gain 2x, midscale. VDD stepped 4.5 V to 5.5 V (5 V +/-10%),
slope of VOUT vs measured VDD in mV/V.
"""

import time
from hardware import GEN_ON, GEN_DEFAULT, REF_EN, SPAN
from report import linfit

NAME = "DC power supply rejection"
TAG = "psrr"
DESCRIPTION = "DC PSRR, VDD 4.5 V to 5.5 V"

VDD_STEPS = [round(4.5 + 0.1 * i, 2) for i in range(11)]


def run(bench, ctx, res):
    dac = bench.dac
    rows = []
    try:
        dac.soft_reset()
        dac.set_config(GEN_ON | REF_EN | SPAN[2.0])
        dac.set_code(bench.part.mid)
        time.sleep(0.2)
        for k, vset in enumerate(VDD_STEPS, start=1):
            ctx.check()
            bench.set_vdd(vset, settle=0.1)
            vdd_m, _ = bench.vdd.measure(4)
            vo, _ = bench.vout.measure(4)
            rows.append([vset, vdd_m, vo])
            ctx.log(f"  VDD {vdd_m:.4f} V -> VOUT {vo:.6f} V")
            ctx.progress("step", k, len(VDD_STEPS), f"VDD {vset:.1f} V")
        slope, _ = linfit([r[1] for r in rows], [r[2] for r in rows])
        res["specs"]["PSRR_DC"] = abs(slope) * 1e3
        ctx.log(f"  PSRR = {abs(slope) * 1e3:.4f} mV/V")
    finally:
        try:
            bench.set_vdd(bench.vdd_nominal)
            dac.set_config(GEN_DEFAULT)
        except Exception:
            pass
        if rows:
            res["tabs"].append({
                "name": "PSRR_DC",
                "notes": [("Condition", "Internal reference, gain 2x, midscale"),
                          ("Method", "Slope of VOUT vs measured VDD"),
                          ("PSRR (mV/V)", res["specs"].get("PSRR_DC")), ("Typical (mV/V)", 0.25)],
                "columns": ["VDD_set_V", "VDD_meas_V", "VOUT_V"],
                "rows": rows,
                "chart": {"title": "VOUT vs VDD", "x": 2, "y": 3, "x_title": "VDD (V)", "y_title": "VOUT (V)"},
            })
