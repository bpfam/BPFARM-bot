# backup_utils.py
import os
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_FILE = os.environ.get("DB_FILE", "./data/users.db")
BACKUP_DIR = os.environ.get("BACKUP_DIR", "./data/backups")
ROTATE_KEEP = int(os.environ.get("BACKUP_KEEP", "7"))

def ensure_dirs():
    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)

def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")

def sqlite_safe_copy(src: str, dst: str):
    src_conn = sqlite3.connect(src)
    dst_conn = sqlite3.connect(dst)
    with dst_conn:
        src_conn.backup(dst_conn)
    src_conn.close()
    dst_conn.close()

def make_db_backup() -> Path:
    ensure_dirs()
    ts = timestamp()
    raw_path = Path(BACKUP_DIR) / f"users-{ts}.db"
    zip_path = Path(BACKUP_DIR) / f"users-{ts}.zip"
    sqlite_safe_copy(DB_FILE, str(raw_path))
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(raw_path, arcname=raw_path.name)
    raw_path.unlink(missing_ok=True)
    rotate_backups()
    return zip_path

def rotate_backups(keep: Optional[int] = None):
    keep = keep or ROTATE_KEEP
    files = sorted(Path(BACKUP_DIR).glob("users-*.zip"), reverse=True)
    for f in files[keep:]:
        f.unlink(missing_ok=True)

def export_users_csv(csv_path: Optional[Path] = None) -> Path:
    ensure_dirs()
    csv_path = csv_path or Path(BACKUP_DIR) / f"users-{timestamp()}.csv"
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if not cur.fetchone():
        conn.close()
        raise RuntimeError("Tabella 'users' non trovata nel database.")
    cur.execute("PRAGMA table_info(users)")
    cols = [row[1] for row in cur.fetchall()]
    cur.execute("SELECT * FROM users ORDER BY ROWID ASC")
    rows = cur.fetchall()
    conn.close()
    import csv
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    return csv_path