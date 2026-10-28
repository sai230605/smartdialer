"""Small SQLite persistence layer. Transactions serialize competing reservations."""
import sqlite3
from contextlib import contextmanager, closing
from pathlib import Path

SCHEMA = '''
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS agents (
 id TEXT PRIMARY KEY, state TEXT NOT NULL, current_call_id TEXT
);
CREATE TABLE IF NOT EXISTS calls (
 id TEXT PRIMARY KEY, borrower_id TEXT NOT NULL, state TEXT NOT NULL,
 agent_id TEXT, provider_call_id TEXT, version INTEGER NOT NULL DEFAULT 0,
 failure_reason TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(agent_id) REFERENCES agents(id)
);
CREATE INDEX IF NOT EXISTS idx_calls_state ON calls(state);
CREATE INDEX IF NOT EXISTS idx_agents_state ON agents(state);
CREATE TABLE IF NOT EXISTS processed_events (
 event_id TEXT PRIMARY KEY, call_id TEXT NOT NULL, event_type TEXT NOT NULL,
 received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
'''

class Database:
    def __init__(self, path='smartdialer.db'):
        self.path = str(path)
        if self.path != ':memory:':
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # sqlite3.Connection's context manager commits/rolls back but does NOT close it.
        # Explicitly close initialization connections, especially on Windows where an
        # open SQLite handle prevents TemporaryDirectory from deleting sim.db.
        with closing(self.connect()) as conn:
            conn.executescript(SCHEMA)

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        conn.execute('PRAGMA busy_timeout = 10000')
        return conn

    @contextmanager
    def transaction(self):
        conn = self.connect()
        try:
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
