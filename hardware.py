"""
hardware.py
Shared hardware layer for DAC53701 validation on the DAC53701EVM.
  DAC    : DAC53701 over the EVM's onboard FT4222H (I2C)
  Smu    : PXIe-4139 wrapper (force voltage, force current, or voltmeter)
  Bench  : power-up order VDD -> POR wait -> I2C -> VOUT SMU, shutdown in reverse

Setup: J3 OPEN, J5 2-3, J6 OPEN, J7 IN.
  VDD SMU  (default "smu1")  HI -> J2 pin 1 (DAC_VDD), LO -> GND
  VOUT SMU (default "smu2")  HI -> TP2 (VOUT),         LO -> GND
"""

import time
import ft4222
from ft4222.I2CMaster import Flag
import nidcpower

# ---------------- DAC constants ----------------
ADDR           = 0x48           # default for both DAC53701 and DAC43701 (SLAVE_ADDRESS = 00)
FT_DESCRIPTION = "FT4222 A"
I2C_KBPS       = 100


class Part:
    """Resolution-dependent details. Both parts share the register map and address scheme."""

    TABLE = {
        #             bits shift  ID  fit_lo fit_hi   (fit codes = datasheet INL/DNL end points)
        "DAC53701": (10,   2,    0x3,   8,   1016),
        "DAC43701": (8,    4,    0x5,   2,    254),
    }
    BY_ID = {v[2]: k for k, v in TABLE.items()}

    def __init__(self, name):
        self.name = name
        self.bits, self.shift, self.device_id, self.fit_lo, self.fit_hi = self.TABLE[name]
        self.size = 1 << self.bits                  # 1024 or 256
        self.code_max = self.size - 1               # 1023 or 255
        self.mid = self.size // 2                   # 512 or 128
        self.data_mask = self.code_max << self.shift

    def scale(self, code10):
        """Map a 10-bit reference code to this part (512 -> 128, 8 -> 2, 1016 -> 254)."""
        return code10 >> (10 - self.bits)


# kept for code that only needs 10-bit defaults
BITS = 10
CODE_MAX = 1023
DEVICE_ID = 0x3

REG_STATUS      = 0xD0
REG_GEN_CONFIG  = 0xD1
REG_CONFIG2     = 0xD2
REG_TRIGGER     = 0xD3
REG_DAC_DATA    = 0x21
REG_MARGIN_HIGH = 0x25
REG_MARGIN_LOW  = 0x26

GEN_DEFAULT = 0x01F0            # output Hi-Z, VDD reference, no slew (reset value)
GEN_ON      = 0x01E0            # output powered up, VDD reference
PDN_10K_01  = 0x01E8            # DAC_PDN = 01, output 10 kOhm to AGND
PDN_10K_11  = 0x01F8            # DAC_PDN = 11, output 10 kOhm to AGND
REF_EN      = 0x0004            # internal reference enable
SPAN        = {1.5: 0b00, 2.0: 0b01, 3.0: 0b10, 4.0: 0b11}

TRIG_SW_RESET = 0x000A
TRIG_UNLOCK   = 0x5008
POR_DELAY_S   = 0.05

# ---------------- SMU constants ----------------
VDD_I_LIMIT = 0.03              # 30 mA, covers the 10 mA load-regulation test
VDD_I_RANGE = 0.1


class ReadDisabled(RuntimeError):
    pass


