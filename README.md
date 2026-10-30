# DAC Validation Station

Automated bench validation for the TI **DAC53701** (10-bit) and **DAC43701** (8-bit) smart DACs.
Texas A&M University, ESET 452.

A Python GUI drives two NI PXIe-4139 source-measure units and an FT4222 I2C adapter. It runs the datasheet electrical tests, checks each result against the TI limits (SLASEY5), and writes Excel reports.

## What it tests

| Test | Measures |
|---|---|
| Functional / register | Device ID, reset defaults, register read/write, walking ones, software reset, lock |
| Static accuracy | INL, DNL, zero-code, offset, gain, full-scale error, TUE |
| Supply current | IDD in normal mode (full scale) and power-down |
| Power-down output | Hi-Z leakage (7 nA max), 10 kOhm power-down modes |
| Internal reference | VREF at 1.5x / 2x / 3x / 4x gain, zero-code error with the internal reference |
| DC PSRR | VOUT vs VDD, 4.5 V to 5.5 V |
| Output drive | Load regulation (+/-10 mA), DC output impedance |
| FB pin impedance | Manual test, J7 removed. Off by default |

Results are marked PASS / FAIL against datasheet min/max values. Specs with only a typical value are marked INFO.

## Files

| File | Purpose |
|---|---|
| `main_gui.py` | Main program. Start here |
| `hardware.py` | FT4222 I2C driver, NI SMU wrapper, bench setup, I2C bus scan |
| `limits.py` | Datasheet limits and PASS / FAIL judging |
| `report.py` | Excel report writer (maroon headers, scatter charts) |
| `runner.py` | Runs the selected tests and writes the summary file |
| `test_*.py` | One file per test (table above) |
| `logo.png` | Logo shown in the GUI header |

All files must stay in the same folder.

## Requirements

- Windows PC with Python 3.10 or newer
- NI-DCPower driver (PXIe-4139 SMUs) and the FTDI FT4222 driver
- `pip install ft4222 nidcpower openpyxl`

`hardware.py` imports `nidcpower` at startup, so the NI driver must be installed even to open the GUI.

## Hardware setup (DAC53701EVM)

| Connection | Setting |
|---|---|
| smu1 (VDD) | HI to J2 pin 1 (DAC_VDD), LO to J1 pin 1 (GND) |
| smu2 (VOUT) | HI to TP2 (VOUT), LO to GND |
| J3 | **Open** |
| J5 | 2-3 |
| J6 | Open |
| J7 | In |
| USB | Plugged into the PC. Close TI's own GUI |

**Never short J3 while a supply is connected to J2 pin 1.**

## Run from source

```
python main_gui.py
```

1. Click **Check hardware** to confirm the FT4222 and both SMUs are found.
2. Pick the part (Auto detects it), I2C address (0x48 to 0x4B), VDD and sweep mode.
3. Click **START**. **Stop** ends the run safely and the supply is always shut down.

Other options: remote sense on VOUT, write-only I2C mode (skips tests that need read-back), **Scan I2C bus**, run name, output folder, timestamp.

## Run the executable

Download `DAC_Validation_Station.exe` from the Releases page. NI-DCPower and the FT4222 driver still need to be installed. Keep `logo.png` next to the exe if it was not bundled.

## Build the executable

```
pip install pyinstaller
python -m PyInstaller --onefile --windowed --clean --name DAC_Validation_Station --add-data "logo.png;." --collect-all ft4222 --collect-all nidcpower --collect-all openpyxl --hidden-import et_xmlfile main_gui.py
```

The exe is created in `dist/`.

## Output

Each test saves its own Excel file in the output folder (default `~/Documents/DAC_logs`), named `<run name>_<test>[_<timestamp>].xlsx`, with a Summary sheet, a Run_Info sheet and one tab per measurement with a chart. A `..._SUMMARY.xlsx` collects every result from the run.

## Status

- **DAC53701 on the EVM:** full suite run and compared against the datasheet.
- **DAC43701 on the team PCB:** under bring-up. The part does not yet ACK at 0x48. Power-up supply current was about 30 uA against an 80 uA typical, so power delivery and the part itself are being checked.

## Known limits

- Output impedance at code 1016 can hit the SMU voltage limit. A 6 V limit with remote sense is planned.
- Room temperature only.
- FB impedance needs manual jumper and lead changes.

## Reference

TI DAC53701 / DAC43701 datasheet, SLASEY5.
