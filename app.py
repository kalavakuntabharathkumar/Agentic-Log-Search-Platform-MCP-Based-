"""
Agentic Log Search Platform — Flask application.

Exposes two MCP tools (defined with FastMCP) as callable HTTP endpoints:

  POST /ingest        — parse and index log files
  POST /search        — full-text search over indexed logs
  GET  /benchmark     — compare grep vs indexed search timing
  GET  /health        — liveness check

Usage:
  python app.py
  # then:
  curl -X POST http://localhost:5000/ingest
  curl -X POST http://localhost:5000/search -H "Content-Type: application/json" \
       -d '{"query": "error"}'
"""

from flask import Flask, request, jsonify

# FastMCP: defines agent tools that can be surfaced to any MCP-compatible client.
from mcp.server.fastmcp import FastMCP

import pandas as pd

from core.log_ingestor    import LogIngestor
from core.log_indexer     import LogIndexer
from core.log_search_agent import LogSearchAgent

# ── Application setup ───────────────────────────────────────────────────────

app = Flask(__name__)
mcp = FastMCP("log-search-agent")

# One shared instance of each core class (no per-request re-construction)
ingestor = LogIngestor(data_dir="data")
indexer  = LogIndexer()
agent    = LogSearchAgent()


# ── MCP Tool Definitions ────────────────────────────────────────────────────

@mcp.tool()
def ingest_logs(filenames: list | None = None) -> dict:
    """
    MCP Tool: Parse log files and push records into the backend stores.

    Args:
        filenames: optional list of filenames (relative to data/).
                   When None, all .log files in data/ are ingested.
    Returns:
        dict with 'status', 'indexed' count, and 'files' processed.
    """
    if filenames:
        frames = [ingestor.parse_file(f) for f in filenames]
        combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    else:
        combined = ingestor.ingest_all()

    if combined.empty:
        return {"status": "no_data", "indexed": 0, "files": filenames or "all"}

    records = ingestor.to_records(combined)
    count   = indexer.index_records(records)
    return {"status": "ok", "indexed": count, "files": filenames or "all"}


@mcp.tool()
def search_logs(query: str, max_results: int = 50) -> dict:
    """
    MCP Tool: Search indexed log records.

    Args:
        query:       free-text search string.
        max_results: maximum number of entries to return (default 50).
    Returns:
        dict with 'results', 'count', 'backend', and 'elapsed_ms'.
    """
    if not query or not query.strip():
        return {"error": "query must be a non-empty string"}
    return agent.search(query.strip(), max_results)


# ── Flask HTTP Routes (thin wrappers around the MCP tools) ─────────────────

@app.route("/ingest", methods=["POST"])
def http_ingest():
    body      = request.get_json(silent=True) or {}
    filenames = body.get("filenames")           # optional list of filenames
    return jsonify(ingest_logs(filenames=filenames))


@app.route("/search", methods=["POST"])
def http_search():
    body        = request.get_json(silent=True) or {}
    query       = body.get("query", "")
    max_results = int(body.get("max_results", 50))
    return jsonify(search_logs(query=query, max_results=max_results))


@app.route("/benchmark", methods=["GET"])
def http_benchmark():
    query = request.args.get("q", "error")
    return jsonify(agent.benchmark(query))


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
