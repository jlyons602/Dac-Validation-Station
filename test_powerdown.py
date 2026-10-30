"""
test_powerdown.py
Power-down output: Hi-Z leakage (VOUT + VFB) and the two 10 kOhm power-down modes.
The VOUT SMU forces voltage on OUT and measures current.
"""

import time
from hardware import GEN_DEFAULT, PDN_10K_01, PDN_10K_11

NAME = "Power-down output"
TAG = "powerdown"
DESCRIPTION = "Hi-Z leakage, 10 kOhm power-down modes"

LEAK_SETTLE_S = 1.0
R_TEST_V = (0.5, 1.5)


def run(bench, ctx, res):
    dac, vout = bench.dac, bench.vout
    rows = []
    leak_notes = []
    try:
        dac.soft_reset()                                   # Hi-Z (reset default)
        v_hold = bench.vdd_set / 2
        vout.force_voltage(v_hold, 1e-6, 1e-6)
        time.sleep(LEAK_SETTLE_S)
        v, i = vout.measure(10)
        vout.voltmeter()
        res["specs"]["LEAK_HIZ"] = i * 1e9
        leak_notes = [("State", "Output Hi-Z (DAC_PDN = 10), FB tied to OUT"),
                      ("Forced voltage on OUT (V)", v), ("Leakage current (nA)", i * 1e9),
                      ("Maximum (nA)", 7), ("Note", "Includes board and SMU lead leakage")]
        ctx.log(f"  Hi-Z leakage = {i * 1e9:.2f} nA")
        ctx.progress("step", 1, 3, "Hi-Z leakage")

        for k, (label, cfg, sid) in enumerate((("DAC_PDN = 01", PDN_10K_01, "R_PDN_01"),
                                               ("DAC_PDN = 11", PDN_10K_11, "R_PDN_11")), start=2):
            ctx.check()
            dac.set_config(cfg)
            time.sleep(0.05)
            pts = []
            for vf in R_TEST_V:
                vout.force_voltage(vf, 1e-3, 1e-3)
                time.sleep(0.05)
                pts.append(vout.measure(4))
            vout.voltmeter()
            r = (pts[1][0] - pts[0][0]) / (pts[1][1] - pts[0][1])
            res["specs"][sid] = r / 1e3
            rows.append([label, pts[0][0], pts[0][1] * 1e6, pts[1][0], pts[1][1] * 1e6, r / 1e3])
            ctx.log(f"  {label}: {r / 1e3:.3f} kOhm")
            dac.set_config(GEN_DEFAULT)
            ctx.progress("step", k, 3, label)
    finally:
        vout.voltmeter()
        try:
            dac.set_config(GEN_DEFAULT)
        except Exception:
            pass
        if leak_notes:
            res["tabs"].append({"name": "HiZ_Leakage", "notes": leak_notes})
        if rows:
            res["tabs"].append({
                "name": "PowerDown_10k",
                "notes": [("Method", "R = (V2 - V1) / (I2 - I1), forced on OUT"),
                          ("Note", "FB is tied to OUT (J7), so the FB network is in parallel")],
                "columns": ["Mode", "V1_V", "I1_uA", "V2_V", "I2_uA", "R_kOhm"],
                "rows": rows,
            })
