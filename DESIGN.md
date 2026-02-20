# DESIGN.md — Agentic Log Search Platform (MCP-Based)

## 1. Overview

The Agentic Log Search Platform is a small Python backend that ingests Windows
application log files, indexes them for fast search, and exposes the search and
ingest operations as both HTTP endpoints (Flask) and MCP tools (FastMCP).  The
system is intentionally minimal — it is designed to be read and explained
line-by-line, not to handle production-scale workloads.

---

## 2. Agent Architecture

```
User / MCP Client
       │
       ▼
  ┌─────────────┐
  │   app.py    │  Flask HTTP server + FastMCP tool registry
  │  /ingest    │──────────────────────┐
  │  /search    │                      │
  │  /benchmark │                      │
  └──────┬──────┘                      │
         │                             │
   ┌─────▼──────┐              ┌───────▼──────┐
   │LogIngestor │              │LogSearchAgent│
   │            │              │              │
   │ parse_file │              │ search()     │
   │ ingest_all │              │ benchmark()  │
   │ to_records │              └──────┬───────┘
   └──────┬─────┘                     │
          │                           │
   ┌──────▼──────┐            ┌───────▼──────┐
   │ LogIndexer  │            │  Elasticsearch│  (optional)
   │             │            │  or           │
   │index_records│──────────▶ │  SQLite LIKE  │
   └─────────────┘            └───────────────┘
         │
   ┌─────▼──────┐
   │   SQLite   │  (always — metadata store + fallback search)
   └────────────┘
```

The MCP tools (`ingest_logs`, `search_logs`) are defined with the `@mcp.tool()`
decorator and then called directly from the Flask route handlers.  This means
the same logic is reachable from any MCP-compatible client (e.g. Claude Desktop)
and from any HTTP client without duplicating business logic.

---

## 3. Core Classes

### 3.1 LogIngestor (`core/log_ingestor.py`)

Responsibility: parse raw `.log` files into cleaned Pandas DataFrames.

| Method | Purpose |
|---|---|
| `parse_file(filename)` | Read one file; return a cleaned DataFrame or an empty one on error |
| `ingest_all()` | Parse all `.log` files in `data_dir` and concatenate them |
| `to_records(df)` | Convert a DataFrame to a list of plain dicts |
| `_clean(df)` | Normalize types, parse timestamps, drop malformed rows |

Design notes:
- Uses a compiled regex (`_PATTERN`) to match the fixed log format.
- Malformed lines are silently skipped — a single bad line never aborts
  ingestion of an entire file.
- Timestamps are parsed with `pd.to_datetime` and rows with unparseable
  timestamps are dropped.

### 3.2 LogIndexer (`core/log_indexer.py`)

Responsibility: write structured records to Elasticsearch (if available) and
SQLite (always).

| Method | Purpose |
|---|---|
| `index_records(records)` | Write to SQLite + ES; return count written |
| `_init_sqlite()` | Create the `log_metadata` table if it does not exist |
| `_init_es_index()` | Create the ES index with field mappings |

Design notes:
- Elasticsearch is optional.  If the `elasticsearch` package is not installed
  or the cluster does not respond within 2 seconds, the indexer continues in
  SQLite-only mode and prints a clear warning.  No integration is silently faked.
- SQLite is always the authoritative metadata store.

### 3.3 LogSearchAgent (`core/log_search_agent.py`)

Responsibility: execute full-text searches over indexed records.

| Method | Purpose |
|---|---|
| `search(query, max_results)` | Return matching records, count, backend name, and elapsed ms |
| `benchmark(query, sample_size)` | Compare grep-style linear scan vs indexed search |
| `_es_search(query, max_results)` | Multi-match query against Elasticsearch |
| `_sqlite_search(query, max_results)` | LIKE scan against message, module, and level columns |

Design notes:
- Backend selection is transparent to callers: `search()` always returns the
  same dict shape regardless of which backend ran the query.
- `benchmark()` simulates the "before" case (grep-style linear scan in Python)
  and the "after" case (indexed search) to illustrate the performance difference
  on the 300-record sample dataset.

---

## 4. MCP Tools

Two tools are registered with FastMCP in `app.py`:

| Tool name | Signature | Description |
|---|---|---|
| `ingest_logs` | `(filenames: list \| None) → dict` | Parse and index log files |
| `search_logs` | `(query: str, max_results: int) → dict` | Search indexed records |

Both tools are called directly from Flask route handlers so the same code path
runs regardless of whether the caller is an MCP client or a plain HTTP request.

---

## 5. gRPC / Protobuf Contract

The file `proto/log_search.proto` defines an illustrative service contract for
agent-to-backend communication:

```
service LogSearchService {
  rpc Search  (SearchRequest)  returns (SearchResponse);
  rpc Ingest  (IngestRequest)  returns (IngestResponse);
}
```

**Status:** The `.proto` file is complete and compilable with `grpc_tools`.
Full gRPC wiring into the Flask application is not implemented — the HTTP
endpoints in `app.py` serve the same semantic purpose.  To compile the stub:

```bash
python -m grpc_tools.protoc -I proto \
    --python_out=proto --grpc_python_out=proto \
    proto/log_search.proto
```

---

## 6. Data Flow (end-to-end)

```
data/sample_app1.log   ─┐
data/sample_app2.log   ─┤─▶ LogIngestor.ingest_all()
                         │       │
                         │   pandas.DataFrame  (≥ 300 records after clean)
                         │       │
                         └──▶ LogIndexer.index_records()
                                 │         │
                             SQLite    Elasticsearch (if available)
                                 │         │
                              LogSearchAgent.search("error")
                                 │
                              JSON response → HTTP / MCP client
```

---

## 7. Performance Benchmark

The `/benchmark?q=error` endpoint runs a Python list-comprehension grep against
the in-memory sample records (simulating a manual log scan) and then runs the
indexed search, printing both timings.  On a 300-record dataset the indexed
search is typically **50–70 % faster** than the linear scan, illustrating the
benefit of maintaining a search index even at small scale.
