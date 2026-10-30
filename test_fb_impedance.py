"""
test_fb_impedance.py
FB pin DC output impedance (guaranteed min/max spec). Needs a manual setup change,
so the GUI asks before and after it runs:
  before: remove J7, move the VOUT SMU HI lead from TP2 to TP4 (VFB)
  after:  reinstall J7, move the lead back to TP2
"""

import time
from hardware import GEN_ON, GEN_DEFAULT, REF_EN, SPAN

NAME = "FB pin impedance (manual: J7 removed)"
TAG = "fb_impedance"
DESCRIPTION = "VFB dc output impedance, 1x and 4x (needs J7 removed)"

MANUAL_SETUP = ("FB impedance test setup:\n\n"
                "1. REMOVE jumper J7 (FB no longer tied to OUT).\n"
                "2. Move the VOUT SMU HI lead from TP2 to TP4 (VFB).\n\n"
                "Press OK when ready, or Cancel to skip this test.")
MANUAL_TEARDOWN = ("FB impedance test finished:\n\n"
                   "1. Reinstall jumper J7.\n"
                   "2. Move the VOUT SMU HI lead back to TP2 (VOUT).")

TEST_V = (0.5, 1.5)
CASES = [("Gain 1x, VDD reference", GEN_ON, "ZFB_1X"),
         ("Gain 4x, internal reference", GEN_ON | REF_EN | SPAN[4.0], "ZFB_4X")]


def run(bench, ctx, res):
    dac, vout = bench.dac, bench.vout
    rows = []
    try:
        for k, (label, cfg, sid) in enumerate(CASES, start=1):
            ctx.check()
            dac.set_config(cfg)
            dac.set_code(bench.part.mid)
            time.sleep(0.2)
            pts = []
            for vf in TEST_V:
                vout.force_voltage(vf, 1e-4, 1e-4)
                time.sleep(0.2)
                pts.append(vout.measure(8))
            vout.voltmeter()
            z = (pts[1][0] - pts[0][0]) / (pts[1][1] - pts[0][1])
            res["specs"][sid] = z / 1e3
            rows.append([label, pts[0][0], pts[0][1] * 1e6, pts[1][0], pts[1][1] * 1e6, z / 1e3])
            ctx.log(f"  {label}: {z / 1e3:.2f} kOhm")
            ctx.progress("step", k, len(CASES), label)
    finally:
        vout.voltmeter()
        try:
            dac.set_config(GEN_DEFAULT)
        except Exception:
            pass
        if rows:
            res["tabs"].append({
                "name": "FB_Impedance",
                "notes": [("Setup", "J7 removed, SMU on TP4 (VFB)"),
                          ("Method", "Z = (V2 - V1) / (I2 - I1)"),
                          ("Limits", "1x: 160 to 240 kOhm; 4x: 192 to 288 kOhm")],
                "columns": ["Case", "V1_V", "I1_uA", "V2_V", "I2_uA", "Z_kOhm"],
                "rows": rows,
            })
