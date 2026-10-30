"""
limits.py
DAC53701 / DAC43701 datasheet limits (TI SLASEY5, Electrical Characteristics), room temperature.
min / max are guaranteed limits -> PASS / FAIL.
Specs with only a typical value -> INFO (Hi-Z leakage 7 nA is a MAX in the datasheet) (measured value shown next to the typical).
"""


def _spec(name, cond, mn, typ, mx, unit):
    return {"name": name, "cond": cond, "min": mn, "typ": typ, "max": mx, "unit": unit}


SPECS = {
    # ---- functional ----
    "F_ID":       _spec("Device ID and NVM CRC", "STATUS: ID = 3, CRC alarms clear", None, None, None, ""),
    "F_DEFAULTS": _spec("Reset defaults", "Registers after software reset vs factory values", None, None, None, ""),
    "F_REGS":     _spec("Config register read/write", "GENERAL_CONFIG and CONFIG2 patterns", None, None, None, ""),
    "F_WALK":     _spec("Data register walking ones", "DAC_DATA, MARGIN_HIGH, MARGIN_LOW", None, None, None, ""),
    "F_RESET":    _spec("Software reset", "Changed registers return to reset values", None, None, None, ""),
    "F_LOCK":     _spec("Device lock / unlock", "DEVICE_LOCK blocks writes, unlock code restores", None, None, None, ""),

    # ---- static accuracy (VDD reference, gain 1x, unloaded) ----
    "INL":    _spec("INL (best fit)", "Codes 8 to 1016 (8-bit: 2 to 254), unloaded", -1.0, None, 1.0, "LSB"),
    "DNL":    _spec("DNL", "Codes 8 to 1016 (8-bit: 2 to 254), unloaded", -1.0, None, 1.0, "LSB"),
    "ZCE":    _spec("Zero-code error", "Code 0, VDD reference, VDD = 5.5 V", None, 6.0, 12.0, "mV"),
    "OFFSET": _spec("Offset error", "End points 8 and 1016 (8-bit: 2 and 254)", -0.5, 0.25, 0.5, "%FSR"),
    "GAIN":   _spec("Gain error", "End points 8 and 1016 (8-bit: 2 and 254)", -0.5, 0.25, 0.5, "%FSR"),
    "FSE":    _spec("Full-scale error", "Full-scale code, 2.7 V <= VDD <= 5.5 V", -0.5, 0.25, 0.5, "%FSR"),
    "TUE":    _spec("Total unadjusted error", "End-point code range (plotted typical only)", None, None, None, "%FSR"),

    # ---- supply current ----
    "IDD_ACTIVE": _spec("IDD, normal mode", "DAC at full scale, digital pins static", None, 0.225, 0.55, "mA"),
    "IDD_PD":     _spec("IDD, power-down", "DAC and internal reference powered down", None, 80.0, None, "uA"),

    # ---- power-down output ----
    "LEAK_HIZ": _spec("VOUT + VFB leakage, Hi-Z", "Output disabled, held at VDD/2, VDD = 5.5 V", None, None, 7.0, "nA"),
    "R_PDN_01": _spec("Power-down resistance, DAC_PDN = 01", "OUT to AGND (FB tied to OUT)", None, 10.0, None, "kOhm"),
    "R_PDN_11": _spec("Power-down resistance, DAC_PDN = 11", "OUT to AGND (FB tied to OUT)", None, 10.0, None, "kOhm"),

    # ---- internal reference ----
    "VREF_1P5X": _spec("Internal reference, gain 1.5x", "Back-calculated from VOUT at midscale", None, 1.212, None, "V"),
    "VREF_2X":   _spec("Internal reference, gain 2x", "Back-calculated from VOUT at midscale", None, 1.212, None, "V"),
    "VREF_3X":   _spec("Internal reference, gain 3x", "Back-calculated from VOUT at midscale", None, 1.212, None, "V"),
    "VREF_4X":   _spec("Internal reference, gain 4x", "Back-calculated from VOUT at midscale", None, 1.212, None, "V"),
    "ZCE_INT4X": _spec("Zero-code error, internal ref 4x", "Code 0, internal reference, gain 4x, VDD = 5.5 V",
                       None, 6.0, 15.0, "mV"),

    # ---- PSRR ----
    "PSRR_DC": _spec("PSRR (dc)", "Internal ref, gain 2x, midscale, VDD = 5 V +/-10%", None, 0.25, None, "mV/V"),

    # ---- output drive ----
    "LOADREG":   _spec("Load regulation", "Midscale, -10 mA to +10 mA, VDD = 5.5 V", None, 0.4, None, "mV/mA"),
    "ZOUT_8":    _spec("VOUT dc output impedance, low code (8 / 2)", "Output enabled, +/-1 mA", None, 0.25, None, "Ohm"),
    "ZOUT_512":  _spec("VOUT dc output impedance, midscale", "Output enabled, +/-1 mA", None, 0.25, None, "Ohm"),
    "ZOUT_1016": _spec("VOUT dc output impedance, high code (1016 / 254)", "Output enabled, +/-1 mA", None, 0.26, None, "Ohm"),

    # ---- FB pin (J7 removed) ----
    "ZFB_1X": _spec("VFB dc output impedance, 1x", "Output enabled, VDD reference", 160.0, 200.0, 240.0, "kOhm"),
    "ZFB_4X": _spec("VFB dc output impedance, 4x", "Output enabled, internal reference, gain 4x",
                    192.0, 240.0, 288.0, "kOhm"),
}


def judge(spec_id, value):
    if value is None:
        return "NO DATA"
    if isinstance(value, str):
        return value
    s = SPECS[spec_id]
    if s["min"] is None and s["max"] is None:
        return "INFO"
    if s["min"] is not None and value < s["min"]:
        return "FAIL"
    if s["max"] is not None and value > s["max"]:
        return "FAIL"
    return "PASS"
