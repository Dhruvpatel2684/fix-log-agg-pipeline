"""Parses directed graph edge records from JSONL data files.

Reads edge definitions from subsystem data files and applies category
filtering based on the configured node categories.
"""
import json
import os
import configparser


class EdgeRecord:
    """Represents a directed edge in the dependency graph."""

    def __init__(self, data):
        self.id = data["id"]
        self.source = data["source"]
        self.target = data["target"]
        self.category = data.get("category", "")
        self.weight = data.get("weight", 1)
        self.subsystem = data.get("subsystem", "")
        self.timestamp = data.get("timestamp", "")
        self.seq = data.get("seq", 0)


class GraphParser:
    """Parses edge records from JSONL files with category filtering."""

    def __init__(self, config_path):
        self._config = configparser.ConfigParser()
        self._config.read(config_path)
        self._input_dir = self._config.get("graph", "input_dir")
        raw_categories = self._config.get("graph", "node_categories")
        self._allowed_categories = set(raw_categories.split(","))

    def parse_all(self, base_dir):
        """Parse all edge files and return filtered EdgeRecord list."""
        data_dir = os.path.join(base_dir, self._input_dir)
        records = []

        for filename in sorted(os.listdir(data_dir)):
            if not filename.endswith(".jsonl"):
                continue
            filepath = os.path.join(data_dir, filename)
            with open(filepath, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    record = EdgeRecord(data)
                    if record.category in self._allowed_categories:
                        records.append(record)

        return records
