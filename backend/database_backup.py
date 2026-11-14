"""Create restrictive PostgreSQL dumps and restore only to an explicitly named target.

Uses pg_dump/pg_restore from PATH. Credentials travel through PG* environment,
never command-line arguments. Separately escrow ENCRYPTION_KEY and CONSENT_LEDGER_KEY.
"""

import argparse
import os
from pathlib import Path
import subprocess
from urllib.parse import urlparse, unquote


def pg_environment(url):
    parsed = urlparse(url)
    if (
        parsed.scheme not in ("postgres", "postgresql")
        or not parsed.hostname
        or not parsed.path.strip("/")
    ):
        raise ValueError("Use a PostgreSQL URL with a host and database")
    env = os.environ.copy()
    env.update(
        PGHOST=parsed.hostname,
        PGPORT=str(parsed.port or 5432),
        PGDATABASE=unquote(parsed.path[1:]),
        PGUSER=unquote(parsed.username or "postgres"),
        PGPASSWORD=unquote(parsed.password or ""),
    )
    from urllib.parse import parse_qs

    for key, values in parse_qs(parsed.query).items():
        if key in ("sslmode", "sslrootcert", "sslcert", "sslkey"):
            env["PG" + key.upper()] = values[-1]
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "verify", "restore"])
    parser.add_argument("file", type=Path)
    parser.add_argument(
        "--confirm-target",
        help="Exact disposable target database name; required for restore",
    )
    args = parser.parse_args()
    os.umask(0o077)
    if args.action == "backup":
        env = pg_environment(os.environ["DATABASE_URL"])
        # Exclusive creation prevents accidental overwrites and symlink following.
        fd = os.open(args.file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as out:
                subprocess.run(
                    ["pg_dump", "--format=custom", "--no-owner", "--no-acl"],
                    env=env,
                    stdout=out,
                    check=True,
                )
        except Exception:
            args.file.unlink(missing_ok=True)
            raise
        print(
            "Backup created. Store it encrypted and escrow application keys separately."
        )
    elif args.action == "verify":
        subprocess.run(
            ["pg_restore", "--list", str(args.file)],
            stdout=subprocess.DEVNULL,
            check=True,
        )
        print("Archive readable. This does not replace a restore drill.")
    else:
        env = pg_environment(os.environ["RESTORE_DATABASE_URL"])
        source = os.environ.get("DATABASE_URL")
        if source:
            src = pg_environment(source)
            if all(src[k] == env[k] for k in ("PGHOST", "PGPORT", "PGDATABASE")):
                parser.error("Restore target must differ from the source database")
        if args.confirm_target != env["PGDATABASE"]:
            parser.error("--confirm-target must equal the target database name")
        # No --clean: refuse destructive replacement of existing schema/data.
        subprocess.run(
            [
                "pg_restore",
                "--exit-on-error",
                "--single-transaction",
                "--no-owner",
                "--no-acl",
                "--dbname",
                env["PGDATABASE"],
                str(args.file),
            ],
            env=env,
            check=True,
        )
        print(
            "Restore completed. Validate decryption with the matching application keys before use."
        )


if __name__ == "__main__":
    main()
