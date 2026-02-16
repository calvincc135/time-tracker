import tkinter as tk
from tkinter import ttk
import csv
import json
import os
import socket
import struct
import time
from datetime import datetime, date, timedelta

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(APP_DIR, "playtime_log.csv")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ── NTP time sync ────────────────────────────────────────────────

def _query_ntp(server="pool.ntp.org", timeout=3):
    """Query an NTP server and return a datetime."""
    NTP_EPOCH = datetime(1900, 1, 1)
    msg = b"\x1b" + 47 * b"\0"
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(msg, (server, 123))
        data, _ = sock.recvfrom(1024)
    finally:
        sock.close()
    t = struct.unpack("!12I", data)[10]
    # t is the transmit timestamp (index 10)
    return NTP_EPOCH + timedelta(seconds=t)


def sync_time_offset():
    """Return the offset (NTP time - local time) as a timedelta."""
    try:
        ntp_time = _query_ntp()
        return ntp_time - datetime.utcnow()
    except Exception:
        return timedelta(0)


_time_offset = sync_time_offset()


def now():
    """Return the current time adjusted by the NTP offset."""
    return datetime.now() + _time_offset


def load_config():
    defaults = {"weekday_limit_minutes": 60, "weekend_limit_minutes": 180, "holidays": [], "games": ["Minecraft", "VR", "Roblox", "Other"]}
    try:
        with open(CONFIG_PATH, "r") as f:
            cfg = json.load(f)
        defaults.update(cfg)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return defaults


def is_holiday(cfg):
    """Return True if today's date is in the holidays list."""
    return now().date().strftime("%Y-%m-%d") in cfg.get("holidays", [])


def get_daily_limit(cfg):
    """Return the limit in minutes based on today being a weekday, weekend, or holiday."""
    if is_holiday(cfg):
        return cfg["weekend_limit_minutes"]
    day = now().date().weekday()  # 0=Mon … 6=Sun
    if day < 5:
        return cfg["weekday_limit_minutes"]
    return cfg["weekend_limit_minutes"]


EXPECTED_HEADER = ["date", "start_time", "end_time", "duration_minutes", "game"]


def ensure_csv():
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(EXPECTED_HEADER)
    else:
        with open(CSV_PATH, "r", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
        if header != EXPECTED_HEADER:
            with open(CSV_PATH, "r", newline="") as f:
                lines = f.readlines()
            with open(CSV_PATH, "w", newline="") as f:
                f.write(",".join(EXPECTED_HEADER) + "\n")
                f.writelines(lines[1:] if lines else [])


def append_session(start_dt, end_dt, game=""):
    duration = (end_dt - start_dt).total_seconds() / 60.0
    with open(CSV_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            start_dt.strftime("%Y-%m-%d"),
            start_dt.strftime("%I:%M %p"),
            end_dt.strftime("%I:%M %p"),
            f"{duration:.1f}",
            game,
        ])
    return duration


