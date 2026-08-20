"""Harness storage (design §30, §35 PR6).

Boring storage first: SQLite for metadata, JSONL for the append-only event stream,
a content-addressed blob store on the filesystem. The source of truth for raw
execution is the append-only events + blobs; the SQLite tables are a rebuildable
index over them (§30). No vector DB, no server dependency.

Layout under `root/`::

    harness.db                 SQLite metadata (captures, episodes, event_index, packages)
    captures/<capture_id>.jsonl append-only canonical event spool
    blobs/sha256/<digest>      content-addressed blobs
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from jdsl.trace.blobs import BlobStore
from jdsl.trace.events import EventKind, TraceEvent
from jdsl.trace.jsonl import JsonlTraceSink, iter_events
from jdsl.trace.replay import Episode, segment_episodes
from jdsl.trace.sink import _Chainer

_SCHEMA = """
CREATE TABLE IF NOT EXISTS captures (
    capture_id   TEXT PRIMARY KEY,
    host         TEXT,
    adapter      TEXT,
    status       TEXT,
    created_at   TEXT,
    finished_at  TEXT,
    note         TEXT
);
CREATE TABLE IF NOT EXISTS episodes (
    episode_id   TEXT PRIMARY KEY,
    capture_id   TEXT,
    outcome      TEXT,
    reward       REAL,
    event_count  INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS event_index (
    capture_id   TEXT,
    episode_id   TEXT,
    sequence     INTEGER,
    kind         TEXT,
    event_hash   TEXT
);
CREATE TABLE IF NOT EXISTS packages (
    name         TEXT,
    version      TEXT,
    digest       TEXT,
    status       TEXT,
    created_at   TEXT,
    path         TEXT,
    PRIMARY KEY (name, version)
);
CREATE INDEX IF NOT EXISTS ix_events_capture ON event_index(capture_id);
CREATE INDEX IF NOT EXISTS ix_episodes_capture ON episodes(capture_id);
"""


class HarnessStore:
    """Metadata + event spool + blob store for one harness instance."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "captures").mkdir(exist_ok=True)
        self.blobs = BlobStore(self.root / "blobs")
        self._db_path = self.root / "harness.db"
        self._local = threading.local()
        self._chainers: dict[str, _Chainer] = {}
        self._lock = threading.Lock()
        self._init_db()

    # -- db plumbing ----------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
        return conn

    def _init_db(self) -> None:
        conn = self._conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    # -- captures -------------------------------------------------------------

    def spool_path(self, capture_id: str) -> Path:
        return self.root / "captures" / f"{capture_id}.jsonl"

    def start_capture(self, capture_id: str, *, host: str = "jdsl", adapter: str = "runtime",
                      note: str = "") -> None:
        from jdsl.trace.events import _now_iso
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO captures(capture_id, host, adapter, status, created_at, note) "
            "VALUES(?,?,?,?,?,?)",
            (capture_id, host, adapter, "recording", _now_iso(), note))
        conn.commit()

    def finish_capture(self, capture_id: str) -> None:
        from jdsl.trace.events import _now_iso
        conn = self._conn()
        conn.execute("UPDATE captures SET status='finished', finished_at=? WHERE capture_id=?",
                     (_now_iso(), capture_id))
        conn.commit()

    def sink(self, capture_id: str) -> JsonlTraceSink:
        """A trace sink that appends to this capture's spool and indexes each event.
        Reuses one hash-chainer per capture so sequences/hashes stay consistent."""
        with self._lock:
            chain = self._chainers.setdefault(capture_id, _Chainer())
        return _IndexingSink(self, capture_id, JsonlTraceSink(self.spool_path(capture_id), chain=chain))

    def ingest(self, event: TraceEvent) -> TraceEvent:
        """Record a single already-formed event (used by adapters/ingest server)."""
        return self.sink(event.capture_id).emit(event)

    def _index(self, event: TraceEvent) -> None:
        from jdsl.trace.events import _now_iso
        conn = self._conn()
        # ensure a capture row exists even for events that arrived via ingest
        # (adapters/hooks) rather than an explicit start_capture (§7.2).
        conn.execute(
            "INSERT OR IGNORE INTO captures(capture_id, host, adapter, status, created_at) "
            "VALUES(?,?,?,?,?)",
            (event.capture_id, event.source.host, event.source.adapter, "recording", _now_iso()))
        conn.execute(
            "INSERT INTO event_index(capture_id, episode_id, sequence, kind, event_hash) VALUES(?,?,?,?,?)",
            (event.capture_id, event.episode_id, event.sequence, event.kind, event.event_hash))
        conn.execute(
            "INSERT OR IGNORE INTO episodes(episode_id, capture_id) VALUES(?,?)",
            (event.episode_id, event.capture_id))
        conn.execute("UPDATE episodes SET event_count = event_count + 1 WHERE episode_id=?",
                     (event.episode_id,))
        if event.kind in (EventKind.ENVIRONMENT_REWARD, EventKind.ENVIRONMENT_VERDICT):
            reward = event.payload.get("reward")
            conn.execute("UPDATE episodes SET outcome=?, reward=? WHERE episode_id=?",
                         (event.payload.get("verdict") or str(event.payload.get("reward")),
                          float(reward) if isinstance(reward, (int, float)) else None,
                          event.episode_id))
        conn.commit()

    # -- reads ----------------------------------------------------------------

    def list_captures(self) -> list[dict[str, Any]]:
        rows = self._conn().execute(
            "SELECT c.*, (SELECT COUNT(*) FROM episodes e WHERE e.capture_id=c.capture_id) AS episodes "
            "FROM captures c ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]

    def capture_events(self, capture_id: str) -> list[TraceEvent]:
        path = self.spool_path(capture_id)
        return list(iter_events(path)) if path.exists() else []

    def capture_episodes(self, capture_id: str) -> list[Episode]:
        return segment_episodes(self.capture_events(capture_id))

    def iter_capture(self, capture_id: str) -> Iterator[TraceEvent]:
        path = self.spool_path(capture_id)
        if path.exists():
            yield from iter_events(path)

    def record_package(self, name: str, version: str, digest: str, *, status: str = "built",
                       path: str = "") -> None:
        from jdsl.trace.events import _now_iso
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO packages(name, version, digest, status, created_at, path) "
            "VALUES(?,?,?,?,?,?)", (name, version, digest, status, _now_iso(), path))
        conn.commit()

    def list_packages(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._conn().execute(
            "SELECT * FROM packages ORDER BY created_at").fetchall()]


class _IndexingSink:
    """Wraps the JSONL sink to also index each event in SQLite."""

    def __init__(self, store: HarnessStore, capture_id: str, inner: JsonlTraceSink) -> None:
        self.store = store
        self.capture_id = capture_id
        self.inner = inner

    def emit(self, event: TraceEvent) -> TraceEvent:
        event = self.inner.emit(event)
        self.store._index(event)
        return event


__all__ = ["HarnessStore"]
