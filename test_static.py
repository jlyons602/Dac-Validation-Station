"""
test_static.py
Static accuracy from one sweep: INL (best fit), DNL, zero-code error, offset error,
gain error, full-scale error, TUE.  VDD reference, gain 1x, output unloaded.
Sweep mode comes from the GUI: "carry" (major carry) or "full" (every code).
Works for DAC53701 (10-bit) and DAC43701 (8-bit); the part comes from the bench.
"""

import time
from hardware import GEN_ON, GEN_DEFAULT

NAME = "Static accuracy"
TAG = "static"
DESCRIPTION = "INL, DNL, zero-code, offset, gain, full-scale error, TUE"

CARRY_STEPS   = 32          # number of major-carry transitions measured (every 32 codes 10-bit, 8 codes 8-bit)
SETTLE_S      = 0.02


def sweep_codes(mode, part):
    if mode == "full":
        return list(range(part.code_max + 1))
    codes = {0, part.fit_lo, part.fit_hi, part.code_max}
    stride = part.size // CARRY_STEPS
    for n in range(stride, part.code_max + 1, stride):
        codes.update((n - 1, n))
    return sorted(codes)


def _worst(values):
    values = list(values)
    return max(values, key=abs) if values else None


def run(bench, ctx, res):
    mode = ctx.settings.get("sweep", "carry")
    part = bench.part
    codes = sweep_codes(mode, part)
    ctx.log(f"{part.name}: {'major carry' if mode == 'carry' else 'full'} sweep, {len(codes)} codes")
    rows = []
    bench.dac.set_config(GEN_ON)
    time.sleep(0.05)
    t0 = time.perf_counter()
    try:
        for k, code in enumerate(codes, start=1):
            ctx.check()
            bench.dac.set_code(code)
            rb = bench.dac.get_code()
            time.sleep(SETTLE_S)
            vout, iout = bench.vout.measure()
            vdd, idd = bench.vdd.measure()
            rows.append({"t": time.perf_counter() - t0, "code": code, "rb": rb, "ok": rb == code,
                         "vout": vout, "iout": iout, "vdd": vdd, "idd": idd})
            if rb is not None and rb != code:
                ctx.log(f"  Code {code}: readback MISMATCH ({rb})")
            ctx.progress("step", k, len(codes), f"Code {code}")
    finally:
        try:
            bench.dac.set_config(GEN_DEFAULT)
        except Exception:
            pass
        analyze(rows, res, part)


