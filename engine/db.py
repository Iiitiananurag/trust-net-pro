import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "trustnet.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  malicious INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS accounts (
  id TEXT PRIMARY KEY,
  handle TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trust_edges (
  src TEXT NOT NULL REFERENCES projects(id),
  dst TEXT NOT NULL REFERENCES projects(id),
  weight REAL NOT NULL CHECK (weight >= 0 AND weight <= 1),
  PRIMARY KEY (src, dst)
);
CREATE TABLE IF NOT EXISTS vouches (
  project_id TEXT NOT NULL REFERENCES projects(id),
  account_id TEXT NOT NULL REFERENCES accounts(id),
  reason TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (project_id, account_id)
);
CREATE TABLE IF NOT EXISTS denounces (
  project_id TEXT NOT NULL REFERENCES projects(id),
  account_id TEXT NOT NULL REFERENCES accounts(id),
  reason TEXT,
  created_at TEXT NOT NULL,
  expires_at TEXT,
  PRIMARY KEY (project_id, account_id)
);
CREATE TABLE IF NOT EXISTS denounce_appeals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL REFERENCES projects(id),
  account_id TEXT NOT NULL REFERENCES accounts(id),
  reason TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS account_vouches (
  voucher_id TEXT NOT NULL REFERENCES accounts(id),
  account_id TEXT NOT NULL REFERENCES accounts(id),
  created_at TEXT NOT NULL,
  PRIMARY KEY (voucher_id, account_id)
);
CREATE TABLE IF NOT EXISTS pull_requests (
  id TEXT PRIMARY KEY,
  repo_id TEXT NOT NULL REFERENCES projects(id),
  author_id TEXT NOT NULL REFERENCES accounts(id),
  title TEXT NOT NULL,
  body TEXT NOT NULL DEFAULT '',
  diff TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pr_author ON pull_requests(author_id);
CREATE INDEX IF NOT EXISTS idx_pr_repo ON pull_requests(repo_id);
CREATE INDEX IF NOT EXISTS idx_appeals_pair ON denounce_appeals(project_id, account_id);
"""


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate_schema(conn):
    """Safely migrate existing SQLite databases created with older schemas."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(denounces)").fetchall()}
    if cols and "expires_at" not in cols:
        conn.execute("ALTER TABLE denounces ADD COLUMN expires_at TEXT")


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    _migrate_schema(conn)
    conn.commit()
    tables = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    conn.close()
    return tables


def ensure_project(conn, project_id, name=None):
    """Ensure a project exists before inserting edges, signals, or PRs."""
    label = name or project_id.replace("-", " ").title()
    conn.execute(
        "INSERT OR IGNORE INTO projects (id, name, malicious) VALUES (?, ?, 0)",
        (project_id, label),
    )


def ensure_account(conn, account_id, handle=None, created_at=None):
    """Ensure an account exists before inserting signals or PRs."""
    ts = created_at or datetime.now().isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO accounts (id, handle, created_at) VALUES (?, ?, ?)",
        (account_id, handle or account_id, ts),
    )


def upsert_pr_and_author(
    conn,
    pr_id,
    repo_id,
    author_id,
    title,
    body="",
    diff="",
    created_at=None,
    author_created_at=None,
):
    """Persist an incoming PR/issue and ensure referenced repo and author exist."""
    now_iso = created_at or datetime.now().isoformat()
    ensure_project(conn, repo_id)
    ensure_account(conn, author_id, handle=author_id, created_at=author_created_at or now_iso)
    conn.execute(
        """
        INSERT INTO pull_requests (id, repo_id, author_id, title, body, diff, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            body=excluded.body,
            diff=excluded.diff
        """,
        (pr_id, repo_id, author_id, title, body or "", diff or "", now_iso),
    )
    conn.commit()


if __name__ == "__main__":
    print("DB:", DB_PATH)
    print("tables:", ", ".join(init_db()))
