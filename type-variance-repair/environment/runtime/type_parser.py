"""Parses type definition records from JSONL data files.

Reads type declarations, generic declarations, assignments, and constraints
from source module files. Applies category filtering based on configuration.
"""
import json
import os
import configparser


class TypeRecord:
    """Represents a single parsed type record from a source file."""

    def __init__(self, data):
        self.id = data["id"]
        self.source_module = data["source_module"]
        self.kind = data["kind"]
        self.name = data.get("name")
        self.parent = data.get("parent")
        self.category = data.get("category", "")
        self.timestamp = data.get("timestamp", "")
        self.seq = data.get("seq", 0)
        self.type_param = data.get("type_param")
        self.variance = data.get("variance")
        self.target = data.get("target")
        self.source = data.get("source")
        self.context = data.get("context")
        self.priority = data.get("priority", 0)
        self.scope = data.get("scope")
        self.type_var = data.get("type_var")
        self.bound = data.get("bound")

    def to_dict(self):
        """Serialize to dictionary for output."""
        result = {"id": self.id, "source_module": self.source_module, "kind": self.kind}
        if self.name:
            result["name"] = self.name
        if self.parent:
            result["parent"] = self.parent
        if self.type_param:
            result["type_param"] = self.type_param
            result["variance"] = self.variance
        if self.target:
            result["target"] = self.target
            result["source"] = self.source
            result["context"] = self.context
        if self.priority:
            result["priority"] = self.priority
        if self.scope:
            result["scope"] = self.scope
            result["type_var"] = self.type_var
            result["bound"] = self.bound
        result["category"] = self.category
        result["timestamp"] = self.timestamp
        result["seq"] = self.seq
        return result


class TypeParser:
    """Parses JSONL source files and filters by configured categories."""

    def __init__(self, config_path):
        self._config = configparser.ConfigParser()
        self._config.read(config_path)
        self._input_dir = self._config.get("sources", "input_dir")
        # Load allowed module categories from config
        raw_modules = self._config.get("sources", "modules")
        self._allowed_modules = set(item.strip() for item in raw_modules.split(","))

    def parse_all(self, base_dir):
        """Parse all JSONL files from the configured input directory.

        Returns list of TypeRecord objects filtered by allowed categories.
        """
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
                    record = TypeRecord(data)
                    # Filter by allowed module categories
                    if record.category in self._allowed_modules:
                        records.append(record)

        return records