class DAC:
    """write_only=True: never read over I2C, and treat write NACKs as warnings (counted, not fatal)."""

    def __init__(self, addr=ADDR, write_only=False, part=None):
        self.addr = addr
        self.part = part or Part("DAC53701")
        self.write_only = write_only
        self.write_errors = 0
        self.dev = ft4222.openByDescription(FT_DESCRIPTION)
        self.dev.i2cMaster_Init(I2C_KBPS)

    def write_reg(self, reg, data):
        payload = bytes([reg, (data >> 8) & 0xFF, data & 0xFF])
        try:
            sent = self.dev.i2cMaster_Write(self.addr, payload)
            if sent != 3:
                raise RuntimeError(f"I2C write to 0x{reg:02X} failed ({sent} of 3 bytes)")
        except Exception:
            if not self.write_only:
                raise
            self.write_errors += 1
            try:
                self.dev.i2cMaster_Reset()
            except Exception:
                pass

    def read_reg(self, reg):
        if self.write_only:
            raise ReadDisabled("I2C read-back is disabled (write-only mode)")
        self.dev.i2cMaster_WriteEx(self.addr, Flag.START, bytes([reg]))
        msb = self.dev.i2cMaster_ReadEx(self.addr, Flag.REPEATED_START, 1)
        lsb = self.dev.i2cMaster_ReadEx(self.addr, Flag.STOP, 1)
        return (msb[0] << 8) | lsb[0]

    def device_id(self):
        return (self.read_reg(REG_STATUS) >> 2) & 0xF

    def set_config(self, value):
        self.write_reg(REG_GEN_CONFIG, value)

    def set_code(self, code):
        p = self.part
        self.write_reg(REG_DAC_DATA, (code & p.code_max) << p.shift)   # left aligned in bits 11:2 or 11:4

    def get_code(self):
        """Returns None in write-only mode (no read-back)."""
        if self.write_only:
            return None
        p = self.part
        return (self.read_reg(REG_DAC_DATA) >> p.shift) & p.code_max

    def soft_reset(self):
        self.write_reg(REG_TRIGGER, TRIG_SW_RESET)
        time.sleep(POR_DELAY_S)

    def close(self):
        self.dev.close()


class Smu:
    def __init__(self, resource, plf=60.0, remote_sense=False):
        self.name = resource
        self.s = nidcpower.Session(resource_name=f"{resource}/0", reset=True)
        s = self.s
        s.source_mode = nidcpower.SourceMode.SINGLE_POINT
        s.sense = nidcpower.Sense.REMOTE if remote_sense else nidcpower.Sense.LOCAL
        s.power_line_frequency = plf
        s.aperture_time = 1.0 / plf
        s.measure_when = nidcpower.MeasureWhen.ON_DEMAND
        self.mode = None
        self.params = None

    def _apply(self):
        s = self.s
        s.abort()
        level, limit, rng = self.params
        if self.mode == "V":
            s.output_function = nidcpower.OutputFunction.DC_VOLTAGE
            s.voltage_level_range = 6.0
            s.voltage_level = level
            s.current_limit_range = rng
            s.current_limit = limit
        else:
            s.output_function = nidcpower.OutputFunction.DC_CURRENT
            s.current_level_range = rng
            s.current_level = level
            s.voltage_limit_range = 6.0
            s.voltage_limit = limit
        s.output_enabled = True
        s.commit()
        s.initiate()

    def force_voltage(self, volts, i_limit, i_range=None):
        self.mode, self.params = "V", (volts, i_limit, i_range or i_limit)
        self._apply()

    def force_current(self, amps, v_limit, i_range):
        self.mode, self.params = "I", (amps, v_limit, i_range)
        self._apply()

    def voltmeter(self):
        """Force 0 A and measure voltage (high-impedance voltmeter)."""
        self.force_current(0.0, 6.0, 1e-6)

    def set_level(self, value, verify_tol=None):
        """Change the output level while running; fall back to a full reconfigure if needed."""
        _, limit, rng = self.params
        self.params = (value, limit, rng)
        try:
            if self.mode == "V":
                self.s.voltage_level = value
            else:
                self.s.current_level = value
        except Exception:
            self._apply()
            return
        if verify_tol is not None:
            time.sleep(0.01)
            v, i = self.measure()
            actual = v if self.mode == "V" else i
            if abs(actual - value) > verify_tol:
                self._apply()

    def measure(self, n=1):
        vs = cs = 0.0
        for _ in range(n):
            m = self.s.measure_multiple()[0]
            vs += m.voltage
            cs += m.current
        return vs / n, cs / n

    def close(self, power_off=False):
        try:
            if power_off:
                self.s.abort()
                self.s.output_function = nidcpower.OutputFunction.DC_VOLTAGE
                self.s.voltage_level = 0.0
                self.s.output_enabled = False
                self.s.commit()
            else:
                self.voltmeter()
        finally:
            self.s.close()


