from __future__ import annotations

import argparse
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import make_url


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PostgreSQL backup/restore helper for M6 runbook automation.",
    )
    parser.add_argument(
        "action",
        choices={"backup", "restore"},
        help="choose backup or restore workflow",
    )
    parser.add_argument(
        "--output",
        help="output file path for backup action",
    )
    parser.add_argument(
        "--input",
        help="existing backup file for restore action",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_BACKUP_URL") or os.getenv("DATABASE_URL"),
        help="database connection string (falls back to env var)",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="dump schema only when running backup",
    )
    return parser.parse_args()


def to_pg_dump_url(database_url: str | None) -> str:
    if not database_url:
        raise SystemExit("database url required, supply --database-url or env var")

    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        raise SystemExit(f"postgresql required, got driver {url.drivername}")

    cleaned = url.set(drivername="postgresql")
    return str(cleaned)


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def run_backup(database_url: str, output: Path, schema_only: bool) -> None:
    ensure_parent_dir(output)
    cmd = [
        "pg_dump",
        "--format",
        "c",
        "--no-owner",
        "--no-privileges",
        "--file",
        str(output),
        "--dbname",
        database_url,
    ]
    if schema_only:
        cmd.append("--schema-only")

    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise SystemExit(f"pg_dump failed with exit code {result.returncode}")


def run_restore(database_url: str, backup_file: Path) -> None:
    if not backup_file.exists():
        raise SystemExit(f"backup file not found: {backup_file}")

    cmd = [
        "pg_restore",
        "--clean",
        "--if-exists",
        "--format",
        "c",
        "--no-owner",
        "--no-privileges",
        "--dbname",
        database_url,
        str(backup_file),
    ]

    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise SystemExit(f"pg_restore failed with exit code {result.returncode}")


def main() -> None:
    args = parse_args()
    pg_url = to_pg_dump_url(args.database_url)

    if args.action == "backup":
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")
        default_output = Path("backups") / f"pg_backup_{timestamp}.dump"
        output_path = Path(args.output or default_output)
        run_backup(pg_url, output_path, args.schema_only)
        print(f"backup completed: {output_path}")
        return

    if args.action == "restore":
        if not args.input:
            raise SystemExit("restore requires --input path to backup file")
        backup_file = Path(args.input)
        run_restore(pg_url, backup_file)
        print(f"restore completed: {backup_file}")
        return


if __name__ == "__main__":
    main()
