"""
LogIndexer — writes structured log records into two sinks:
  1. Elasticsearch  — full-text search (used when an ES cluster is reachable)
  2. SQLite         — metadata store and fallback search backend

If Elasticsearch is not reachable the indexer falls back gracefully to
SQLite-only mode and logs a clear warning.  No integration is faked.
"""

import sqlite3
import time
from typing import List, Dict

# Elasticsearch is optional; if the package or cluster is unavailable we
# continue in SQLite-only mode.
try:
    from elasticsearch import Elasticsearch, helpers as es_helpers
    _ES_PACKAGE_AVAILABLE = True
except ImportError:
    _ES_PACKAGE_AVAILABLE = False

_INDEX_NAME = "windows_app_logs"


class LogIndexer:
    """
    Dual-sink log indexer.

    Priority:
      - Elasticsearch (if the package is installed and the cluster responds)
      - SQLite (always available; used as both primary store and fallback)
    """

    def __init__(
        self,
        es_host: str = "http://localhost:9200",
        db_path: str = "data/log_metadata.db",
    ):
        self.db_path = db_path
        self._init_sqlite()

        self.es = None
        if _ES_PACKAGE_AVAILABLE:
            try:
                client = Elasticsearch(es_host, request_timeout=2)
                if client.ping():
                    self.es = client
                    self._init_es_index()
                else:
                    print("[LogIndexer] Elasticsearch unreachable — using SQLite only.")
            except Exception as exc:
                print(f"[LogIndexer] ES connection failed ({exc}) — using SQLite only.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index_records(self, records: List[Dict]) -> int:
        """
        Write records to SQLite and, if available, to Elasticsearch.
        Returns the number of records successfully written.
        """
        ingested_at = time.strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(self.db_path)
        for rec in records:
            conn.execute(
                """INSERT INTO log_metadata
                   (source_file, module, level, message, timestamp, ingested_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    rec.get("source_file"),
                    rec.get("module"),
                    rec.get("level"),
                    rec.get("message"),
                    str(rec.get("timestamp")),
                    ingested_at,
                ),
            )
        conn.commit()
        conn.close()

        if self.es and records:
            actions = [{"_index": _INDEX_NAME, "_source": r} for r in records]
            es_helpers.bulk(self.es, actions)

        return len(records)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _init_sqlite(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS log_metadata (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT,
                module      TEXT,
                level       TEXT,
                message     TEXT,
                timestamp   TEXT,
                ingested_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _init_es_index(self):
        if not self.es.indices.exists(index=_INDEX_NAME):
            self.es.indices.create(
                index=_INDEX_NAME,
                body={
                    "mappings": {
                        "properties": {
                            "message":   {"type": "text"},
                            "timestamp": {"type": "date"},
                            "level":     {"type": "keyword"},
                            "module":    {"type": "keyword"},
                        }
                    }
                },
            )