def analyze(rows, res, part):
    specs, tabs = res["specs"], res["tabs"]
    tabs.append({
        "name": "Static_Data",
        "columns": ["elapsed_s", "Code", "Readback", "Write_check", "VOUT_V", "VOUT_I_A", "VDD_V", "IDD_mA"],
        "rows": [[r["t"], r["code"], r["rb"] if r["rb"] is not None else "-",
                  "NOT CHECKED" if r["rb"] is None else ("OK" if r["ok"] else "MISMATCH"),
                  r["vout"], r["iout"], r["vdd"], r["idd"] * 1e3] for r in rows],
    })
    if not rows:
        return

    vdd = sum(r["vdd"] for r in rows) / len(rows)
    FIT_LO, FIT_HI, CODE_MAX, SIZE = part.fit_lo, part.fit_hi, part.code_max, part.size
    ideal_lsb = vdd / SIZE
    V = {r["code"]: r["vout"] for r in rows}
    fit = [c for c in sorted(V) if FIT_LO <= c <= FIT_HI]

    if len(fit) >= 2:
        n = len(fit)
        sx = sum(fit)
        sy = sum(V[c] for c in fit)
        sxx = sum(c * c for c in fit)
        sxy = sum(c * V[c] for c in fit)
        slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
        icpt = (sy - slope * sx) / n
        if abs(slope) < 1e-6:
            raise RuntimeError("VOUT did not change with the DAC code, so the I2C writes are not reaching "
                               "the DAC (or the output is not enabled). Raw data saved in Static_Data.")
        inl = {c: (V[c] - (slope * c + icpt)) / slope for c in fit}
        dnl = {c: (V[c] - V[c - 1]) / slope - 1 for c in fit if c - 1 in V and c - 1 >= FIT_LO}

        specs["INL"] = _worst(inl.values())
        tabs.append({
            "name": "INL",
            "notes": [("Part", f"{part.name} ({part.bits}-bit)"), ("Method", "Best-fit line"), ("Fit range", f"Codes {FIT_LO} to {FIT_HI}"),
                      ("Points in fit", n), ("Best-fit LSB (mV)", slope * 1e3),
                      ("Best-fit offset at code 0 (mV)", icpt * 1e3),
                      ("Worst INL (LSB)", specs["INL"]), ("Limit (LSB)", "+/- 1")],
            "columns": ["Code", "VOUT_V", "Fit_V", "INL_LSB"],
            "rows": [[c, V[c], slope * c + icpt, inl[c]] for c in fit],
            "chart": {"title": "INL vs Code", "x": 1, "y": 4, "x_title": "Code", "y_title": "INL (LSB)"},
        })
        if dnl:
            specs["DNL"] = _worst(dnl.values())
            tabs.append({
                "name": "DNL",
                "notes": [("LSB size used (mV)", slope * 1e3), ("Transitions measured", len(dnl)),
                          ("Worst DNL (LSB)", specs["DNL"]), ("Limit (LSB)", "+/- 1")],
                "columns": ["Code", "V_prev_V", "V_code_V", "Step_mV", "DNL_LSB"],
                "rows": [[c, V[c - 1], V[c], (V[c] - V[c - 1]) * 1e3, dnl[c]] for c in sorted(dnl)],
                "chart": {"title": "DNL vs Code", "x": 1, "y": 5, "x_title": "Code", "y_title": "DNL (LSB)"},
            })

    if 0 in V:
        specs["ZCE"] = V[0] * 1e3
        tabs.append({"name": "Zero_Code_Error",
                     "notes": [("Code", 0), ("VOUT (V)", V[0]), ("Zero-code error (mV)", specs["ZCE"]),
                               ("Limit (mV)", "12 max, 6 typ")]})

    if FIT_LO in V and FIT_HI in V:
        ep_slope = (V[FIT_HI] - V[FIT_LO]) / (FIT_HI - FIT_LO)
        ep_off = V[FIT_LO] - ep_slope * FIT_LO
        specs["OFFSET"] = ep_off / vdd * 100
        specs["GAIN"] = (ep_slope / ideal_lsb - 1) * 100
        tabs.append({"name": "Offset_Gain_Error",
                     "notes": [("VDD average (V)", vdd),
                               (f"VOUT at code {FIT_LO} (V)", V[FIT_LO]),
                               (f"VOUT at code {FIT_HI} (V)", V[FIT_HI]),
                               ("End-point slope (mV/LSB)", ep_slope * 1e3),
                               (f"Ideal slope VDD/{SIZE} (mV/LSB)", ideal_lsb * 1e3),
                               ("Line value at code 0 (mV)", ep_off * 1e3),
                               ("Offset error (%FSR)", specs["OFFSET"]),
                               ("Gain error (%FSR)", specs["GAIN"]),
                               ("Limits (%FSR)", "+/- 0.5 each")]})

    if CODE_MAX in V:
        ideal_fs = vdd * CODE_MAX / SIZE
        specs["FSE"] = (V[CODE_MAX] - ideal_fs) / vdd * 100
        tabs.append({"name": "Full_Scale_Error",
                     "notes": [("Code", CODE_MAX), ("VDD average (V)", vdd),
                               ("VOUT measured (V)", V[CODE_MAX]),
                               (f"VOUT ideal, VDD x {CODE_MAX}/{SIZE} (V)", ideal_fs),
                               ("Error (mV)", (V[CODE_MAX] - ideal_fs) * 1e3),
                               ("Full-scale error (%FSR)", specs["FSE"]),
                               ("Limit (%FSR)", "+/- 0.5")]})

    if fit:
        tue = {c: (V[c] - c * ideal_lsb) / vdd * 100 for c in fit}
        specs["TUE"] = _worst(tue.values())
        tabs.append({
            "name": "TUE",
            "notes": [("Ideal output", f"code x VDD / {SIZE}"), ("Worst TUE (%FSR)", specs["TUE"])],
            "columns": ["Code", "VOUT_V", "Ideal_V", "Error_mV", "TUE_%FSR"],
            "rows": [[c, V[c], c * ideal_lsb, (V[c] - c * ideal_lsb) * 1e3, tue[c]] for c in fit],
            "chart": {"title": "TUE vs Code", "x": 1, "y": 5, "x_title": "Code", "y_title": "TUE (%FSR)"},
        })
