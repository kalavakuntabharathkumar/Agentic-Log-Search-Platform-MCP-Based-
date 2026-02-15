"""
LogIngestor — reads and parses raw Windows application log files into
structured Pandas DataFrames.

Expected log line format:
    YYYY-MM-DD HH:MM:SS  LEVEL  MODULE  Message text here
"""

import re
from pathlib import Path
from typing import List, Dict

import pandas as pd


class LogIngestor:
    """
    Parses raw .log files into cleaned DataFrames.

    Each file is expected to contain lines in the format:
        2026-02-14 08:00:01 INFO WindowsUpdateClient Checking for updates
    Malformed lines are silently skipped so a partial file never crashes
    the pipeline.
    """

    # Regex that captures the four fixed columns in a log line.
    _PATTERN = re.compile(
        r'^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+'
        r'(?P<level>\w+)\s+(?P<module>\w+)\s+(?P<message>.+)$'
    )

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_file(self, filename: str) -> pd.DataFrame:
        """
        Read a single log file and return a cleaned DataFrame.
        Returns an empty DataFrame (with correct columns) when the file
        is missing or contains no parseable lines.
        """
        filepath = self.data_dir / filename
        _empty = pd.DataFrame(
            columns=["timestamp", "level", "module", "message", "source_file"]
        )

        if not filepath.exists():
            return _empty

        records: List[Dict] = []
        with open(filepath, "r", encoding="utf-8") as fh:
            for line in fh:
                m = self._PATTERN.match(line.strip())
                if m:
                    record = m.groupdict()
                    record["source_file"] = filename
                    records.append(record)

        if not records:
            return _empty

        return self._clean(pd.DataFrame(records))

    def ingest_all(self) -> pd.DataFrame:
        """
        Ingest every .log file found in data_dir and return a combined,
        timestamp-sorted DataFrame.
        """
        frames = [self.parse_file(f.name) for f in self.data_dir.glob("*.log")]
        if not frames:
            return pd.DataFrame(
                columns=["timestamp", "level", "module", "message", "source_file"]
            )
        combined = pd.concat(frames, ignore_index=True)
        return combined.sort_values("timestamp").reset_index(drop=True)

    def to_records(self, df: pd.DataFrame) -> List[Dict]:
        """Convert a DataFrame to plain dicts; timestamps become ISO strings."""
        out = df.copy()
        out["timestamp"] = out["timestamp"].astype(str)
        return out.to_dict(orient="records")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize column types and drop rows with unparseable timestamps."""
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["level"]     = df["level"].str.upper().str.strip()
        df["module"]    = df["module"].str.strip()
        df["message"]   = df["message"].str.strip()
        return df.dropna(subset=["timestamp"]).reset_index(drop=True)
