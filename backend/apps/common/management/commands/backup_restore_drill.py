"""Dump the database, restore into a scratch DB, and compare key counts."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Backup/restore drill: pg_dump, restore to scratch DB, compare counts."

    def handle(self, *args, **options):
        db = settings.DATABASES["default"]
        env = os.environ.copy()
        env["PGPASSWORD"] = str(db["PASSWORD"])
        env["PGCLIENTENCODING"] = "UTF8"

        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM organizations_facility")
            facility_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM accounts_user")
            user_count = cursor.fetchone()[0]

        scratch = f"{db['NAME']}_restore_drill"
        dump_path = Path(tempfile.gettempdir()) / "hims_backup_drill.sql"

        common = [
            "-h",
            str(db["HOST"]),
            "-p",
            str(db["PORT"]),
            "-U",
            str(db["USER"]),
        ]

        def run(cmd: list[str]) -> subprocess.CompletedProcess:
            return subprocess.run(cmd, check=True, env=env, capture_output=True)

        try:
            run(["pg_dump", *common, "-d", str(db["NAME"]), "-f", str(dump_path)])
            # DROP/CREATE must not run inside an implicit transaction (Windows psql).
            run(
                [
                    "psql",
                    *common,
                    "-d",
                    "postgres",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-c",
                    f"DROP DATABASE IF EXISTS {scratch};",
                ]
            )
            run(
                [
                    "psql",
                    *common,
                    "-d",
                    "postgres",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-c",
                    f"CREATE DATABASE {scratch} OWNER {db['USER']};",
                ]
            )
            run(
                [
                    "psql",
                    *common,
                    "-d",
                    scratch,
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-f",
                    str(dump_path),
                ]
            )
            result = subprocess.run(
                [
                    "psql",
                    *common,
                    "-d",
                    scratch,
                    "-t",
                    "-A",
                    "-c",
                    "SELECT (SELECT COUNT(*) FROM organizations_facility)::text || '|' || "
                    "(SELECT COUNT(*) FROM accounts_user)::text;",
                ],
                check=True,
                env=env,
                capture_output=True,
                text=True,
            )
            parts = result.stdout.strip().split("|")
            restored_facilities, restored_users = int(parts[0]), int(parts[1])
            if restored_facilities != facility_count or restored_users != user_count:
                raise CommandError(
                    f"Count mismatch: facilities {facility_count}->{restored_facilities}, "
                    f"users {user_count}->{restored_users}"
                )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Backup restore drill OK: facilities={facility_count} users={user_count}"
                )
            )
        except FileNotFoundError as exc:
            raise CommandError(
                "pg_dump/psql not found. Install PostgreSQL client tools."
            ) from exc
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            raise CommandError(f"Drill failed: {detail or exc}") from exc
        finally:
            subprocess.run(
                [
                    "psql",
                    *common,
                    "-d",
                    "postgres",
                    "-c",
                    f"DROP DATABASE IF EXISTS {scratch};",
                ],
                env=env,
                capture_output=True,
            )
            if dump_path.exists():
                dump_path.unlink(missing_ok=True)
