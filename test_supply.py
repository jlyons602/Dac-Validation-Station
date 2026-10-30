"""
test_supply.py
Supply current: IDD in power-down (reset state) and IDD vs code in normal mode.
The VDD SMU is switched to its 1 mA range for resolution during this test only.
"""

import time
from hardware import GEN_ON, GEN_DEFAULT, VDD_I_LIMIT, VDD_I_RANGE, POR_DELAY_S

NAME = "Supply current"
TAG = "supply"
DESCRIPTION = "IDD normal mode (full scale), IDD power-down"

IDD_RANGE = 1e-3
CODES_10 = [0, 128, 256, 384, 512, 640, 768, 896, 1023]   # scaled for 8-bit parts
AVG = 10


def run(bench, ctx, res):
    dac, vdd = bench.dac, bench.vdd
    rows = []
    pd_notes = []
    ctx.log("VDD SMU to 1 mA range")
    vdd.force_voltage(bench.vdd_set, IDD_RANGE, IDD_RANGE)
    time.sleep(0.1)
    try:
        dac.soft_reset()                            # output Hi-Z, reference off = power-down
        time.sleep(0.3)
        v_pd, i_pd = vdd.measure(AVG)
        res["specs"]["IDD_PD"] = i_pd * 1e6
        pd_notes = [("State", "After software reset: output Hi-Z, internal reference off"),
                    ("VDD (V)", v_pd), ("IDD (uA)", i_pd * 1e6), ("Typical (uA)", 80),
                    ("Note", "Includes EVM DAC_VDD rail: idle I2C pull-ups and level translator (a few uA)")]
        ctx.log(f"  Power-down IDD = {i_pd * 1e6:.2f} uA")

        dac.set_config(GEN_ON)
        CODES = [bench.part.scale(c) for c in CODES_10]
        for k, code in enumerate(CODES, start=1):
            ctx.check()
            dac.set_code(code)
            time.sleep(0.2)
            v, i = vdd.measure(AVG)
            rows.append([code, v, i * 1e3])
            ctx.log(f"  Code {code}: IDD = {i * 1e3:.4f} mA")
            ctx.progress("step", k, len(CODES), f"Code {code}")
        res["specs"]["IDD_ACTIVE"] = rows[-1][2]
    finally:
        try:
            dac.set_config(GEN_DEFAULT)
        except Exception:
            pass
        if pd_notes:
            res["tabs"].append({"name": "IDD_Power_Down", "notes": pd_notes})
        if rows:
            res["tabs"].append({
                "name": "IDD_vs_Code",
                "notes": [("Mode", "Normal, VDD reference, output unloaded, digital pins static"),
                          ("Spec", "0.55 mA max at full scale (0.225 typ)"),
                          ("IDD at last code (mA)", rows[-1][2])],
                "columns": ["Code", "VDD_V", "IDD_mA"],
                "rows": rows,
                "chart": {"title": "Supply Current vs Code", "x": 1, "y": 3,
                          "x_title": "Code", "y_title": "IDD (mA)"},
            })
        vdd.force_voltage(bench.vdd_set, VDD_I_LIMIT, VDD_I_RANGE)
        time.sleep(POR_DELAY_S)
