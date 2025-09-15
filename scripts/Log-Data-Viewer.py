# picoos_log_viewer.py
"""
PicoOS Log & Data Viewer (Tkinter)
Reads binary log/data files produced by the PicoOS logger you posted and decodes them.

Usage:
    python picoos_log_viewer.py

Features:
 - Open log/data files (defaults to 'log.bin' and 'data.bin' in working dir).
 - Parse log records using heuristics for timestamp/domain encodings.
 - Parse data packets framed by SDB/MDB/EDB.
 - Filter by log level and domain, search text, export selected entries, view raw hex.
 - Tail mode to auto-refresh when files change.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import struct, time, os, threading, binascii, traceback
from datetime import datetime

# -----------------------
# Constants (copied / inferred from user's code)
# -----------------------
LOG_HDR_SOB = 0xA1  # Start Origin Byte
LOG_HDR_EOB = 0xAF  # End Origin Byte

DATA_HDR_SDB = 0xB1  # Start Data Byte
DATA_HDR_MDB = 0xB5  # Middle Data Byte
DATA_HDR_EDB = 0xBF  # End Data Byte

# Log severity bytes mapping (as in user's file)
LOG_LEVELS = {
    "FATAL": b"\x06",
    "CRITICAL": b"\x05",
    "WARN": b"\x04",
    "INFO": b"\x03",
    "DEBUG": b"\x02",
    "UNKNOWN": b"\x01",
    "OFF": b"\x00",
}
# reverse mapping from numeric byte value (int) to name
LEVEL_BY_INT = {b[0]: name for name, b in LOG_LEVELS.items()}

# Logging domain mapping (from user's LOGGING_TABLE)
LOGGING_TABLE = {
    "UNKNOWN": 0,
    "SERVICE INIT": 1,
    "SERVICE START": 2,
    "SERVICE STOP": 3,
    "SERVICE RESTART": 4,
    "PARAMETER": 5,
    "BOARD TEMP": 6,
    "SYSTEM RESTART": 7,
    "SYSTEM": 8,
    "CPU": 9,
    "RAM": 10,
    "FLASH MEMORY": 11,
    "OVERFLOW": 12
}
LOGGING_TABLE_REV = {v: k for k, v in LOGGING_TABLE.items()}

# Default filenames
DEFAULT_LOG_FILE = "log.bin"
DEFAULT_DATA_FILE = "data.bin"

# -----------------------
# Utility / parsing helpers
# -----------------------

def human_time_from_timestamp_bytes(bts):
    """
    Try various ways to interpret bts as a timestamp and return a (human, rawvalue, used_fmt) tuple.
    Heuristics:
      - if len >=8 try big-endian double (>d)
      - if len >=8 try big-endian unsigned long long (>Q)
      - if len >=4 try unsigned int (>I)
      - try ascii-decoded int
    Validate by checking reasonable unix time range (2000..2035).
    """
    now = time.time()
    plausible_min = 946684800   # Jan 1 2000
    plausible_max = 2082758400  # ~ Jan 1 2036 (very loose)
    def plausible(val):
        return plausible_min <= val <= plausible_max

    if not bts:
        return ("<no-timestamp>", None, None)

    # try double
    if len(bts) >= 8:
        try:
            d = struct.unpack(">d", bts[:8])[0]
            if plausible(d):
                return (datetime.utcfromtimestamp(int(d)).isoformat() + "Z", d, "double>8")
        except Exception:
            pass
    # try 8-byte uint
    if len(bts) >= 8:
        try:
            q = struct.unpack(">Q", bts[:8])[0]
            if plausible(q):
                return (datetime.utcfromtimestamp(q).isoformat() + "Z", q, "uint64>8")
        except Exception:
            pass
    # try 4-byte uint
    if len(bts) >= 4:
        try:
            i = struct.unpack(">I", bts[:4])[0]
            if plausible(i):
                return (datetime.utcfromtimestamp(i).isoformat() + "Z", i, "uint32>4")
        except Exception:
            pass
    # ascii decode
    try:
        s = bts.decode("ascii", "ignore")
        s_digits = ''.join(ch for ch in s if ch.isdigit())
        if s_digits:
            v = int(s_digits)
            if plausible(v):
                return (datetime.utcfromtimestamp(v).isoformat() + "Z", v, "ascii-digits")
    except Exception:
        pass

    # fallback: show raw hex and integer interpretation
    try:
        as_int = int.from_bytes(bts, "big")
        if plausible(as_int):
            return (datetime.utcfromtimestamp(as_int).isoformat() + "Z", as_int, f"int({len(bts)})")
    except Exception:
        pass

    return (f"<raw:{binascii.hexlify(bts).decode()}>", None, "unknown")

def bytes_to_printable(bts, maxlen=1024):
    try:
        s = bts.decode("utf-8", "replace")
        if len(s) > maxlen:
            s = s[:maxlen] + "...(truncated)"
        return s
    except Exception:
        return binascii.hexlify(bts).decode()

# -----------------------
# Parsing functions
# -----------------------

def parse_logs(raw: bytes):
    """
    Parse log entries heuristically from raw bytes.
    Returns list of dicts:
      {pos, level_int, level_name, timestamp_str, ts_raw_bytes, origin, domain_int, domain_name, message, raw_bytes}
    The parser scans for bytes that match known level bytes and attempts to parse each record.
    """
    entries = []
    n = len(raw)
    i = 0
    level_byte_values = set(LEVEL_BY_INT.keys())

    # helper to find next record start index given a current index
    def find_next_start(start_idx):
        for j in range(start_idx+1, n):
            if raw[j] in level_byte_values:
                # quick check: there should be a LOG_HDR_SOB somewhere after j (within next 64 bytes) - suggests start
                if raw.find(bytes([LOG_HDR_SOB]), j+1, min(n, j+1+128)) != -1:
                    return j
        return -1

    while i < n:
        b = raw[i]
        if b in level_byte_values:
            # attempt to parse record starting at i
            level_int = b
            level_name = LEVEL_BY_INT.get(level_int, f"0x{level_int:02x}")
            # find next SOB after i
            pos_sob = raw.find(bytes([LOG_HDR_SOB]), i+1)
            if pos_sob == -1:
                # no SOB -> cannot parse; treat rest as message
                message = raw[i+1:]
                ts_str, ts_val, ts_fmt = ("<no-timestamp>", None, None)
                entries.append({
                    "pos": i,
                    "level_int": level_int,
                    "level_name": level_name,
                    "timestamp_str": ts_str,
                    "timestamp_raw": b'',
                    "timestamp_fmt": ts_fmt,
                    "origin": "<no-origin>",
                    "origin_raw": b'',
                    "domain_int": None,
                    "domain_name": None,
                    "message": bytes_to_printable(message),
                    "raw": raw[i:],
                })
                break
            # timestamp bytes are between i+1 and pos_sob
            ts_bytes = raw[i+1:pos_sob]
            ts_str, ts_val, ts_fmt = human_time_from_timestamp_bytes(ts_bytes)

            # find EOB after pos_sob
            pos_eob = raw.find(bytes([LOG_HDR_EOB]), pos_sob+1)
            if pos_eob == -1:
                # broken origin; take rest as message
                origin_bytes = raw[pos_sob+1:]
                origin = bytes_to_printable(origin_bytes)
                domain_int = None
                domain_name = None
                msg_start = n
            else:
                origin_bytes = raw[pos_sob+1:pos_eob]
                try:
                    origin = origin_bytes.decode("utf-8", "ignore")
                except Exception:
                    origin = bytes_to_printable(origin_bytes)
                msg_start = pos_eob+1
                # attempt to read domain: prefer 1 byte (if maps), otherwise try to find first non-zero single-byte in next 4 bytes
                domain_int = None
                domain_name = None
                if msg_start < n:
                    candidate = raw[msg_start]
                    if candidate in LOGGING_TABLE_REV:
                        domain_int = candidate
                        domain_name = LOGGING_TABLE_REV.get(domain_int, f"0x{domain_int:02x}")
                        msg_start += 1
                    else:
                        # sometimes domain may be encoded as a single byte number but value could be zero (UNKNOWN=0)
                        # if first byte is 0 and mapping has 0, accept
                        if candidate == 0 and 0 in LOGGING_TABLE_REV:
                            domain_int = 0
                            domain_name = LOGGING_TABLE_REV[0]
                            msg_start += 1
                        else:
                            # other code path: domain might have been encoded incorrectly (bytes(n) in original)
                            # try scanning next 4 bytes for a small integer value
                            look = raw[msg_start:msg_start+4]
                            found = None
                            for offset in range(len(look)):
                                v = look[offset]
                                if v in LOGGING_TABLE_REV:
                                    found = (v, offset)
                                    break
                            if found:
                                domain_int, off = found
                                domain_name = LOGGING_TABLE_REV.get(domain_int, None)
                                msg_start += (off+1)
                # else no domain, message directly follows

            # determine end of message: heuristics -> next record start
            next_start = find_next_start(msg_start-1)
            if next_start == -1:
                message_bytes = raw[msg_start:]
                next_i = n
            else:
                message_bytes = raw[msg_start:next_start]
                next_i = next_start

            entries.append({
                "pos": i,
                "level_int": level_int,
                "level_name": level_name,
                "timestamp_str": ts_str,
                "timestamp_raw": ts_bytes,
                "timestamp_fmt": ts_fmt,
                "origin": origin,
                "origin_raw": origin_bytes,
                "domain_int": domain_int,
                "domain_name": domain_name,
                "message": bytes_to_printable(message_bytes),
                "message_raw": message_bytes,
                "raw": raw[i:next_i],
            })
            i = next_i
        else:
            i += 1

    return entries

def parse_data_packets(raw: bytes):
    """
    Parse data packets formatted as:
      SDB (0xB1) + name bytes + MDB (0xB5) + data bytes + EDB (0xBF)
    Returns list of {pos, name, value, name_raw, value_raw, raw}
    """
    entries = []
    idx = 0
    n = len(raw)
    while idx < n:
        pos = raw.find(bytes([DATA_HDR_SDB]), idx)
        if pos == -1:
            break
        pos_name_start = pos + 1
        pos_mdb = raw.find(bytes([DATA_HDR_MDB]), pos_name_start)
        if pos_mdb == -1:
            break
        name_raw = raw[pos_name_start:pos_mdb]
        pos_edb = raw.find(bytes([DATA_HDR_EDB]), pos_mdb+1)
        if pos_edb == -1:
            break
        value_raw = raw[pos_mdb+1:pos_edb]
        try:
            name = name_raw.decode("utf-8", "ignore")
        except Exception:
            name = bytes_to_printable(name_raw)
        try:
            value = value_raw.decode("utf-8", "ignore")
        except Exception:
            value = bytes_to_printable(value_raw)
        entries.append({
            "pos": pos,
            "name": name,
            "value": value,
            "name_raw": name_raw,
            "value_raw": value_raw,
            "raw": raw[pos:pos_edb+1],
        })
        idx = pos_edb + 1
    return entries

# -----------------------
# Tkinter GUI
# -----------------------

class PicoLogViewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PicoOS Log & Data Viewer")
        self.geometry("1100x700")
        self.create_widgets()
        self.log_file = DEFAULT_LOG_FILE
        self.data_file = DEFAULT_DATA_FILE
        self.parsed_logs = []
        self.parsed_data = []
        self.tail_running = False
        self.last_log_mtime = None
        self.last_data_mtime = None

    def create_widgets(self):
        # Top controls frame
        top = ttk.Frame(self)
        top.pack(side="top", fill="x", padx=6, pady=6)

        ttk.Label(top, text="Log file:").pack(side="left")
        self.log_path_var = tk.StringVar(value=DEFAULT_LOG_FILE)
        ttk.Entry(top, textvariable=self.log_path_var, width=40).pack(side="left", padx=4)
        ttk.Button(top, text="Open...", command=self.select_log_file).pack(side="left", padx=2)
        ttk.Button(top, text="Load Logs", command=self.load_logs).pack(side="left", padx=4)

        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=6)

        ttk.Label(top, text="Data file:").pack(side="left")
        self.data_path_var = tk.StringVar(value=DEFAULT_DATA_FILE)
        ttk.Entry(top, textvariable=self.data_path_var, width=30).pack(side="left", padx=4)
        ttk.Button(top, text="Open...", command=self.select_data_file).pack(side="left", padx=2)
        ttk.Button(top, text="Load Data", command=self.load_data).pack(side="left", padx=4)

        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=6)

        self.tail_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Auto-tail (poll)", variable=self.tail_var, command=self.toggle_tail).pack(side="left", padx=4)
        ttk.Label(top, text="Poll interval (s):").pack(side="left", padx=2)
        self.poll_interval = tk.DoubleVar(value=1.0)
        ttk.Entry(top, textvariable=self.poll_interval, width=6).pack(side="left")

        ttk.Button(top, text="Refresh", command=self.manual_refresh).pack(side="right", padx=4)

        # Middle - Paned window: left: log list + filters, right: details
        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.pack(side="top", fill="both", expand=True, padx=6, pady=6)

        leftframe = ttk.Frame(paned)
        rightframe = ttk.Frame(paned, width=420)
        paned.add(leftframe, weight=3)
        paned.add(rightframe, weight=1)

        # Filters
        filt_frame = ttk.Frame(leftframe)
        filt_frame.pack(side="top", fill="x", pady=4)
        ttk.Label(filt_frame, text="Filter:").pack(side="left")
        self.search_var = tk.StringVar()
        ttk.Entry(filt_frame, textvariable=self.search_var, width=40).pack(side="left", padx=6)
        ttk.Button(filt_frame, text="Search", command=self.update_log_view).pack(side="left", padx=4)
        ttk.Button(filt_frame, text="Clear", command=self.clear_search).pack(side="left", padx=4)

        # Level filter checkbuttons
        level_frame = ttk.Frame(leftframe)
        level_frame.pack(side="top", fill="x")
        ttk.Label(level_frame, text="Levels:").pack(side="left")
        self.level_vars = {}
        for lvl in ["FATAL", "CRITICAL", "WARN", "INFO", "DEBUG", "UNKNOWN", "OFF"]:
            v = tk.BooleanVar(value=True)
            chk = ttk.Checkbutton(level_frame, text=lvl, variable=v, command=self.update_log_view)
            chk.pack(side="left", padx=2)
            self.level_vars[lvl] = v

        # Treeview for logs
        columns = ("time", "level", "origin", "domain", "message")
        self.tree = ttk.Treeview(leftframe, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("time", text="Time")
        self.tree.heading("level", text="Level")
        self.tree.heading("origin", text="Origin")
        self.tree.heading("domain", text="Domain")
        self.tree.heading("message", text="Message")
        self.tree.column("time", width=160)
        self.tree.column("level", width=80)
        self.tree.column("origin", width=140)
        self.tree.column("domain", width=120)
        self.tree.column("message", width=420)
        self.tree.pack(side="top", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_select_entry)

        # Bottom controls for logs
        bottom_controls = ttk.Frame(leftframe)
        bottom_controls.pack(side="bottom", fill="x", pady=6)
        ttk.Button(bottom_controls, text="Export Selected", command=self.export_selected).pack(side="left", padx=4)
        ttk.Button(bottom_controls, text="Export All", command=self.export_all).pack(side="left")
        ttk.Button(bottom_controls, text="Open Containing Folder", command=self.open_containing_folder).pack(side="left", padx=6)

        # Right frame - details
        details_label = ttk.Label(rightframe, text="Entry Details / Raw", font=("TkDefaultFont", 10, "bold"))
        details_label.pack(side="top", anchor="w", pady=(4,2))
        self.details_text = tk.Text(rightframe, wrap="none", height=20)
        self.details_text.pack(side="top", fill="both", expand=True)
        # Raw hex view
        ttk.Label(rightframe, text="Raw (hex):").pack(side="top", anchor="w")
        self.hex_text = tk.Text(rightframe, height=8, wrap="none")
        self.hex_text.pack(side="top", fill="x", expand=False)

        # Data tab below logs
        data_frame = ttk.LabelFrame(self, text="Parsed Data Packets")
        data_frame.pack(side="bottom", fill="x", padx=6, pady=6)
        self.data_tree = ttk.Treeview(data_frame, columns=("pos","name","value"), show="headings")
        self.data_tree.heading("pos", text="Pos")
        self.data_tree.heading("name", text="Name")
        self.data_tree.heading("value", text="Value")
        self.data_tree.pack(side="left", fill="x", expand=True)
        self.data_tree.bind("<<TreeviewSelect>>", self.on_select_data)
        data_buttons = ttk.Frame(data_frame)
        data_buttons.pack(side="right", padx=6)
        ttk.Button(data_buttons, text="Export Data", command=self.export_data).pack(side="top", pady=4)
        ttk.Button(data_buttons, text="Clear Data View", command=lambda: self.data_tree.delete(*self.data_tree.get_children())).pack(side="top")

        # status bar
        self.status_var = tk.StringVar(value="Ready")
        status = ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w")
        status.pack(side="bottom", fill="x")

    # -----------------------
    # UI actions
    # -----------------------
    def select_log_file(self):
        p = filedialog.askopenfilename(title="Select log binary", filetypes=[("Binary files","*.bin;*.*")])
        if p:
            self.log_path_var.set(p)
            self.log_file = p

    def select_data_file(self):
        p = filedialog.askopenfilename(title="Select data binary", filetypes=[("Binary files","*.bin;*.*")])
        if p:
            self.data_path_var.set(p)
            self.data_file = p

    def set_status(self, text):
        self.status_var.set(text)

    def load_logs(self):
        path = self.log_path_var.get()
        if not os.path.exists(path):
            messagebox.showerror("File not found", f"Log file not found: {path}")
            return
        try:
            with open(path, "rb") as f:
                raw = f.read()
            self.parsed_logs = parse_logs(raw)
            self.update_log_view()
            self.set_status(f"Loaded {len(self.parsed_logs)} log entries from {os.path.basename(path)}")
            self.log_file = path
            self.last_log_mtime = os.path.getmtime(path)
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Error parsing logs", str(e))

    def load_data(self):
        path = self.data_path_var.get()
        if not os.path.exists(path):
            messagebox.showerror("File not found", f"Data file not found: {path}")
            return
        try:
            with open(path, "rb") as f:
                raw = f.read()
            self.parsed_data = parse_data_packets(raw)
            self.data_tree.delete(*self.data_tree.get_children())
            for ent in self.parsed_data:
                self.data_tree.insert("", "end", values=(ent["pos"], ent["name"], ent["value"]))
            self.set_status(f"Loaded {len(self.parsed_data)} data packets from {os.path.basename(path)}")
            self.data_file = path
            self.last_data_mtime = os.path.getmtime(path)
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Error parsing data", str(e))

    def update_log_view(self):
        # Apply filters and update tree
        search = self.search_var.get().lower().strip()
        selected_levels = {lvl for lvl,v in self.level_vars.items() if v.get()}
        self.tree.delete(*self.tree.get_children())
        for idx, ent in enumerate(self.parsed_logs):
            if ent["level_name"] not in selected_levels:
                continue
            full_text = f'{ent.get("message","")} {ent.get("origin","")} {ent.get("domain_name","")}'
            if search and search not in full_text.lower():
                continue
            self.tree.insert("", "end", iid=str(idx), values=(ent.get("timestamp_str",""), ent.get("level_name",""), ent.get("origin",""), ent.get("domain_name") or "", ent.get("message","")))
        self.set_status(f"Showing {len(self.tree.get_children())} / {len(self.parsed_logs)} entries")

    def clear_search(self):
        self.search_var.set("")
        self.update_log_view()

    def on_select_entry(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        ent = self.parsed_logs[idx]
        self.details_text.delete("1.0", "end")
        details = []
        details.append(f"Position: {ent.get('pos')}")
        details.append(f"Level: {ent.get('level_name')} (0x{ent.get('level_int'):02x})")
        details.append(f"Timestamp: {ent.get('timestamp_str')}  (fmt: {ent.get('timestamp_fmt')})")
        details.append(f"Origin: {ent.get('origin')}")
        details.append(f"Domain: {ent.get('domain_name')} (raw: {ent.get('domain_int')})")
        details.append("Message:")
        details.append(ent.get("message",""))
        details.append("")
        details.append("Raw bytes (decoded where possible):")
        # show hex of entry raw
        raw = ent.get("raw", b"")
        self.details_text.insert("1.0", "\n".join(details))
        self.hex_text.delete("1.0", "end")
        self.hex_text.insert("1.0", binascii.hexlify(raw).decode())

    def on_select_data(self, event):
        sel = self.data_tree.selection()
        if not sel:
            return
        iid = sel[0]
        idx = self.data_tree.index(iid)
        ent = self.parsed_data[idx]
        self.details_text.delete("1.0", "end")
        out = []
        out.append(f"Pos: {ent['pos']}")
        out.append(f"Name: {ent['name']}")
        out.append("Value:")
        out.append(ent['value'])
        out.append("")
        out.append("Raw name (hex): " + binascii.hexlify(ent['name_raw']).decode())
        out.append("Raw value (hex): " + binascii.hexlify(ent['value_raw']).decode())
        self.details_text.insert("1.0", "\n".join(out))
        self.hex_text.delete("1.0", "end")
        self.hex_text.insert("1.0", binascii.hexlify(ent['raw']).decode())

    def export_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "No log rows selected to export.")
            return
        export_path = filedialog.asksaveasfilename(title="Export selected logs", defaultextension=".txt", filetypes=[("Text","*.txt")])
        if not export_path:
            return
        try:
            with open(export_path, "w", encoding="utf-8") as f:
                for item in sel:
                    ent = self.parsed_logs[int(item)]
                    f.write(f"[{ent.get('timestamp_str')}] {ent.get('level_name')} ({ent.get('origin')} | {ent.get('domain_name')}) {ent.get('message')}\n")
            messagebox.showinfo("Export complete", f"Exported {len(sel)} entries to {export_path}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    def export_all(self):
        if not self.parsed_logs:
            messagebox.showinfo("No logs", "No logs loaded.")
            return
        export_path = filedialog.asksaveasfilename(title="Export all logs", defaultextension=".txt", filetypes=[("Text","*.txt")])
        if not export_path:
            return
        try:
            with open(export_path, "w", encoding="utf-8") as f:
                for ent in self.parsed_logs:
                    f.write(f"[{ent.get('timestamp_str')}] {ent.get('level_name')} ({ent.get('origin')} | {ent.get('domain_name')}) {ent.get('message')}\n")
            messagebox.showinfo("Export complete", f"Exported {len(self.parsed_logs)} entries to {export_path}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    def export_data(self):
        if not self.parsed_data:
            messagebox.showinfo("No data", "No data loaded.")
            return
        export_path = filedialog.asksaveasfilename(title="Export data packets", defaultextension=".csv", filetypes=[("CSV","*.csv;*.txt"),("Text","*.txt")])
        if not export_path:
            return
        try:
            with open(export_path, "w", encoding="utf-8") as f:
                f.write("pos,name,value\n")
                for ent in self.parsed_data:
                    # naive CSV quoting
                    name = ent['name'].replace('"', '""')
                    val = ent['value'].replace('"', '""')
                    f.write(f'{ent["pos"]},"{name}","{val}"\n')
            messagebox.showinfo("Export complete", f"Exported {len(self.parsed_data)} packets to {export_path}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    def open_containing_folder(self):
        p = self.log_path_var.get()
        if not os.path.exists(p):
            messagebox.showerror("Not found", f"{p} does not exist")
            return
        # open folder in explorer (Windows)
        try:
            folder = os.path.abspath(os.path.dirname(p))
            os.startfile(folder)
        except Exception as e:
            messagebox.showerror("Open folder failed", str(e))

    def manual_refresh(self):
        # re-load files if they changed, else re-parse last read contents
        try:
            # logs
            p = self.log_path_var.get()
            if os.path.exists(p):
                m = os.path.getmtime(p)
                if self.last_log_mtime is None or m != self.last_log_mtime:
                    # load fresh
                    self.load_logs()
                else:
                    # no change, just reapply filters
                    self.update_log_view()
            # data
            pd = self.data_path_var.get()
            if os.path.exists(pd):
                m = os.path.getmtime(pd)
                if self.last_data_mtime is None or m != self.last_data_mtime:
                    self.load_data()
        except Exception as e:
            traceback.print_exc()
            self.set_status("Refresh failed: " + str(e))

    def toggle_tail(self):
        run = self.tail_var.get()
        if run:
            self.tail_running = True
            self.set_status("Tail started")
            self.tail_worker()
        else:
            self.tail_running = False
            self.set_status("Tail stopped")

    def tail_worker(self):
        if not self.tail_running:
            return
        try:
            # check log file
            p = self.log_path_var.get()
            if os.path.exists(p):
                m = os.path.getmtime(p)
                if self.last_log_mtime is None or m != self.last_log_mtime:
                    self.load_logs()
            pd = self.data_path_var.get()
            if os.path.exists(pd):
                m2 = os.path.getmtime(pd)
                if self.last_data_mtime is None or m2 != self.last_data_mtime:
                    self.load_data()
        except Exception:
            pass
        interval = max(0.1, float(self.poll_interval.get()))
        # schedule next check
        self.after(int(interval * 1000), self.tail_worker)

# -----------------------
# Entry point
# -----------------------

if __name__ == "__main__":
    app = PicoLogViewer()
    # try to auto-load default files if present
    if os.path.exists(DEFAULT_LOG_FILE):
        try:
            app.load_logs()
        except Exception:
            pass
    if os.path.exists(DEFAULT_DATA_FILE):
        try:
            app.load_data()
        except Exception:
            pass
    app.mainloop()
