#!/usr/bin/env python3
"""
main_gui.py
DAC53701 Validation Station - main GUI. Calls the separate test files:
  test_functional, test_static, test_supply, test_powerdown,
  test_reference, test_psrr, test_output, test_fb_impedance
Each selected test writes its own Excel file, plus one overall SUMMARY file.

Logo: put your own image named "logo.png" next to this file (or next to the .exe).
If it is missing, the header shows text only.
"""

import os
import sys
import math
import queue
import threading
import re
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from hardware import check_hardware, scan_i2c
from limits import SPECS, judge
from runner import Context, run_suite
import test_functional
import test_static
import test_supply
import test_powerdown
import test_reference
import test_psrr
import test_output
import test_fb_impedance

APP_TITLE = "DAC53701 Validation Station"
TESTS = [test_functional, test_static, test_supply, test_powerdown,
         test_reference, test_psrr, test_output, test_fb_impedance]
DEFAULT_ON = {"fb_impedance": False}          # manual test is off by default

DEFAULTS = {
    "vdd_smu": "smu1",
    "vout_smu": "smu2",
    "vdd": 5.5,
    "plf": 60.0,
    "run_name": "dac53701_evm",
    "folder": os.path.join(os.path.expanduser("~"), "Documents", "DAC_logs"),
}

# ---- Texas A&M colors ----
MAROON = "#500000"
MAROON_DARK = "#3C0000"
MAROON_LIGHT = "#732F2F"
WHITE = "#FFFFFF"
BG = "#F4F2F0"
GRAY = "#707373"
TEXT = "#1A1A1A"
PASS_BG, FAIL_BG, WARN_BG = "#D8EFD9", "#F6D3D3", "#FFF1C7"
FONT = "Segoe UI"


