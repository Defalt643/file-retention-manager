import json
import sqlite3
from pathlib import Path

DEFAULTS = {
    "target_paths": "[]",
    "retention_months": "4",
    "interval_hours": "24",
    "dry_run": "1",
    "worker_enabled": "0",
}

def _connect(db_path):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path):
    with _connect(db_path) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS worker_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            heartbeat TEXT, last_run TEXT, last_result TEXT)""")
        conn.execute("INSERT OR IGNORE INTO worker_state(id) VALUES (1)")
        for key, value in DEFAULTS.items():
            conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)", (key, value))

def get_settings(db_path):
    with _connect(db_path) as conn:
        values = dict(DEFAULTS)
        values.update({r["key"]: r["value"] for r in conn.execute("SELECT key,value FROM settings")})
    values["target_paths"] = json.loads(values["target_paths"])
    values["retention_months"] = int(values["retention_months"])
    values["interval_hours"] = int(values["interval_hours"])
    values["dry_run"] = values["dry_run"] == "1"
    values["worker_enabled"] = values["worker_enabled"] == "1"
    return values

def save_settings(db_path, settings):
    serial = {
        "target_paths": json.dumps(settings["target_paths"]),
        "retention_months": str(settings["retention_months"]),
        "interval_hours": str(settings["interval_hours"]),
        "dry_run": "1" if settings["dry_run"] else "0",
        "worker_enabled": "1" if settings["worker_enabled"] else "0",
    }
    with _connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            serial.items()
        )

def update_worker_state(db_path, heartbeat=None, last_run=None, last_result=None):
    with _connect(db_path) as conn:
        conn.execute("""UPDATE worker_state SET
            heartbeat=COALESCE(?,heartbeat),
            last_run=COALESCE(?,last_run),
            last_result=COALESCE(?,last_result) WHERE id=1""",
            (heartbeat, last_run, last_result))

def get_worker_state(db_path):
    with _connect(db_path) as conn:
        row = conn.execute("SELECT heartbeat,last_run,last_result FROM worker_state WHERE id=1").fetchone()
    return dict(row) if row else {}
