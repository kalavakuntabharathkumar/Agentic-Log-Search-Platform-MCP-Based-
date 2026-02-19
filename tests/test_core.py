"""
Test suite for LogIngestor, LogIndexer, and LogSearchAgent.

Run with:
    pytest tests/ -v --cov=core --cov-report=term-missing

Five test cases are included, covering:
  1. LogIngestor parses a valid log file correctly.
  2. LogIngestor handles a missing file gracefully.
  3. LogIndexer writes records to SQLite.
  4. LogSearchAgent returns matching results.
  5. LogSearchAgent returns an empty list for an unmatched query.
"""

import sqlite3

import pandas as pd
import pytest

from core.log_ingestor     import LogIngestor
from core.log_indexer      import LogIndexer
from core.log_search_agent import LogSearchAgent


# ── Shared sample data ───────────────────────────────────────────────────────

SAMPLE_LOG = """\
2026-02-14 08:00:01 INFO WindowsUpdateClient Module initialized successfully
2026-02-14 08:00:02 WARNING WindowsUpdateClient Disk space low: only 2 GB remaining
2026-02-14 08:00:03 ERROR WindowsUpdateClient Failed to connect to update server
2026-02-14 08:00:04 DEBUG WindowsUpdateClient Retry attempt 1 of 3
2026-02-14 08:00:05 INFO WindowsUpdateClient Connection re-established successfully
"""


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_data_dir(tmp_path):
    """Create a temporary data directory with one sample log file."""
    log_file = tmp_path / "sample_app1.log"
    log_file.write_text(SAMPLE_LOG, encoding="utf-8")
    return tmp_path


@pytest.fixture
def tmp_db(tmp_path):
    """Return a path to a fresh temporary SQLite database."""
    return str(tmp_path / "test_metadata.db")


# ── Test 1: LogIngestor parses a valid log file ───────────────────────────────

def test_ingestor_parses_file(tmp_data_dir):
    """LogIngestor.parse_file should return 5 rows with correct columns."""
    ingestor = LogIngestor(data_dir=str(tmp_data_dir))
    df = ingestor.parse_file("sample_app1.log")

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 5
    required_cols = {"timestamp", "level", "module", "message", "source_file"}
    assert required_cols.issubset(set(df.columns))

    # Spot-check first row
    assert df["level"].iloc[0] == "INFO"
    assert df["module"].iloc[0] == "WindowsUpdateClient"
    assert "initialized" in df["message"].iloc[0]


# ── Test 2: LogIngestor handles a missing file gracefully ────────────────────

def test_ingestor_missing_file(tmp_data_dir):
    """parse_file should return an empty DataFrame for a non-existent file."""
    ingestor = LogIngestor(data_dir=str(tmp_data_dir))
    df = ingestor.parse_file("does_not_exist.log")

    assert isinstance(df, pd.DataFrame)
    assert df.empty


# ── Test 3: LogIndexer writes records to SQLite ───────────────────────────────

def test_indexer_writes_to_sqlite(tmp_data_dir, tmp_db):
    """index_records should persist all records in the SQLite metadata table."""
    ingestor = LogIngestor(data_dir=str(tmp_data_dir))
    df       = ingestor.parse_file("sample_app1.log")
    records  = ingestor.to_records(df)

    indexer = LogIndexer(es_host="http://localhost:9200", db_path=tmp_db)
    count   = indexer.index_records(records)

    assert count == 5

    conn = sqlite3.connect(tmp_db)
    row  = conn.execute("SELECT COUNT(*) FROM log_metadata").fetchone()
    conn.close()
    assert row[0] == 5


# ── Test 4: LogSearchAgent returns matching results ───────────────────────────

def test_search_agent_finds_results(tmp_data_dir, tmp_db):
    """search('error') should return at least one result from indexed records."""
    ingestor = LogIngestor(data_dir=str(tmp_data_dir))
    records  = ingestor.to_records(ingestor.parse_file("sample_app1.log"))

    LogIndexer(es_host="http://localhost:9200", db_path=tmp_db).index_records(records)

    agent  = LogSearchAgent(es_host="http://localhost:9200", db_path=tmp_db)
    result = agent.search("error")

    assert result["count"] >= 1
    # At least one result should relate to an ERROR-level entry or the word "error"
    found = any(
        "error" in r.get("message", "").lower() or r.get("level", "").upper() == "ERROR"
        for r in result["results"]
    )
    assert found


# ── Test 5: LogSearchAgent returns empty list for an unmatched query ──────────

def test_search_agent_empty_results(tmp_data_dir, tmp_db):
    """search on a nonsense query should return count=0 and an empty list."""
    ingestor = LogIngestor(data_dir=str(tmp_data_dir))
    records  = ingestor.to_records(ingestor.parse_file("sample_app1.log"))

    LogIndexer(es_host="http://localhost:9200", db_path=tmp_db).index_records(records)

    agent  = LogSearchAgent(es_host="http://localhost:9200", db_path=tmp_db)
    result = agent.search("xyzzy_no_match_term_99999")

    assert result["count"] == 0
    assert result["results"] == []
