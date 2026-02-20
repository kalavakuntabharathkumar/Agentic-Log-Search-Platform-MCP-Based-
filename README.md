# Agentic Log Search Platform (MCP-Based)

A small Python project that ingests Windows application log files, indexes them
for fast full-text search, and exposes the ingest and search operations as both
HTTP endpoints (Flask) and MCP tools (FastMCP).

**Project duration:** Feb 14 – 20, 2026  
**Author:** Bharath Kumar Kalavakunta

---

## Features

- **Agent-based design** via FastMCP — two tools (`ingest_logs`, `search_logs`) callable from any MCP-compatible client
- **Dual-backend indexing** — Elasticsearch for fast full-text search; SQLite as the always-on metadata store and fallback
- **Pandas data pipeline** — parses and cleans 300+ sample log records before indexing
- **Performance benchmark** — `/benchmark` endpoint compares grep-style linear scan vs indexed search (~60 % faster)
- **gRPC contract** — a `.proto` file documents the agent-to-backend communication contract (illustrative; HTTP endpoints are the active interface)
- **Test suite** — 5 pytest cases covering parsing, indexing, and search (including the empty-result case)

---

## Project Structure

```
.
├── app.py                  # Flask app + FastMCP tool definitions
├── core/
│   ├── log_ingestor.py     # LogIngestor: parse raw log files with Pandas
│   ├── log_indexer.py      # LogIndexer: write to Elasticsearch + SQLite
│   └── log_search_agent.py # LogSearchAgent: query indexed records
├── proto/
│   └── log_search.proto    # gRPC service contract (illustrative)
├── data/
│   ├── sample_app1.log     # 184 sample entries — WindowsUpdateClient
│   └── sample_app2.log     # 144 sample entries — SecurityCenterService
├── tests/
│   └── test_core.py        # 5 pytest cases
├── DESIGN.md               # Architecture and design decisions
├── requirements.txt
└── conftest.py             # Adds project root to sys.path for pytest
```

---

## Setup

### 1. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Elasticsearch (optional)

The application works without Elasticsearch — it falls back to SQLite LIKE
search automatically.  If you have access to an Elasticsearch cluster
(local or cloud trial), set the host in `app.py`:

```python
indexer = LogIndexer(es_host="http://localhost:9200")
agent   = LogSearchAgent(es_host="http://localhost:9200")
```

If Elasticsearch is not reachable the application prints:

```
[LogIndexer] Elasticsearch unreachable — using SQLite only.
```

No other changes are needed.

---

## Running the Application

```bash
python app.py
```

The Flask development server starts on `http://localhost:5000`.

### Ingest sample logs

```bash
curl -X POST http://localhost:5000/ingest
```

Or ingest specific files:

```bash
curl -X POST http://localhost:5000/ingest \
     -H "Content-Type: application/json" \
     -d '{"filenames": ["sample_app1.log"]}'
```

### Search indexed logs

```bash
curl -X POST http://localhost:5000/search \
     -H "Content-Type: application/json" \
     -d '{"query": "error", "max_results": 20}'
```

Example response:

```json
{
  "count": 8,
  "backend": "sqlite",
  "elapsed_ms": 1.42,
  "results": [
    {
      "id": 3,
      "source_file": "sample_app1.log",
      "module": "WindowsUpdateClient",
      "level": "ERROR",
      "message": "Failed to reach update server: timeout after 30s",
      "timestamp": "2026-02-14 10:00:01",
      "ingested_at": "2026-02-14 08:14:30"
    }
  ]
}
```

### Run the performance benchmark

```bash
curl "http://localhost:5000/benchmark?q=error"
```

Example response:

```json
{
  "query": "error",
  "grep_ms": 0.18,
  "indexed_ms": 0.07,
  "reduction_pct": 61.1
}
```

### Health check

```bash
curl http://localhost:5000/health
```

---

## Running Tests

```bash
pytest tests/ -v --cov=core --cov-report=term-missing
```

Expected output: 5 tests passing with ≥ 80 % coverage on the three core classes.

---

## gRPC Contract

The file `proto/log_search.proto` defines the agent-to-backend communication
contract.  It is illustrative — the active interface is the Flask HTTP API.
To compile Python stubs from the proto:

```bash
python -m grpc_tools.protoc -I proto \
    --python_out=proto --grpc_python_out=proto \
    proto/log_search.proto
```

See `DESIGN.md §5` for details.

---

## Architecture

See [DESIGN.md](DESIGN.md) for a full description of the agent architecture,
the three core classes, the MCP tools, and the gRPC contract.

---

## Notes

- Elasticsearch integration is fully implemented but optional.  If unavailable,
  the system uses SQLite without any code changes required.
- The gRPC contract is not wired into the Flask app — the HTTP endpoints serve
  the same semantic purpose and are the active interface.
- The benchmark endpoint measures real timing on the sample dataset; results
  vary by machine but consistently show a meaningful reduction.
