"""Stable, explicit directory used by the API and integration mappings."""

import hashlib
import json
from pathlib import Path


class Directory:
    def __init__(self, path: Path):
        raw = path.read_bytes()
        self.version = hashlib.sha256(raw).hexdigest()
        self.entries = json.loads(raw)
        self.by_id = {entry["id"]: entry for entry in self.entries}
        self.by_name = {entry["name"]: entry for entry in self.entries}
        if len(self.by_id) != len(self.entries) or len(self.by_name) != len(
            self.entries
        ):
            raise ValueError("Duplicate directory entries")

    def resolve(self, names):
        return [self.by_name[name] for name in names]