class Bench:
    """settings keys: vdd_smu, vout_smu, vdd, remote_sense, plf"""

    def __init__(self, settings):
        self.cfg = settings
        self.vdd = self.vout = self.dac = None
        self.part = Part("DAC53701")
        self.vdd_nominal = settings["vdd"]
        self.vdd_set = settings["vdd"]

    def open(self, log):
        c = self.cfg
        log(f"VDD SMU {c['vdd_smu']}: {c['vdd']:.3f} V, {VDD_I_LIMIT * 1e3:.0f} mA limit")
        self.vdd = Smu(c["vdd_smu"], plf=c["plf"])
        self.vdd.force_voltage(c["vdd"], VDD_I_LIMIT, VDD_I_RANGE)
        time.sleep(POR_DELAY_S)
        v, i = self.vdd.measure(2)
        log(f"VDD = {v:.4f} V, IDD = {i * 1e3:.3f} mA")

        addr = c.get("i2c_addr", ADDR)
        write_only = c.get("write_only", False)
        want = c.get("part", "Auto")
        if write_only and want == "Auto":
            raise RuntimeError("Write-only mode cannot auto-detect the part. Pick DAC53701 or DAC43701.")
        self.part = Part(want if want != "Auto" else "DAC53701")
        self.dac = DAC(addr=addr, write_only=write_only, part=self.part)
        if write_only:
            log(f"WRITE-ONLY I2C MODE at 0x{addr:02X} ({self.part.name}): no read-back, write errors only counted")
        else:
            dev_id = None
            try:
                dev_id = self.dac.device_id()
            except Exception:
                pass
            found = Part.BY_ID.get(dev_id)
            if found is None:
                raise RuntimeError(
                    f"No DAC53701/DAC43701 answering at 0x{addr:02X} (ID read: {dev_id}). Check that the "
                    "EVM DAC_VDD (J2 pin 1) is on the same VDD as the DAC, J3 is open, J5 is on 2-3, "
                    "grounds are common, and TI's GUI is closed. Use the I2C scan tool to see what is on the bus.")
            if want == "Auto":
                self.part = Part(found)
                self.dac.part = self.part
            elif found != want:
                raise RuntimeError(f"Found a {found} (ID {dev_id}) at 0x{addr:02X}, but {want} is selected. "
                                   "Change the part selection or set it to Auto.")
            log(f"{self.part.name} ({self.part.bits}-bit) found on I2C at 0x{addr:02X}")

        self.vout = Smu(c["vout_smu"], plf=c["plf"], remote_sense=c["remote_sense"])
        self.vout.voltmeter()
        log(f"VOUT SMU {c['vout_smu']}: voltmeter mode (0 A)")
        if write_only:
            self._analog_check(log)

    def _analog_check(self, log):
        """Write-only mode: prove the writes land by checking VOUT at midscale."""
        self.dac.set_config(GEN_ON)
        self.dac.set_code(self.part.mid)
        time.sleep(0.05)
        v, _ = self.vout.measure(2)
        self.dac.set_config(GEN_DEFAULT)
        expected = self.vdd_set / 2
        if abs(v - expected) < 0.1:
            log(f"Write check by VOUT: midscale gave {v:.4f} V (expected {expected:.3f} V), writes are landing")
        else:
            log(f"WARNING: midscale gave VOUT = {v:.4f} V, expected {expected:.3f} V. "
                f"Writes are probably NOT reaching the DAC ({self.dac.write_errors} write errors so far).")

    def set_vdd(self, volts, settle=0.1):
        self.vdd.set_level(volts, verify_tol=0.05)
        self.vdd_set = volts
        time.sleep(settle)

    def restore(self):
        """Known state between tests: VOUT SMU at 0 A, VDD nominal, DAC reset (Hi-Z)."""
        if self.vout:
            self.vout.voltmeter()
        if self.vdd:
            self.vdd.force_voltage(self.vdd_nominal, VDD_I_LIMIT, VDD_I_RANGE)
            self.vdd_set = self.vdd_nominal
            time.sleep(POR_DELAY_S)
        if self.dac:
            try:
                self.dac.write_reg(REG_TRIGGER, TRIG_UNLOCK)
            except Exception:
                pass
            self.dac.soft_reset()

    def close(self, log=print):
        if self.dac and self.dac.write_only:
            log(f"Write-only mode: {self.dac.write_errors} I2C write errors (NACKs) during the run")
        if self.vout:
            try:
                self.vout.close()
            except Exception:
                pass
        if self.dac:
            try:
                self.dac.set_config(GEN_DEFAULT)
            except Exception:
                pass
            try:
                self.dac.close()
            except Exception:
                pass
        if self.vdd:
            try:
                self.vdd.close(power_off=True)
                log("VDD off")
            except Exception:
                pass


