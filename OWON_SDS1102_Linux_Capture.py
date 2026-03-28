#!/usr/bin/env python3
import serial
import time
import json
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
import threading
import re

class OwonScopeGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Owon SDS1102 - Waveform Analysis Tool")
        self.root.geometry("1200x900")
        
        # Desktop integration style
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.root.configure(bg=self.style.lookup('TFrame', 'background'))

        self.stop_event = threading.Event()
        self.port = "/dev/ttyUSB0"
        self.is_auto_refreshing = False
        self.is_running = True
        self.current_config = None
        self.channel_data = {}

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # --- Top Control Panel ---
        top_frame = ttk.Frame(root, padding="10")
        top_frame.pack(side=tk.TOP, fill=tk.X)

        self.btn_download = ttk.Button(top_frame, text="Download Now", command=self.manual_download)
        self.btn_download.pack(side=tk.LEFT, padx=5)

        self.btn_start = ttk.Button(top_frame, text="▶ Start Live", command=self.start_auto)
        self.btn_start.pack(side=tk.LEFT, padx=5)

        self.btn_stop = ttk.Button(top_frame, text="■ Stop", command=self.stop_auto, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        ttk.Separator(top_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=15)
        self.entry_filename = ttk.Entry(top_frame, width=20)
        self.entry_filename.insert(0, "scope_capture")
        self.entry_filename.pack(side=tk.LEFT, padx=5)

        self.btn_save = ttk.Button(top_frame, text="Save Data", command=self.save_to_file)
        self.btn_save.pack(side=tk.LEFT, padx=5)

        # --- Status Bar (Moved above the plot, black background) ---
        self.status_bar = tk.Frame(root, bg="black", height=35, padx=10)
        self.status_bar.pack(side=tk.TOP, fill=tk.X)

        self.stat_msg = tk.Label(self.status_bar, text="Ready", bg="black", fg="#00FF00", font=("Arial", 9, "bold"), width=15, anchor="w")
        self.stat_msg.pack(side=tk.LEFT)

        self.stat_ch1 = tk.Label(self.status_bar, text="CH1: ---", bg="black", fg="#FFFF00", font=("Monospace", 10), width=55, anchor="w")
        self.stat_ch1.pack(side=tk.LEFT, padx=20)

        self.stat_ch2 = tk.Label(self.status_bar, text="CH2: ---", bg="black", fg="#00FFFF", font=("Monospace", 10), width=55, anchor="w")
        self.stat_ch2.pack(side=tk.LEFT, padx=20)

        # --- Plotting Area ---
        plt.style.use('dark_background')
        self.fig, self.ax1 = plt.subplots(figsize=(10, 6), facecolor='#1e1e1e', constrained_layout=True) # veľkosť v palcoch default DPI = 100, teda veľkosť v bodoch = 1000x600
        self.ax2 = self.ax1.twinx() 
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1, padx=10, pady=10)
        
        self.reset_axes()

    def reset_axes(self):
        for ax in [self.ax1, self.ax2]:
            ax.set_facecolor("black")
            ax.grid(False)
        self.ax1.grid(True, color='#222222', linestyle='--')
        self.canvas.draw()

    def parse_value(self, s):
        if not s: return 1.0
        val_match = re.search(r"([-+]?\d*\.\d+|\d+)", s)
        if not val_match: return 1.0
        n = float(val_match.group(1))
        low = s.lower()
        # Sample rates: check original case to distinguish MS/s vs ms
        if 'GS/' in s: n *= 1e9
        elif 'MS/' in s: n *= 1e6
        elif 'kS/' in s or 'KS/' in s: n *= 1e3
        # Voltage and time units (case-insensitive)
        elif 'mv' in low: n *= 0.001
        elif 'us' in low or 'μs' in low: n *= 1e-6
        elif 'ms' in low: n *= 1e-3
        elif 'ns' in low: n *= 1e-9
        return n

    def on_closing(self):
        self.is_auto_refreshing = False
        self.stop_event.set()
        try:
            self.root.quit()
            self.root.destroy()
        except:
            pass
        sys.exit(0)

    def fetch_data(self):
        try:
            with serial.Serial(self.port, 115200, timeout=1.5) as ser:
                ser.write(b':DATA:WAVE:DEPMEM:All?\r\n')
                header = ser.read_until(b'{"')
                if not header.endswith(b'{"'): return None
                
                json_len = int.from_bytes(header[-6:-2], byteorder='little')
                raw_json = (b'{"' + ser.read(json_len - 2)).decode('utf-8', errors='ignore')
                if '}' in raw_json:
                    raw_json = raw_json[:raw_json.rfind('}') + 1]
                
                config = json.loads(raw_json)
                data = {}
                for ch in [c for c in config['CHANNEL'] if c['DISPLAY'] == 'ON']:
                    l_hdr = ser.read(4)
                    if not l_hdr: break
                    b_len = int.from_bytes(l_hdr, byteorder='little')
                    raw_bytes = b''
                    while len(raw_bytes) < b_len:
                        if self.stop_event.is_set(): return None
                        raw_bytes += ser.read(min(8192, b_len - len(raw_bytes)))
                    data[ch['NAME']] = np.frombuffer(raw_bytes, dtype=np.int16)
                return config, data
        except:
            return None

    def update_ui(self, config, data):
        if not data or self.stop_event.is_set(): return
        self.current_config, self.channel_data = config, data
        
        self.ax1.clear(); self.ax2.clear()
        self.reset_axes()

        # Timebase
        sr_val = self.parse_value(config['SAMPLE']['SAMPLERATE'])
        datalen = config['SAMPLE']['DATALEN']
        t_vec = np.arange(datalen) * (1.0 / sr_val)
        t_scale = self.parse_value(config['TIMEBASE']['SCALE'])  # seconds per division
        xf, xu = (1e6, "μs") if t_vec[-1] < 1e-3 else (1e3, "ms") if t_vec[-1] < 1 else (1.0, "s")
        t_scale_disp = t_scale * xf  # time scale in display units

        # Vertical Calibration: 50 units = 1 Division. 8 Divisions total.
        UNITS_PER_DIV = 50.0

        for ch in config['CHANNEL']:
            name = ch['NAME']
            if name in data:
                raw_wave = data[name][:datalen].astype(float)
                raw_min, raw_max = int(np.min(data[name][:datalen])), int(np.max(data[name][:datalen]))
                v_scale = self.parse_value(ch['SCALE'])
                probe_match = re.findall(r"(\d+)", ch['PROBE'])
                probe = float(probe_match[0]) if probe_match else 1.0
                offset_units = float(ch['OFFSET'])
                ratio = float(ch.get('Current_Ratio', 1.0))

                # 12-bit ADC (4096 counts), 10 divisions total on screen
                # OFFSET shifts zero line: 1 div = UNITS_PER_DIV units
                counts_per_div = 4096.0 / 10.0  # = 409.6 counts per division
                zero_raw = (offset_units / UNITS_PER_DIV) * counts_per_div
                volt_wave = (raw_wave - zero_raw) / counts_per_div * v_scale * probe

                # Screen height is 10 divs (+/- 5 divs from center)
                # Offset shifted by 'offset_units' units
                v_center_rel_to_zero = -(offset_units / UNITS_PER_DIV) * v_scale * probe
                v_min_lim = v_center_rel_to_zero - (5.0 * v_scale * probe)
                v_max_lim = v_center_rel_to_zero + (5.0 * v_scale * probe)

                v_min, v_max = np.min(volt_wave), np.max(volt_wave)

                # Y axis ticks: one tick per division (v_scale volts)
                y_ticks = np.arange(
                    np.ceil(v_min_lim / v_scale) * v_scale,
                    v_max_lim + v_scale * 0.5,
                    v_scale * probe
                )

                if name == 'CH1':
                    self.ax1.plot(t_vec * xf, volt_wave, color='#FFFF00', label='CH1', linewidth=1)
                    self.ax1.set_ylabel(f"CH1 [{ch['SCALE']}/div]", color='#FFFF00')
                    self.ax1.set_ylim(v_min_lim, v_max_lim)
                    self.ax1.set_yticks(y_ticks)
                    self.ax1.tick_params(axis='y', labelcolor='#FFFF00')
                    self.stat_ch1.config(text=f"CH1: Max {v_max:.3f}V  Min {v_min:.3f}V  raw[{raw_min},{raw_max}]")
                else:
                    self.ax2.plot(t_vec * xf, volt_wave, color='#00FFFF', label='CH2', linewidth=1)
                    self.ax2.set_ylabel(f"CH2 [{ch['SCALE']}/div]", color='#00FFFF')
                    self.ax2.set_ylim(v_min_lim, v_max_lim)
                    self.ax2.set_yticks(y_ticks)
                    self.ax2.tick_params(axis='y', labelcolor='#00FFFF')
                    self.stat_ch2.config(text=f"CH2: Max {v_max:.3f}V  Min {v_min:.3f}V  raw[{raw_min},{raw_max}]")
            else:
                if name == 'CH1': self.stat_ch1.config(text="CH1: [OFF]")
                else: self.stat_ch2.config(text="CH2: [OFF]")

        # X axis ticks: one tick per division
        t_total = t_vec[-1] * xf
        x_ticks = np.arange(0, t_total + t_scale_disp * 0.5, t_scale_disp)
        self.ax1.set_xticks(x_ticks)
        self.ax1.set_xlim(0, t_total)

        self.ax1.set_xlabel(f"Time [{xu}]  (1 div = {config['TIMEBASE']['SCALE']})", color='#888888')
        self.ax1.set_title(f"OWON SDS1102 | Base: {config['TIMEBASE']['SCALE']}/div | {config['RUNSTATUS']}", color='white', fontsize=10)

        h1, l1 = self.ax1.get_legend_handles_labels()
        h2, l2 = self.ax2.get_legend_handles_labels()
        if h1 + h2:
            self.ax1.legend(h1 + h2, l1 + l2, loc='upper right', facecolor='#1e1e1e', framealpha=0.9)
        self.canvas.draw()

    def manual_download(self):
        self.btn_download.config(state=tk.DISABLED)
        self.stat_msg.config(text="Fetching...", fg="orange")
        def task():
            res = self.fetch_data()
            if res:
                self.root.after(0, lambda: self.update_ui(res[0], res[1]))
                self.root.after(0, lambda: self.stat_msg.config(text="OK", fg="#00FF00"))
            else:
                self.root.after(0, lambda: self.stat_msg.config(text="Timeout", fg="red"))
            if not self.is_auto_refreshing:
                self.root.after(0, lambda: self.btn_download.config(state=tk.NORMAL))
        threading.Thread(target=task, daemon=True).start()

    def start_auto(self):
        self.is_auto_refreshing = True
        self.btn_start.config(state=tk.DISABLED); self.btn_download.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL); self.stat_msg.config(text="LIVE", fg="cyan")
        def loop():
            while self.is_auto_refreshing and not self.stop_event.is_set():
                res = self.fetch_data()
                if res and self.is_auto_refreshing:
                    self.root.after(0, lambda r=res: self.update_ui(r[0], r[1]))
                time.sleep(0.1)
        threading.Thread(target=loop, daemon=True).start()

    def stop_auto(self):
        self.is_auto_refreshing = False
        self.btn_start.config(state=tk.NORMAL); self.btn_download.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED); self.stat_msg.config(text="Ready", fg="#00FF00")

    def save_to_file(self):
        if not self.channel_data: return
        path = filedialog.asksaveasfilename(initialfile=self.entry_filename.get(), defaultextension=".png", filetypes=[("PNG", "*.png")])
        if path:
            try:
                self.fig.savefig(path, facecolor='#1e1e1e', dpi=150)
                with open(os.path.splitext(path)[0] + ".json", 'w', encoding='utf-8') as f:
                    json.dump(self.current_config, f, indent=4, ensure_ascii=False)
            except Exception as e:
                sys.stderr.write(f"Error: {e}\n")

if __name__ == "__main__":
    root = tk.Tk()
    root.option_add("*Font", ("Liberation Sans", 10))
    app = OwonScopeGUI(root)
    root.mainloop()