def read_sessions():
    """Return list of dicts from the CSV."""
    sessions = []
    try:
        with open(CSV_PATH, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sessions.append(row)
    except FileNotFoundError:
        pass
    return sessions


def today_total_minutes(sessions):
    today_str = now().date().strftime("%Y-%m-%d")
    total = 0.0
    for s in sessions:
        if s.get("date") == today_str:
            try:
                total += float(s["duration_minutes"])
            except (ValueError, KeyError):
                pass
    return total


class PlayTimeTracker:
    def __init__(self, root):
        self.root = root
        self.root.title("Calvin's Play Time Tracker")
        self.root.resizable(False, False)

        self.config = load_config()
        ensure_csv()

        self.running = False
        self.start_time = None
        self.elapsed = 0  # seconds since current session started

        self._build_ui()
        self._refresh_history()
        self._update_daily_bar()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self):
        self.root.configure(bg="#f0f0f0")

        # Title
        title = tk.Label(
            self.root, text="Calvin's Play Time Tracker",
            font=("Segoe UI", 16, "bold"), bg="#f0f0f0", pady=8,
        )
        title.pack(fill="x")

        ttk.Separator(self.root).pack(fill="x")

        # Timer frame
        timer_frame = tk.Frame(self.root, bg="#f0f0f0", pady=16)
        timer_frame.pack(fill="x")

        self.timer_label = tk.Label(
            timer_frame, text="00:00:00",
            font=("Consolas", 40, "bold"), bg="#f0f0f0", fg="#333",
        )
        self.timer_label.pack()

        # Game selection dropdown
        game_frame = tk.Frame(self.root, bg="#f0f0f0")
        game_frame.pack(pady=(0, 4))

        tk.Label(
            game_frame, text="Playing:", font=("Segoe UI", 11),
            bg="#f0f0f0",
        ).pack(side="left", padx=(0, 6))

        self.game_var = tk.StringVar(value=self.config["games"][0])
        self.game_dropdown = ttk.Combobox(
            game_frame, textvariable=self.game_var,
            values=self.config["games"], state="readonly",
            font=("Segoe UI", 11), width=14,
        )
        self.game_dropdown.pack(side="left")

        # Start / Stop button
        btn_frame = tk.Frame(self.root, bg="#f0f0f0", pady=8)
        btn_frame.pack()

        self.toggle_btn = tk.Button(
            btn_frame, text="\u25b6  START PLAYING",
            font=("Segoe UI", 14, "bold"), fg="white", bg="#2ecc71",
            activebackground="#27ae60", activeforeground="white",
            width=22, height=2, relief="flat", cursor="hand2",
            command=self._toggle,
        )
        self.toggle_btn.pack()

        ttk.Separator(self.root).pack(fill="x", pady=(12, 0))

        # Daily progress section
        progress_frame = tk.Frame(self.root, bg="#f0f0f0", padx=20, pady=10)
        progress_frame.pack(fill="x")

        self.daily_label = tk.Label(
            progress_frame, text="Today: 0 / 60 min",
            font=("Segoe UI", 11), bg="#f0f0f0", anchor="w",
        )
        self.daily_label.pack(fill="x")

        bar_row = tk.Frame(progress_frame, bg="#f0f0f0")
        bar_row.pack(fill="x", pady=(4, 0))

        self.progress_bar = ttk.Progressbar(bar_row, length=300, maximum=100)
        self.progress_bar.pack(side="left", fill="x", expand=True)

        self.pct_label = tk.Label(
            bar_row, text="0%", font=("Segoe UI", 10), bg="#f0f0f0", width=6,
        )
        self.pct_label.pack(side="left")

        ttk.Separator(self.root).pack(fill="x", pady=(10, 0))

        # History section
        hist_frame = tk.Frame(self.root, bg="#f0f0f0", padx=20, pady=10)
        hist_frame.pack(fill="both", expand=True)

        tk.Label(
            hist_frame, text="Recent Sessions:",
            font=("Segoe UI", 11, "bold"), bg="#f0f0f0", anchor="w",
        ).pack(fill="x")

        self.history_text = tk.Text(
            hist_frame, height=6, width=52, font=("Consolas", 10),
            bg="#fafafa", relief="flat", state="disabled", wrap="none",
        )
        self.history_text.pack(fill="both", expand=True, pady=(4, 0))

    # ── Timer logic ──────────────────────────────────────────────────

    def _toggle(self):
        if self.running:
            self._stop_session()
        else:
            self._start_session()

    def _start_session(self):
        global _time_offset
        _time_offset = sync_time_offset()
        self.running = True
        self.start_time = now()
        self.elapsed = 0
        self.current_game = self.game_var.get()
        self.game_dropdown.config(state="disabled")

        self.toggle_btn.config(
            text="\u25a0  STOP PLAYING", bg="#e74c3c",
            activebackground="#c0392b",
        )
        self._tick()

    def _stop_session(self):
        if not self.running:
            return
        self.running = False
        end_time = now()
        append_session(self.start_time, end_time, self.current_game)
        self.start_time = None
        self.game_dropdown.config(state="readonly")

        self.toggle_btn.config(
            text="\u25b6  START PLAYING", bg="#2ecc71",
            activebackground="#27ae60",
        )
        self._refresh_history()
        self._update_daily_bar()

    def _tick(self):
        if not self.running:
            return
        self.elapsed = (now() - self.start_time).total_seconds()
        h, rem = divmod(int(self.elapsed), 3600)
        m, s = divmod(rem, 60)
        self.timer_label.config(text=f"{h:02d}:{m:02d}:{s:02d}")
        self._update_daily_bar()
        self.root.after(500, self._tick)

    # ── Daily progress ───────────────────────────────────────────────

    def _update_daily_bar(self):
        sessions = read_sessions()
        logged = today_total_minutes(sessions)
        # Add current running session time
        if self.running:
            logged += self.elapsed / 60.0

        limit = get_daily_limit(self.config)
        pct = min(logged / limit * 100, 100) if limit > 0 else 0

        day_name = WEEKDAY_NAMES[now().date().weekday()]
        if is_holiday(self.config):
            kind = "Holiday"
        elif now().date().weekday() >= 5:
            kind = "Weekend"
        else:
            kind = "Weekday"
        self.daily_label.config(
            text=f"Today ({day_name}): {logged:.0f} / {limit} min  [{kind}]"
        )

        self.progress_bar["value"] = pct
        self.pct_label.config(text=f"{pct:.0f}%")

        # Color the bar: green → yellow → red
        style = ttk.Style()
        if pct >= 100:
            style.configure("TProgressbar", background="#e74c3c")
        elif pct >= 80:
            style.configure("TProgressbar", background="#f39c12")
        else:
            style.configure("TProgressbar", background="#2ecc71")

    # ── History table ────────────────────────────────────────────────

    def _refresh_history(self):
        sessions = read_sessions()
        # Show most recent 20, newest first
        recent = sessions[-20:][::-1]

        self.history_text.config(state="normal")
        self.history_text.delete("1.0", "end")
        for s in recent:
            d = s.get("date", "")
            # Shorten date to m/d
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
                short_date = f"{dt.month}/{dt.day}"
            except ValueError:
                short_date = d
            start = s.get("start_time", "")
            end = s.get("end_time", "")
            dur = s.get("duration_minutes", "0")
            try:
                dur_display = f"{float(dur):.0f}m"
            except ValueError:
                dur_display = dur
            game = s.get("game", "")
            game_display = f"  [{game}]" if game else ""
            self.history_text.insert("end", f"  {short_date}   {start} - {end}   {dur_display}{game_display}\n")
        self.history_text.config(state="disabled")

    # ── Window close ─────────────────────────────────────────────────

    def _on_close(self):
        if self.running:
            self._stop_session()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = PlayTimeTracker(root)
    root.mainloop()
