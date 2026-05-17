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
import platform

CONFIG_PATH = os.path.join(
    os.environ.get('APPDATA', os.path.expanduser('~/.config')) if platform.system() == 'Windows'
    else os.path.expanduser('~/.config'),
    'owon_scope', 'settings.json'
)

DEFAULTS = {
    'output_dir':    os.path.expanduser('~'),
    'file_name':     'scope_capture',
    'batch_count':   '10',
    'save_png':      True,
    'save_json':     True,
}

def load_settings():
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {**DEFAULTS, **data}
    except Exception:
        return dict(DEFAULTS)

def save_settings(cfg):
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
    except Exception as e:
        sys.stderr.write(f"Settings save error: {e}\n")

class OwonScopeGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Owon SDS1102 - Waveform Analysis Tool")
        self.root.geometry("1200x900")
        
        # Desktop integration style
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.root.configure(bg=self.style.lookup('TFrame', 'background'))

        self._cfg = load_settings()
        self.stop_event = threading.Event()
        self.port = "/dev/ttyUSB0"
        self.is_auto_refreshing = False
        self.is_running = True
        self.current_config = None
        self.channel_data = {}
        self.x_min = None   # current view window in display units
        self.x_max = None
        self.t_total = None      # full data range in display units
        self.t_scale_disp = None  # current timebase in display units
        self.xf = 1.0             # time scale factor for display
        self._pan_start = None  # x position when pan started
        self._batch_running = False

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

        ttk.Separator(top_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        # Output directory selector (shared)
        ttk.Label(top_frame, text="Dir:").pack(side=tk.LEFT)
        self.entry_out_dir = ttk.Entry(top_frame, width=24)
        self.entry_out_dir.insert(0, self._cfg['output_dir'])
        self.entry_out_dir.pack(side=tk.LEFT, padx=3)
        ttk.Button(top_frame, text="…", width=2,
                   command=self._browse_dir).pack(side=tk.LEFT, padx=2)

        ttk.Separator(top_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        # File name (shared between single save and batch)
        ttk.Label(top_frame, text="Name:").pack(side=tk.LEFT)
        self.entry_filename = ttk.Entry(top_frame, width=16)
        self.entry_filename.insert(0, self._cfg['file_name'])
        self.entry_filename.pack(side=tk.LEFT, padx=3)

        self.var_save_png = tk.BooleanVar(value=self._cfg['save_png'])
        ttk.Checkbutton(top_frame, text="PNG", variable=self.var_save_png).pack(side=tk.LEFT, padx=3)
        self.var_save_json = tk.BooleanVar(value=self._cfg['save_json'])
        ttk.Checkbutton(top_frame, text="JSON", variable=self.var_save_json).pack(side=tk.LEFT, padx=3)

        self.btn_save = ttk.Button(top_frame, text="Save", command=self.save_to_file)
        self.btn_save.pack(side=tk.LEFT, padx=5)

        ttk.Separator(top_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        # --- Batch section (same row) ---
        ttk.Label(top_frame, text="Batch count:").pack(side=tk.LEFT)
        self.entry_batch_count = ttk.Entry(top_frame, width=5)
        self.entry_batch_count.insert(0, self._cfg['batch_count'])
        self.entry_batch_count.pack(side=tk.LEFT, padx=3)
        self.btn_batch = ttk.Button(top_frame, text="▶ Batch", command=self.start_batch)
        self.btn_batch.pack(side=tk.LEFT, padx=4)
        self.btn_batch_stop = ttk.Button(top_frame, text="■", width=2,
                                         command=self.stop_batch, state=tk.DISABLED)
        self.btn_batch_stop.pack(side=tk.LEFT, padx=2)
        self.lbl_batch_progress = ttk.Label(top_frame, text="")
        self.lbl_batch_progress.pack(side=tk.LEFT, padx=6)

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
        
        self.canvas.mpl_connect('scroll_event', self._on_scroll)
        self.canvas.mpl_connect('button_press_event', self._on_pan_start)
        self.canvas.mpl_connect('button_release_event', self._on_pan_end)
        self.canvas.mpl_connect('motion_notify_event', self._on_pan_move)
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
        self._persist_settings()
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
        self.canvas.mpl_connect('scroll_event', self._on_scroll)
        self.canvas.mpl_connect('button_press_event', self._on_pan_start)
        self.canvas.mpl_connect('button_release_event', self._on_pan_end)
        self.canvas.mpl_connect('motion_notify_event', self._on_pan_move)
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

                # Y axis ticks: integer multiples of v_per_div within visible range
                v_per_div = v_scale * probe
                first_tick = int(np.ceil(v_min_lim / v_per_div))
                last_tick  = int(np.floor(v_max_lim / v_per_div))
                y_ticks = np.array([i * v_per_div for i in range(first_tick, last_tick + 1)])

                # Format effective volts/div as human-readable string
                if v_per_div >= 1.0:
                    v_label = f"{v_per_div:.3g}V/div"
                else:
                    v_label = f"{v_per_div * 1000:.3g}mV/div"

                if name == 'CH1':
                    self.ax1.plot(t_vec * xf, volt_wave, color='#FFFF00', label='CH1', linewidth=1)
                    self.ax1.axhline(0, color='#FFFF00', linewidth=0.5, linestyle='-')
                    self.ax1.set_ylabel(f"CH1 [{v_label}]", color='#FFFF00')
                    self.ax1.set_ylim(v_min_lim, v_max_lim)
                    self.ax1.set_yticks(y_ticks)
                    self.ax1.tick_params(axis='y', labelcolor='#FFFF00')
                    self.stat_ch1.config(text=f"CH1: Max {v_max:.3f}V  Min {v_min:.3f}V  raw[{raw_min},{raw_max}]")
                else:
                    self.ax2.plot(t_vec * xf, volt_wave, color='#00FFFF', label='CH2', linewidth=1)
                    self.ax2.axhline(0, color='#00FFFF', linewidth=0.5, linestyle='-')
                    self.ax2.set_ylabel(f"CH2 [{v_label}]", color='#00FFFF')
                    self.ax2.set_ylim(v_min_lim, v_max_lim)
                    self.ax2.set_yticks(y_ticks)
                    self.ax2.tick_params(axis='y', labelcolor='#00FFFF')
                    self.stat_ch2.config(text=f"CH2: Max {v_max:.3f}V  Min {v_min:.3f}V  raw[{raw_min},{raw_max}]")
            else:
                if name == 'CH1':
                    self.ax1.set_yticks([])
                    self.ax1.set_ylabel("")
                    self.stat_ch1.config(text="CH1: [OFF]")
                else:
                    self.ax2.set_yticks([])
                    self.ax2.set_ylabel("")
                    self.stat_ch2.config(text="CH2: [OFF]")

        # X axis ticks and zoom window
        t_total = t_vec[-1] * xf
        # Save previous values before overwriting for change detection
        prev_total      = self.t_total
        prev_scale_disp = self.t_scale_disp
        self.t_total    = t_total
        self.xf         = xf
        self.xu         = xu
        self.t_scale_disp          = t_scale_disp
        self.timebase_scale_str    = config['TIMEBASE']['SCALE']
        # Reset view when timebase or data length changes, otherwise keep zoom/pan
        timebase_changed = (
            prev_total is None
            or prev_scale_disp is None
            or abs(t_total - prev_total) > 1e-12
            or abs(t_scale_disp - prev_scale_disp) > 1e-15
        )
        if self.x_min is None or self.x_max is None or timebase_changed:
            self.x_min, self.x_max = 0.0, t_total
        else:
            self.x_min = max(0.0, self.x_min)
            self.x_max = min(t_total, self.x_max)
            if self.x_max <= self.x_min:
                self.x_min, self.x_max = 0.0, t_total
        self._apply_xlim()

        self.ax1.set_xlabel(f"Time [{xu}]  (1 div = {config['TIMEBASE']['SCALE']})", color='#888888')
        self.ax1.set_title(f"OWON SDS1102 | Base: {config['TIMEBASE']['SCALE']}/div | {config['RUNSTATUS']}", color='white', fontsize=10)

        h1, l1 = self.ax1.get_legend_handles_labels()
        h2, l2 = self.ax2.get_legend_handles_labels()
        if h1 + h2:
            self.ax1.legend(h1 + h2, l1 + l2, loc='upper right', facecolor='#1e1e1e', framealpha=0.9)
        self.canvas.draw()

    def _apply_xlim(self):
        """Apply current x_min/x_max to axes and update ticks."""
        x_min, x_max = self.x_min, self.x_max
        self.ax1.set_xlim(x_min, x_max)
        # Ticks: integer multiples of t_scale_disp within view
        first = int(np.ceil(x_min / self.t_scale_disp))
        last  = int(np.floor(x_max / self.t_scale_disp))
        x_ticks = [i * self.t_scale_disp for i in range(first, last + 1)]
        self.ax1.set_xticks(x_ticks)
        self.canvas.draw_idle()

    def _on_scroll(self, event):
        if self.t_total is None or event.xdata is None: return
        span = self.x_max - self.x_min
        # Pixel width of axes to compute max zoom (1 sample per pixel)
        ax_width_px = self.ax1.get_window_extent().width
        samples = self.current_config['SAMPLE']['DATALEN'] if self.current_config else 1
        min_span = self.t_total / max(samples, 1) * ax_width_px  # 1 sample per pixel

        if event.key == 'shift':
            # Horizontal pan: one tick step per scroll click
            step = self.t_scale_disp * (1 if event.button == 'down' else -1)
            new_min = max(0.0, self.x_min + step)
            new_max = new_min + span
            if new_max > self.t_total:
                new_max = self.t_total
                new_min = new_max - span
            self.x_min, self.x_max = new_min, new_max
        else:
            # Zoom around cursor position
            factor = 1.3 if event.button == 'down' else 1.0 / 1.3
            new_span = span * factor
            new_span = max(min_span, min(new_span, self.t_total))
            cursor = max(x_min := event.xdata, self.x_min)
            ratio = (cursor - self.x_min) / span
            new_min = cursor - ratio * new_span
            new_max = new_min + new_span
            if new_min < 0.0:
                new_min, new_max = 0.0, new_span
            if new_max > self.t_total:
                new_max = self.t_total
                new_min = new_max - new_span
            self.x_min, self.x_max = new_min, new_max
        self._apply_xlim()

    def _on_pan_start(self, event):
        if event.button == 1 and event.xdata is not None:
            self._pan_start = event.xdata

    def _on_pan_end(self, event):
        self._pan_start = None

    def _on_pan_move(self, event):
        if self._pan_start is None or event.xdata is None: return
        dx = self._pan_start - event.xdata
        span = self.x_max - self.x_min
        new_min = max(0.0, self.x_min + dx)
        new_max = new_min + span
        if new_max > self.t_total:
            new_max = self.t_total
            new_min = new_max - span
        self.x_min, self.x_max = new_min, new_max
        self._pan_start = event.xdata  # update anchor
        self._apply_xlim()

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

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.entry_out_dir.get())
        if d:
            self.entry_out_dir.delete(0, tk.END)
            self.entry_out_dir.insert(0, d)
            self._persist_settings()

    def _persist_settings(self):
        save_settings({
            'output_dir':  self.entry_out_dir.get(),
            'file_name':   self.entry_filename.get(),
            'batch_count': self.entry_batch_count.get(),
            'save_png':    self.var_save_png.get(),
            'save_json':   self.var_save_json.get(),
        })

    def save_to_file(self):
        if not self.channel_data: return
        directory = self.entry_out_dir.get()
        stem = os.path.join(directory, self.entry_filename.get())
        try:
            if self.var_save_png.get():
                self.fig.savefig(stem + ".png", facecolor='#1e1e1e', dpi=150)
            if self.var_save_json.get():
                enriched = self._enrich_config(self.current_config, self.channel_data)
                with open(stem + ".json", 'w', encoding='utf-8') as f:
                    json.dump(enriched, f, indent=4, ensure_ascii=False)
        except Exception as e:
            sys.stderr.write(f"Error: {e}\n")
        self._persist_settings()

    def _enrich_config(self, config, data):
        """Return a copy of config with raw_min/raw_max added to each active channel."""
        import copy
        out = copy.deepcopy(config)
        datalen = config['SAMPLE']['DATALEN']
        for ch in out['CHANNEL']:
            name = ch['NAME']
            if name in data:
                raw = data[name][:datalen]
                ch['RAW_MIN'] = int(np.min(raw))
                ch['RAW_MAX'] = int(np.max(raw))
        return out

    def _save_capture(self, directory, base_name, index, config, data):
        stem = os.path.join(directory, f"{base_name}_{index:03d}")
        if self.var_save_png.get():
            self.fig.savefig(stem + ".png", facecolor='#1e1e1e', dpi=150)
        if self.var_save_json.get():
            enriched = self._enrich_config(config, data)
            with open(stem + ".json", 'w', encoding='utf-8') as f:
                json.dump(enriched, f, indent=4, ensure_ascii=False)

    def _volt_wave(self, ch, data, datalen):
        raw_wave = data[ch['NAME']][:datalen].astype(float)
        v_scale = self.parse_value(ch['SCALE'])
        probe_match = re.findall(r"(\d+)", ch['PROBE'])
        probe = float(probe_match[0]) if probe_match else 1.0
        offset_units = float(ch['OFFSET'])
        zero_raw = (offset_units / 50.0) * (4096.0 / 10.0)
        return (raw_wave - zero_raw) / (4096.0 / 10.0) * v_scale * probe

    def _compute_stats(self, all_results):
        stats = {}
        for ch_name in ('CH1', 'CH2'):
            for stat_key, volt_fn, raw_fn in [
                ('max', lambda vw: float(np.max(vw)), lambda r: int(np.max(r))),
                ('min', lambda vw: float(np.min(vw)), lambda r: int(np.min(r))),
            ]:
                volt_vals, raw_vals = [], []
                for config, data in all_results:
                    datalen = config['SAMPLE']['DATALEN']
                    for ch in config['CHANNEL']:
                        if ch['NAME'] == ch_name and ch_name in data:
                            vw = self._volt_wave(ch, data, datalen)
                            volt_vals.append(volt_fn(vw))
                            raw_vals.append(raw_fn(data[ch_name][:datalen]))
                if volt_vals:
                    stats[f"{ch_name}_{stat_key}"] = {
                        'maximum': max(volt_vals),
                        'center':  sum(volt_vals) / len(volt_vals),
                        'minimum': min(volt_vals),
                        'raw_maximum': max(raw_vals),
                        'raw_center':  round(sum(raw_vals) / len(raw_vals)),
                        'raw_minimum': min(raw_vals),
                    }
        return stats

    def start_batch(self):
        if self._batch_running: return
        try:
            count = int(self.entry_batch_count.get())
            assert count > 0
        except Exception:
            self.lbl_batch_progress.config(text="Invalid count!")
            return
        directory = self.entry_out_dir.get().strip() or os.path.expanduser('~')
        base_name = self.entry_filename.get().strip() or "capture"
        os.makedirs(directory, exist_ok=True)
        self._persist_settings()
        self._batch_running = True
        self.btn_batch.config(state=tk.DISABLED)
        self.btn_batch_stop.config(state=tk.NORMAL)

        def task():
            all_results = []
            for i in range(1, count + 1):
                if not self._batch_running: break
                self.root.after(0, lambda i=i: self.lbl_batch_progress.config(
                    text=f"Capturing {i}/{count}..."))
                res = self.fetch_data()
                if res:
                    config, data = res
                    all_results.append((config, data))
                    # update_ui and save must both run in main thread (matplotlib not thread-safe)
                    saved = threading.Event()
                    def _update_and_save(r=res, idx=i, ev=saved):
                        self.update_ui(r[0], r[1])
                        try:
                            self._save_capture(directory, base_name, idx, r[0], r[1])
                        except Exception as e:
                            sys.stderr.write(f"Save error: {e}\n")
                        ev.set()
                    self.root.after(0, _update_and_save)
                    saved.wait(timeout=15)
                else:
                    self.root.after(0, lambda i=i: self.lbl_batch_progress.config(
                        text=f"Timeout at {i}/{count}"))
                    time.sleep(0.5)
            if all_results:
                try:
                    stats = self._compute_stats(all_results)
                    with open(os.path.join(directory, "statistics.json"), 'w', encoding='utf-8') as f:
                        json.dump(stats, f, indent=4, ensure_ascii=False)
                except Exception as e:
                    sys.stderr.write(f"Stats error: {e}\n")
            n = len(all_results)
            self.root.after(0, lambda: self.lbl_batch_progress.config(
                text=f"Done: {n}/{count} saved to '{directory}'"))
            self.root.after(0, lambda: self.btn_batch.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.btn_batch_stop.config(state=tk.DISABLED))
            self._batch_running = False

        threading.Thread(target=task, daemon=True).start()

    def stop_batch(self):
        self._batch_running = False
        self.btn_batch_stop.config(state=tk.DISABLED)
        self.lbl_batch_progress.config(text="Stopping...")

if __name__ == "__main__":
    root = tk.Tk()
    root.option_add("*Font", ("Liberation Sans", 10))
    app = OwonScopeGUI(root)
    root.mainloop()
