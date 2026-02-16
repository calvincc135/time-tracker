# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
python tracker.py
```

The app is also launched via `Play Time Tracker.bat` (uses `pythonw` for no console window). No dependencies beyond Python 3 stdlib.

## Architecture

Single-file tkinter app (`tracker.py`) that tracks children's screen time with configurable daily limits.

**Key components in `tracker.py`:**
- **NTP time sync** (top of file): Queries `pool.ntp.org` to get accurate time. Computes `_time_offset` (global timedelta) applied via `now()` helper. NTP returns UTC; offset is calculated against `datetime.utcnow()`.
- **`PlayTimeTracker` class**: The tkinter GUI. Manages start/stop sessions, timer ticking, daily progress bar, and session history display.
- **CSV persistence**: Sessions logged to `playtime_log.csv` (date, start_time, end_time, duration_minutes, game). The `ensure_csv()` function auto-creates or fixes headers on startup.
- **Config**: `config.json` defines `weekday_limit_minutes`, `weekend_limit_minutes`, `holidays` (dates that use weekend limits), and `games` list.

**Time flow:** `_time_offset` is re-synced from NTP each time the user presses Start. All time reads go through `now()` which adds the offset to `datetime.now()`.

## Data Files

- `config.json` — user-editable settings (limits, holidays, game list)
- `playtime_log.csv` — append-only session log (do not change header format)
