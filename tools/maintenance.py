"""Purge terminal job history using the configured retention period."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.storage.audit import AuditStore

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--retention-days", type=int)
    args = parser.parse_args()
    settings = Settings.from_env()
    days = (
        settings.retention_days if args.retention_days is None else args.retention_days
    )
    if days <= 0:
        parser.error("retention-days must be positive")
    store = AuditStore(settings.db_path)
    store.init()
    store.purge(days)
    print(f"Purged terminal jobs older than {days} days.")
