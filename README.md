# Agentic Log Search Platform (MCP-Based)

A Python project that ingests Windows application log files and exposes
search functionality via Flask and FastMCP.

**Author:** Bharath Kumar Kalavakunta  
**Duration:** Feb 14 – 20, 2026

---

## Stack

- Flask — HTTP server
- FastMCP — MCP tool definitions
- Elasticsearch (optional) + SQLite — search backends
- Pandas — log parsing and transformation

## Structure (in progress)

```
app.py          # Flask + FastMCP entry point (coming)
core/           # LogIngestor, LogIndexer, LogSearchAgent (coming)
proto/          # gRPC service contract (coming)
data/           # Sample Windows application log files (coming)
tests/          # pytest suite (coming)
```

Setup and usage instructions will be added once all components are built.
