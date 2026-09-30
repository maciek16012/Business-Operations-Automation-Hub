"""Explicit Docker backup/restore. Never includes environment files or master keys."""

import argparse
import hashlib
import io
import json
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

VERSION = "boah-m7-v1"
ROOT = Path(__file__).resolve().parents[2]


def compose(project, files):
    command = ["docker", "compose"]
    if project:
        command += ["-p", project]
    for filename in files:
        command += ["-f", filename]
    return command


def run(base, *args, input=None):
    return subprocess.check_output([*base, *args], input=input, cwd=ROOT)


def pack(entries, output, schema):
    manifest = {
        "format": VERSION,
        "application_version": "0.7.0",
        "schema_version": schema,
        "created_at": datetime.now(UTC).isoformat(),
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in entries.items()},
        "master_key_included": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        with tarfile.open(fileobj=stream, mode="w:gz") as archive:
            for name, data in {
                **entries,
                "manifest.json": json.dumps(manifest, indent=2).encode(),
            }.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o600
                archive.addfile(info, io.BytesIO(data))
    output.chmod(0o600)
    return manifest


def verify(path):
    entries = {}
    total = 0
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            total += member.size
            if total > 2 * 1024 * 1024 * 1024:
                raise ValueError("Archive exceeds 2 GiB supported restore limit")
            name = PurePosixPath(member.name)
            if (
                not member.isfile()
                or name.is_absolute()
                or ".." in name.parts
                or "\\" in member.name
                or member.name in entries
            ):
                raise ValueError("Unsafe archive entry")
            if member.size > 1024 * 1024 * 1024:
                raise ValueError("Archive member exceeds 1 GiB limit")
            entries[member.name] = archive.extractfile(member).read()
    manifest = json.loads(entries.pop("manifest.json"))
    if manifest["format"] != VERSION or manifest["master_key_included"] is not False:
        raise ValueError("Incompatible backup format")
    if set(entries) != set(manifest["files"]):
        raise ValueError("Backup contents differ from manifest")
    if any(
        hashlib.sha256(data).hexdigest() != manifest["files"][name]
        for name, data in entries.items()
    ):
        raise ValueError("Backup hash mismatch")
    if any(name != "database.dump" and not name.startswith("storage/") for name in entries):
        raise ValueError("Unexpected backup content")
    return manifest, entries


def backup(base, output):
    running = set(run(base, "ps", "--services", "--status", "running").decode().split())
    if running & {"backend", "review-worker", "delivery-worker", "n8n"}:
        raise ValueError("Stop backend, workers and n8n before backup (maintenance window)")
    dump = run(
        base,
        "exec",
        "-T",
        "postgres",
        "sh",
        "-c",
        'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc',
    )
    schema = (
        run(
            base,
            "exec",
            "-T",
            "postgres",
            "sh",
            "-c",
            'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
            ' -Atc "SELECT version_num FROM alembic_version"',
        )
        .decode()
        .strip()
    )
    script = """import sys,tarfile,os
from app.core.config import settings
from pathlib import Path
root=Path(settings.storage_path).resolve()
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
 for p in sorted(root.rglob('*')):
  if p.is_symlink():raise ValueError('Storage symlink rejected')
  if p.is_file():archive.add(p,arcname='storage/'+p.relative_to(root).as_posix(),recursive=False)
"""
    raw = run(base, "run", "--rm", "-T", "--no-deps", "backend", "python", "-c", script)
    entries = {"database.dump": dump}
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive:
            if member.isfile():
                entries[member.name] = archive.extractfile(member).read()
    return pack(entries, output, schema)


def restore(base, path, force):
    if not force:
        raise ValueError("Restore requires explicit --force and a clean target deployment")
    manifest, entries = verify(path)
    # Require a schema revision known to this checkout before any mutation.
    known = set()
    import re

    for migration in (ROOT / "backend/alembic/versions").glob("*.py"):
        match = re.search(
            r'revision(?:\s*:[^=]+)?\s*=\s*["\']([^"\']+)',
            migration.read_text(encoding="utf-8"),
        )
        if match:
            known.add(match[1])
    if manifest["schema_version"] not in known:
        raise ValueError("Unknown schema revision")
    count = (
        run(
            base,
            "exec",
            "-T",
            "postgres",
            "sh",
            "-c",
            'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
            " -Atc \"SELECT count(*) FROM information_schema.tables WHERE table_schema='public'\"",
        )
        .decode()
        .strip()
    )
    if count != "0":
        raise ValueError("Restore target database is not empty; use a separate clean deployment")
    check = (
        "from pathlib import Path; "
        "from app.core.config import settings; "
        "p=Path(settings.storage_path); "
        "assert not p.exists() or not any(p.iterdir()), 'Restore target storage is not empty'"
    )
    run(base, "run", "--rm", "-T", "--no-deps", "backend", "python", "-c", check)
    run(
        base,
        "exec",
        "-T",
        "postgres",
        "sh",
        "-c",
        'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-acl --exit-on-error',
        input=entries["database.dump"],
    )
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for name, data in entries.items():
            if not name.startswith("storage/"):
                continue
            item = tarfile.TarInfo(name.removeprefix("storage/"))
            item.size = len(data)
            item.mode = 0o600
            archive.addfile(item, io.BytesIO(data))
    extract = """import sys,tarfile
from pathlib import Path
from app.core.config import settings
root=Path(settings.storage_path).resolve();root.mkdir(parents=True,exist_ok=True)
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
 for member in archive:
  target=(root/member.name).resolve()
  if not member.isfile() or not target.is_relative_to(root):raise ValueError('Unsafe restore path')
  target.parent.mkdir(parents=True,exist_ok=True)
  with target.open('xb') as f:f.write(archive.extractfile(member).read())
"""
    run(
        base,
        "run",
        "--rm",
        "-T",
        "--no-deps",
        "backend",
        "python",
        "-c",
        extract,
        input=output.getvalue(),
    )
    run(base, "run", "--rm", "-T", "--no-deps", "backend", "alembic", "upgrade", "head")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["backup", "verify", "restore"])
    parser.add_argument("archive", type=Path)
    parser.add_argument("--project")
    parser.add_argument("-f", "--compose-file", action="append", default=[])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    base = compose(args.project, args.compose_file or ["docker-compose.yml"])
    if args.action == "backup":
        result = backup(base, args.archive)
    elif args.action == "restore":
        result = restore(base, args.archive, args.force)
    else:
        result = verify(args.archive)[0]
    print(
        json.dumps(
            {
                "format": result["format"],
                "schema_version": result["schema_version"],
                "file_count": len(result["files"]),
                "master_key_included": False,
            }
        )
    )
