"""
test_functional.py
Register / functional checks (no analog measurements): device ID and NVM CRC, reset
defaults, register read/write, walking ones, software reset, device lock.
"""

from hardware import (REG_STATUS, REG_GEN_CONFIG, REG_CONFIG2, REG_TRIGGER,
                      REG_DAC_DATA, REG_MARGIN_HIGH, REG_MARGIN_LOW, GEN_DEFAULT, TRIG_UNLOCK)
from limits import SPECS

NAME = "Functional / register tests"
TAG = "functional"
DESCRIPTION = "Device ID, reset defaults, register R/W, walking ones, soft reset, lock"
NEEDS_READ = True              # skipped in write-only I2C mode

FACTORY = {REG_GEN_CONFIG: 0x01F0, REG_CONFIG2: 0x0000, REG_DAC_DATA: 0x0000,
           REG_MARGIN_HIGH: 0x0000, REG_MARGIN_LOW: 0x0000}
LOCK_BIT = 1 << 13


def _patterns(dac, reg, patterns, mask):
    fails = []
    for p in patterns:
        dac.write_reg(reg, p)
        rb = dac.read_reg(reg)
        if (rb & mask) != (p & mask):
            fails.append(f"0x{reg:02X}: wrote 0x{p:04X} read 0x{rb:04X}")
    return fails


def run(bench, ctx, res):
    dac = bench.dac
    part = bench.part
    DATA_MASK = part.data_mask
    rows = []
    steps = 6

    def record(k, sid, result, detail):
        res["specs"][sid] = result
        rows.append([SPECS[sid]["name"], result, detail])
        ctx.log(f"  {SPECS[sid]['name']}: {result}")
        ctx.progress("step", k, steps, SPECS[sid]["name"])
        ctx.check()

    try:
        s = dac.read_reg(REG_STATUS)
        dev_id = (s >> 2) & 0xF
        ok = dev_id == part.device_id and not (s & 0xE000)
        record(1, "F_ID", "PASS" if ok else "FAIL",
               f"STATUS=0x{s:04X}, ID={dev_id}, CRC user={s >> 15 & 1}, "
               f"CRC internal={s >> 14 & 1}, NVM busy={s >> 13 & 1}")

        dac.soft_reset()
        snap = {r: dac.read_reg(r) for r in FACTORY}
        diffs = [f"0x{r:02X}=0x{v:04X}" for r, v in snap.items() if v != FACTORY[r]]
        record(2, "F_DEFAULTS", "PASS" if not diffs else "WARN",
               "Match factory values" if not diffs else "NVM differs from factory: " + ", ".join(diffs))

        fails = _patterns(dac, REG_GEN_CONFIG, [0x0000, 0x4A5A, 0x85A5, 0xCFFF, GEN_DEFAULT], 0xFFFF)
        fails += _patterns(dac, REG_CONFIG2, [0x0015, 0x002A, 0x003F, 0x0000], 0xFF3F)
        record(3, "F_REGS", "PASS" if not fails else "FAIL",
               "9 patterns read back correctly" if not fails else "; ".join(fails))

        walk = [1 << (part.shift + i) for i in range(part.bits)] + [DATA_MASK, 0x0000]
        fails = []
        for reg in (REG_DAC_DATA, REG_MARGIN_HIGH, REG_MARGIN_LOW):
            fails += _patterns(dac, reg, walk, DATA_MASK)
        record(4, "F_WALK", "PASS" if not fails else "FAIL",
               f"{3 * len(walk)} writes read back correctly" if not fails else "; ".join(fails))

        dac.write_reg(REG_GEN_CONFIG, 0x4A5A)
        dac.write_reg(REG_DAC_DATA, 0x0AA8 & DATA_MASK)
        dac.soft_reset()
        g = dac.read_reg(REG_GEN_CONFIG)
        d = dac.read_reg(REG_DAC_DATA) & DATA_MASK
        ok = g == snap[REG_GEN_CONFIG] and d == (snap[REG_DAC_DATA] & DATA_MASK)
        record(5, "F_RESET", "PASS" if ok else "FAIL",
               f"After reset GEN_CONFIG=0x{g:04X}, DAC_DATA=0x{d:04X}")

        target = 0x0550 & DATA_MASK
        dac.write_reg(REG_DAC_DATA, 0x0000)
        dac.write_reg(REG_GEN_CONFIG, GEN_DEFAULT | LOCK_BIT)
        try:
            dac.write_reg(REG_DAC_DATA, target)
            nack = False
        except Exception:
            nack = True
        blocked = (dac.read_reg(REG_DAC_DATA) & DATA_MASK) == 0
        dac.write_reg(REG_TRIGGER, TRIG_UNLOCK)
        dac.write_reg(REG_GEN_CONFIG, GEN_DEFAULT)
        dac.write_reg(REG_DAC_DATA, target)
        works = (dac.read_reg(REG_DAC_DATA) & DATA_MASK) == target
        dac.write_reg(REG_DAC_DATA, 0x0000)
        record(6, "F_LOCK", "PASS" if blocked and works else "FAIL",
               f"Locked write blocked={blocked} (NACK={nack}), writes after unlock={works}")
    finally:
        res["tabs"].append({"name": "Functional", "columns": ["Check", "Result", "Detail"], "rows": rows})
        try:
            dac.write_reg(REG_TRIGGER, TRIG_UNLOCK)
            dac.soft_reset()
        except Exception:
            pass