def resource_path(name):
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(os.path.dirname(sys.executable), name))
        candidates.append(os.path.join(getattr(sys, "_MEIPASS", ""), name))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), name))
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.configure(bg=BG)
        self.minsize(1180, 760)
        self.q = queue.Queue()
        self.stop_evt = threading.Event()
        self.worker = None
        self.logo = None

        self._styles()
        self._vars()
        self._header()
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=(10, 0))
        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="y")
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(14, 0))
        self._left_panel(left)
        self._right_panel(right)
        self._footer()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self.poll)

    # ------------------------------------------------------------ styling
    def _styles(self):
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure(".", background=BG, foreground=TEXT, font=(FONT, 10))
        st.configure("TFrame", background=BG)
        st.configure("Card.TLabelframe", background=WHITE, bordercolor=MAROON, relief="solid", borderwidth=1)
        st.configure("Card.TLabelframe.Label", background=WHITE, foreground=MAROON, font=(FONT, 10, "bold"))
        st.configure("Card.TLabel", background=WHITE, foreground=TEXT)
        st.configure("Hint.TLabel", background=WHITE, foreground=GRAY, font=(FONT, 8))
        st.configure("Card.TCheckbutton", background=WHITE, foreground=TEXT)
        st.map("Card.TCheckbutton", background=[("active", WHITE)])
        st.configure("Card.TRadiobutton", background=WHITE, foreground=TEXT)
        st.map("Card.TRadiobutton", background=[("active", WHITE)])
        st.configure("TEntry", fieldbackground=WHITE)
        st.configure("Maroon.TButton", background=MAROON, foreground=WHITE, font=(FONT, 10, "bold"),
                     borderwidth=0, padding=(18, 8))
        st.map("Maroon.TButton", background=[("disabled", "#B9A3A3"), ("active", MAROON_LIGHT)],
               foreground=[("disabled", "#EEE")])
        st.configure("Plain.TButton", background=WHITE, foreground=MAROON, font=(FONT, 10, "bold"),
                     bordercolor=MAROON, borderwidth=1, padding=(14, 7))
        st.map("Plain.TButton", background=[("active", "#F3E9E9"), ("disabled", WHITE)],
               foreground=[("disabled", "#B9A3A3")])
        st.configure("Small.TButton", background=WHITE, foreground=MAROON, padding=(8, 3),
                     bordercolor=MAROON, borderwidth=1)
        st.configure("Maroon.Horizontal.TProgressbar", troughcolor="#E6DCDC", background=MAROON,
                     bordercolor="#E6DCDC", lightcolor=MAROON, darkcolor=MAROON, thickness=14)
        st.configure("Treeview", background=WHITE, fieldbackground=WHITE, rowheight=24, font=(FONT, 9))
        st.configure("Treeview.Heading", background=MAROON, foreground=WHITE, font=(FONT, 9, "bold"),
                     relief="flat")
        st.map("Treeview.Heading", background=[("active", MAROON_LIGHT)])
        st.map("Treeview", background=[("selected", "#E8D6D6")], foreground=[("selected", TEXT)])

    def _vars(self):
        self.vdd_smu = tk.StringVar(value=DEFAULTS["vdd_smu"])
        self.vout_smu = tk.StringVar(value=DEFAULTS["vout_smu"])
        self.vdd = tk.StringVar(value=str(DEFAULTS["vdd"]))
        self.plf = tk.StringVar(value="60")
        self.remote = tk.BooleanVar(value=False)
        self.write_only = tk.BooleanVar(value=False)
        self.i2c_addr = tk.StringVar(value="0x48")
        self.part = tk.StringVar(value="Auto")
        self.sweep = tk.StringVar(value="carry")
        self.run_name = tk.StringVar(value=DEFAULTS["run_name"])
        self.folder = tk.StringVar(value=DEFAULTS["folder"])
        self.stamp = tk.BooleanVar(value=True)
        self.test_vars = {m.TAG: tk.BooleanVar(value=DEFAULT_ON.get(m.TAG, True)) for m in TESTS}
        self.status = tk.StringVar(value="Ready")
        self.test_label = tk.StringVar(value="No test running")
        self.step_label = tk.StringVar(value="")

    # ------------------------------------------------------------ layout
    def _header(self):
        bar = tk.Frame(self, bg=MAROON, height=86)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        path = resource_path("logo.png")
        if path:
            try:
                img = tk.PhotoImage(file=path)
                factor = max(1, math.ceil(img.height() / 64))
                self.logo = img.subsample(factor, factor)
                tk.Label(bar, image=self.logo, bg=MAROON).pack(side="left", padx=(18, 12), pady=10)
                self.iconphoto(True, img.subsample(max(1, math.ceil(img.height() / 32))))
            except tk.TclError:
                self.logo = None
        text = tk.Frame(bar, bg=MAROON)
        text.pack(side="left", padx=(18 if not self.logo else 0, 0))
        tk.Label(text, text=APP_TITLE, bg=MAROON, fg=WHITE, font=(FONT, 20, "bold")).pack(anchor="w")
        tk.Label(text, text="Texas A&M University  |  Electronic Systems Engineering Technology",
                 bg=MAROON, fg="#E8D6D6", font=(FONT, 10)).pack(anchor="w")
        tk.Label(bar, text="PXIe-4139 x2  +  FT4222 I2C  +  DAC53701EVM", bg=MAROON, fg="#E8D6D6",
                 font=(FONT, 9)).pack(side="right", padx=18)
        tk.Frame(self, bg=MAROON_DARK, height=4).pack(fill="x")

    def _left_panel(self, parent):
        inst = ttk.LabelFrame(parent, text="Instruments", style="Card.TLabelframe", padding=10)
        inst.pack(fill="x", pady=(0, 10))
        rows = [("VDD SMU (supply, J2 pin 1)", self.vdd_smu), ("VOUT SMU (measure, TP2)", self.vout_smu),
                ("VDD (V)", self.vdd)]
        for r, (label, var) in enumerate(rows):
            ttk.Label(inst, text=label, style="Card.TLabel").grid(row=r, column=0, sticky="w", pady=3)
            ttk.Entry(inst, textvariable=var, width=14).grid(row=r, column=1, sticky="w", padx=(8, 0))
        ttk.Label(inst, text="Line frequency (Hz)", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Combobox(inst, textvariable=self.plf, values=["60", "50"], width=11,
                     state="readonly").grid(row=3, column=1, sticky="w", padx=(8, 0))
        ttk.Checkbutton(inst, text="VOUT SMU remote sense wired (J1 pin 5)", variable=self.remote,
                        style="Card.TCheckbutton").grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Label(inst, text="DAC part", style="Card.TLabel").grid(row=8, column=0, sticky="w", pady=3)
        ttk.Combobox(inst, textvariable=self.part, values=["Auto", "DAC53701", "DAC43701"], width=11,
                     state="readonly").grid(row=8, column=1, sticky="w", padx=(8, 0))
        ttk.Label(inst, text="Auto reads the device ID (3 = DAC53701, 5 = DAC43701)",
                  style="Hint.TLabel").grid(row=9, column=0, columnspan=2, sticky="w", padx=(22, 0))
        ttk.Label(inst, text="DAC I2C address", style="Card.TLabel").grid(row=5, column=0, sticky="w", pady=3)
        ttk.Combobox(inst, textvariable=self.i2c_addr, values=["0x48", "0x49", "0x4A", "0x4B"], width=11,
                     state="readonly").grid(row=5, column=1, sticky="w", padx=(8, 0))
        ttk.Checkbutton(inst, text="Write-only I2C (no read-back)", variable=self.write_only,
                        style="Card.TCheckbutton").grid(row=6, column=0, columnspan=2, sticky="w")
        ttk.Label(inst, text="Skips ID check and register tests; confirms writes by measuring VOUT",
                  style="Hint.TLabel").grid(row=7, column=0, columnspan=2, sticky="w", padx=(22, 0))

        tests = ttk.LabelFrame(parent, text="Tests", style="Card.TLabelframe", padding=10)
        tests.pack(fill="x", pady=(0, 10))
        for r, m in enumerate(TESTS):
            ttk.Checkbutton(tests, text=m.NAME, variable=self.test_vars[m.TAG],
                            style="Card.TCheckbutton").grid(row=2 * r, column=0, sticky="w")
            ttk.Label(tests, text=m.DESCRIPTION, style="Hint.TLabel").grid(row=2 * r + 1, column=0,
                                                                           sticky="w", padx=(22, 0))
        btns = tk.Frame(tests, bg=WHITE)
        btns.grid(row=2 * len(TESTS), column=0, sticky="w", pady=(6, 0))
        ttk.Button(btns, text="Select all", style="Small.TButton",
                   command=lambda: self._select(True)).pack(side="left")
        ttk.Button(btns, text="Clear", style="Small.TButton",
                   command=lambda: self._select(False)).pack(side="left", padx=6)

        sw = ttk.LabelFrame(parent, text="Static sweep", style="Card.TLabelframe", padding=10)
        sw.pack(fill="x", pady=(0, 10))
        ttk.Radiobutton(sw, text="Major carry (32 transitions, fast)", value="carry", variable=self.sweep,
                        style="Card.TRadiobutton").pack(anchor="w")
        ttk.Radiobutton(sw, text="Every code (1024 or 256 codes)", value="full", variable=self.sweep,
                        style="Card.TRadiobutton").pack(anchor="w")

        out = ttk.LabelFrame(parent, text="Output", style="Card.TLabelframe", padding=10)
        out.pack(fill="x")
        ttk.Label(out, text="Run name", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(out, textvariable=self.run_name, width=30).grid(row=0, column=1, columnspan=2, sticky="w", padx=8)
        ttk.Label(out, text="Folder", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(out, textvariable=self.folder, width=30).grid(row=1, column=1, sticky="w", padx=8)
        ttk.Button(out, text="Browse", style="Small.TButton", command=self.browse).grid(row=1, column=2)
        ttk.Checkbutton(out, text="Append date/time to file names", variable=self.stamp,
                        style="Card.TCheckbutton").grid(row=2, column=0, columnspan=3, sticky="w")
        ttk.Button(out, text="Open folder", style="Small.TButton",
                   command=self.open_folder).grid(row=3, column=0, sticky="w", pady=(6, 0))

    def _right_panel(self, parent):
        ctl = tk.Frame(parent, bg=BG)
        ctl.pack(fill="x")
        self.start_btn = ttk.Button(ctl, text="START", style="Maroon.TButton", command=self.start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(ctl, text="Stop", style="Plain.TButton", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=8)
        self.check_btn = ttk.Button(ctl, text="Check hardware", style="Plain.TButton", command=self.check_hw)
        self.check_btn.pack(side="left")
        self.scan_btn = ttk.Button(ctl, text="Scan I2C bus", style="Plain.TButton", command=self.scan_bus)
        self.scan_btn.pack(side="left", padx=8)

        prog = tk.Frame(parent, bg=WHITE, highlightbackground=MAROON, highlightthickness=1)
        prog.pack(fill="x", pady=10)
        tk.Label(prog, textvariable=self.test_label, bg=WHITE, fg=MAROON,
                 font=(FONT, 10, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
        self.test_pb = ttk.Progressbar(prog, style="Maroon.Horizontal.TProgressbar", mode="determinate")
        self.test_pb.pack(fill="x", padx=10)
        tk.Label(prog, textvariable=self.step_label, bg=WHITE, fg=GRAY, font=(FONT, 9)).pack(anchor="w",
                                                                                          padx=10, pady=(6, 2))
        self.step_pb = ttk.Progressbar(prog, style="Maroon.Horizontal.TProgressbar", mode="determinate")
        self.step_pb.pack(fill="x", padx=10, pady=(0, 10))

        res = tk.Frame(parent, bg=BG)
        res.pack(fill="both", expand=True)
        cols = ("spec", "measured", "unit", "limits", "result")
        self.tree = ttk.Treeview(res, columns=cols, show="headings", height=11)
        for c, w, txt in (("spec", 300, "Specification"), ("measured", 110, "Measured"),
                          ("unit", 70, "Unit"), ("limits", 170, "Min / Typ / Max"), ("result", 80, "Result")):
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w, anchor="w" if c == "spec" else "center")
        self.tree.tag_configure("PASS", background=PASS_BG)
        self.tree.tag_configure("FAIL", background=FAIL_BG)
        self.tree.tag_configure("WARN", background=WARN_BG)
        sb = ttk.Scrollbar(res, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        logf = tk.Frame(parent, bg=BG)
        logf.pack(fill="both", expand=True, pady=(10, 0))
        self.log = tk.Text(logf, height=10, bg="#1E1414", fg="#F2E6E6", insertbackground=WHITE,
                           font=("Consolas", 9), relief="flat", state="disabled", wrap="word")
        lsb = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        self.log.pack(side="left", fill="both", expand=True)
        lsb.pack(side="left", fill="y")

    def _footer(self):
        bar = tk.Frame(self, bg=MAROON_DARK, height=26)
        bar.pack(fill="x", side="bottom", pady=(10, 0))
        tk.Label(bar, textvariable=self.status, bg=MAROON_DARK, fg=WHITE, font=(FONT, 9)).pack(side="left", padx=12)
        tk.Label(bar, text="Room temperature  |  Limits: TI SLASEY5", bg=MAROON_DARK, fg="#E8D6D6",
                 font=(FONT, 9)).pack(side="right", padx=12)

    # ------------------------------------------------------------ helpers
    def _select(self, on):
        for tag, v in self.test_vars.items():
            v.set(on if tag != "fb_impedance" else False)

    def browse(self):
        d = filedialog.askdirectory(initialdir=self.folder.get() or DEFAULTS["folder"])
        if d:
            self.folder.set(d)

    def open_folder(self):
        folder = self.folder.get().strip() or DEFAULTS["folder"]
        os.makedirs(folder, exist_ok=True)
        try:
            os.startfile(folder)
        except AttributeError:
            messagebox.showinfo("Folder", folder)

    def write_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_running(self, running):
        for b in (self.start_btn, self.check_btn, self.scan_btn):
            b.configure(state="disabled" if running else "normal")
        self.stop_btn.configure(state="normal" if running else "disabled")

    @staticmethod
    def _limits_text(sid):
        s = SPECS[sid]
        parts = ["-" if s[k] is None else f"{s[k]:g}" for k in ("min", "typ", "max")]
        return " / ".join(parts)

    def show_result(self, sid, val):
        result = judge(sid, val)
        meas = f"{val:.5g}" if isinstance(val, float) else str(val)
        values = (SPECS[sid]["name"], meas, SPECS[sid]["unit"], self._limits_text(sid), result)
        if self.tree.exists(sid):
            self.tree.item(sid, values=values, tags=(result,))
        else:
            self.tree.insert("", "end", iid=sid, values=values, tags=(result,))
        self.tree.see(sid)

    # ------------------------------------------------------------ actions
    def check_hw(self):
        self.status.set("Checking hardware...")
        self.update_idletasks()
        lines = check_hardware(self.vdd_smu.get().strip(), self.vout_smu.get().strip())
        for line in lines:
            self.write_log(line)
        self.status.set("Ready")
        messagebox.showinfo("Hardware check", "\n".join(lines))

    def scan_bus(self):
        try:
            vdd = float(self.vdd.get())
        except ValueError:
            messagebox.showerror("Input error", "Check the VDD value.")
            return
        power = messagebox.askyesnocancel(
            "Scan I2C bus",
            f"Power VDD from {self.vdd_smu.get().strip()} at {vdd} V during the scan?\n\n"
            "Yes = SMU powers VDD (J3 open setup)\nNo = VDD already powered (USB, J3 closed)")
        if power is None:
            return
        self.status.set("Scanning I2C bus...")
        self.update_idletasks()
        lines = scan_i2c(self.vdd_smu.get().strip(), vdd, float(self.plf.get()), power=power)
        self.write_log("I2C scan:")
        for line in lines:
            self.write_log("  " + line)
        self.status.set("Ready")
        messagebox.showinfo("I2C scan", "\n".join(lines))

    def _settings(self):
        vdd = float(self.vdd.get())
        if not 1.8 <= vdd <= 5.5:
            raise ValueError("VDD must be between 1.8 and 5.5 V.")
        name = self.run_name.get().strip()
        if name.lower().endswith(".xlsx"):
            name = name[:-5]
        name = re.sub(r'[<>:"/\\|?*]', "_", name).strip() or DEFAULTS["run_name"]
        return {"vdd_smu": self.vdd_smu.get().strip(), "vout_smu": self.vout_smu.get().strip(),
                "vdd": vdd, "plf": float(self.plf.get()), "remote_sense": self.remote.get(),
                "sweep": self.sweep.get(), "run_name": name,
                "write_only": self.write_only.get(), "i2c_addr": int(self.i2c_addr.get(), 16),
                "part": self.part.get(),
                "folder": self.folder.get().strip() or DEFAULTS["folder"], "stamp": self.stamp.get()}

    def start(self):
        try:
            settings = self._settings()
        except ValueError as e:
            messagebox.showerror("Input error", str(e) or "Check the VDD value.")
            return
        mods = [m for m in TESTS if self.test_vars[m.TAG].get()]
        if not mods:
            messagebox.showerror("Input error", "Select at least one test.")
            return
        try:
            os.makedirs(settings["folder"], exist_ok=True)
        except OSError as e:
            messagebox.showerror("Folder error", f"Cannot use that folder:\n{e}")
            return
        if not settings["stamp"]:
            existing = [m.TAG for m in mods
                        if os.path.exists(os.path.join(settings["folder"], f"{settings['run_name']}_{m.TAG}.xlsx"))]
            if existing and not messagebox.askyesno(
                    "Files exist", "Files for these tests already exist and will be overwritten:\n"
                    + ", ".join(existing) + "\n\nContinue?"):
                return

        for item in self.tree.get_children():
            self.tree.delete(item)
        self.test_pb["value"] = self.step_pb["value"] = 0
        self.stop_evt.clear()
        self._set_running(True)
        self.status.set("Running...")
        self.write_log(f"\n##### Run started {datetime.now():%Y-%m-%d %H:%M:%S} #####")

        ctx = Context(settings,
                      log=lambda m: self.q.put(("log", m)),
                      progress=lambda kind, i, n, label: self.q.put(("progress", kind, i, n, label)),
                      stop_evt=self.stop_evt,
                      confirm=self._confirm_from_worker,
                      result=lambda sid, val: self.q.put(("result", sid, val)))
        self.worker = threading.Thread(target=self._work, args=(mods, ctx), daemon=True)
        self.worker.start()

    def _work(self, mods, ctx):
        try:
            specs, statuses = run_suite(mods, ctx)
            self.q.put(("done", specs, statuses))
        except Exception as e:
            self.q.put(("log", f"ERROR: {e}"))
            self.q.put(("done", {}, [("Run", f"Error: {e}")]))

    def _confirm_from_worker(self, text):
        ev = threading.Event()
        box = {}
        self.q.put(("confirm", text, ev, box))
        ev.wait()
        return box.get("ok", False)

    def stop(self):
        self.stop_evt.set()
        self.status.set("Stopping after the current step...")

    def poll(self):
        while not self.q.empty():
            msg = self.q.get()
            kind = msg[0]
            if kind == "log":
                self.write_log(msg[1])
            elif kind == "progress":
                _, which, i, n, label = msg
                if which == "test":
                    self.test_pb["maximum"], self.test_pb["value"] = n, i - 1
                    self.test_label.set(f"Test {i} of {n}:  {label}")
                    self.step_pb["value"] = 0
                    self.step_label.set("")
                else:
                    self.step_pb["maximum"], self.step_pb["value"] = n, i
                    self.step_label.set(f"{label}  ({i}/{n})")
            elif kind == "result":
                self.show_result(msg[1], msg[2])
            elif kind == "confirm":
                _, text, ev, box = msg
                box["ok"] = messagebox.askokcancel("Manual setup", text)
                ev.set()
            elif kind == "done":
                _, specs, statuses = msg
                self._set_running(False)
                self.test_pb["value"] = self.test_pb["maximum"]
                n_fail = sum(1 for sid, v in specs.items() if judge(sid, v) == "FAIL")
                n_pass = sum(1 for sid, v in specs.items() if judge(sid, v) == "PASS")
                self.test_label.set("Run finished")
                self.status.set(f"Finished: {n_pass} pass, {n_fail} fail, {len(specs)} results")
                lines = [f"{n}: {s}" for n, s in statuses]
                messagebox.showinfo("Run finished",
                                    f"{n_pass} PASS, {n_fail} FAIL, {len(specs)} results\n\n" + "\n".join(lines)
                                    + f"\n\nFiles saved in:\n{self.folder.get()}")
        self.after(100, self.poll)

    def on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Test running", "A test is running. Stop it and close?"):
                return
            self.stop_evt.set()
            self.worker.join(timeout=15)
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