def check_hardware(vdd_smu, vout_smu):
    """Quick presence check used by the GUI. Returns a list of text lines."""
    lines = []
    try:
        n = ft4222.createDeviceInfoList()
        if n == 0:
            lines.append("FT4222: NOT FOUND (driver missing, board unplugged, or in use)")
        for i in range(n):
            d = ft4222.getDeviceInfoDetail(i, False)
            lines.append(f"FT4222: found {d['description'].decode()}")
    except Exception as e:
        lines.append(f"FT4222: error ({e})")
    for label, name in (("VDD SMU", vdd_smu), ("VOUT SMU", vout_smu)):
        try:
            s = nidcpower.Session(resource_name=f"{name}/0", reset=False)
            s.close()
            lines.append(f"{label} {name}: OK")
        except Exception as e:
            lines.append(f"{label} {name}: NOT FOUND ({e})")
    return lines


def scan_i2c(vdd_smu, vdd, plf=60.0, power=True):
    """Power VDD from the SMU (optional), then probe every 7-bit address.
    Returns text lines. For 0x48-0x4B also reads STATUS to name the part."""
    lines = []
    smu = None
    try:
        if power:
            smu = Smu(vdd_smu, plf=plf)
            smu.force_voltage(vdd, VDD_I_LIMIT, VDD_I_RANGE)
            time.sleep(POR_DELAY_S)
            v, i = smu.measure(2)
            lines.append(f"VDD from {vdd_smu}: {v:.3f} V, {i * 1e3:.3f} mA")
        dev = ft4222.openByDescription(FT_DESCRIPTION)
        dev.i2cMaster_Init(I2C_KBPS)
        found = []
        try:
            for addr in range(0x08, 0x78):
                try:
                    dev.i2cMaster_WriteEx(addr, Flag.START, bytes([REG_STATUS]))
                    msb = dev.i2cMaster_ReadEx(addr, Flag.REPEATED_START, 1)
                    lsb = dev.i2cMaster_ReadEx(addr, Flag.STOP, 1)
                    status = (msb[0] << 8) | lsb[0]
                    st = dev.i2cMaster_GetStatus() if hasattr(dev, "i2cMaster_GetStatus") else 0
                    if st & 0x06:          # error or address NACK reported by the controller
                        raise IOError("nack")
                    if status == 0xFFFF:   # nobody drove the bus (pull-ups only)
                        raise IOError("no answer")
                    dev_id = (status >> 2) & 0xF
                    name = Part.BY_ID.get(dev_id) if 0x48 <= addr <= 0x4B else None
                    found.append(addr)
                    lines.append(f"0x{addr:02X}: answers, STATUS=0x{status:04X}"
                                 + (f" -> {name}" if name else ""))
                except Exception:
                    try:
                        dev.i2cMaster_Reset()
                    except Exception:
                        pass
        finally:
            dev.close()
        if not found:
            lines.append("No device answered. Check VDD on EVM J2 pin 1, common ground, J5 on 2-3, "
                         "SCL/SDA wiring, and that TI's GUI is closed.")
    except Exception as e:
        lines.append(f"Scan error: {e}")
    finally:
        if smu:
            try:
                smu.close(power_off=True)
            except Exception:
                pass
    return lines
