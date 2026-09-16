"""Copy the SQLite database to data/backups with a timestamp."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SOURCE = DATA / "ganglia.db"
DEST = DATA / "backups"


def main() -> None:
    """Write data/backups/ganglia-UTC.db if the live database exists."""

    if not SOURCE.exists():
        raise SystemExit(f"no database at {SOURCE}")
    DEST.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = DEST / f"ganglia-{stamp}.db"
    shutil.copy2(SOURCE, target)
    print(target)


if __name__ == "__main__":
    main()
