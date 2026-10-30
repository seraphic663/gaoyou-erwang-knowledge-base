"""Pack and verify the immutable machine SQLite release used by Railway."""
from __future__ import annotations

import argparse
import hashlib
import json
import lzma
import os
import sqlite3
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def active_run(path: Path) -> dict:
    connection = sqlite3.connect(f'file:{path.resolve().as_posix()}?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('PRAGMA query_only=ON')
        assert connection.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        rows = connection.execute(
            "SELECT run_id, parser_sha256, machine_library_sha256, input_manifest_sha256, content_sha256 "
            "FROM parser_runs WHERE run_status='active'"
        ).fetchall()
        if len(rows) != 1:
            raise ValueError('Machine bundle must contain exactly one active run')
        return dict(rows[0])
    finally:
        connection.close()


def pack(db: Path, bundle: Path, manifest_path: Path) -> dict:
    run = active_run(db)
    bundle.parent.mkdir(parents=True, exist_ok=True)
    temporary = bundle.with_name(bundle.name + '.partial')
    with db.open('rb') as source, lzma.open(temporary, 'wb', preset=6) as destination:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            destination.write(chunk)
    manifest = {
        'schema': 'machine-library.bundle.v1',
        'database_bytes': db.stat().st_size, 'database_sha256': digest(db),
        'bundle_bytes': temporary.stat().st_size, 'bundle_sha256': digest(temporary),
        'run': run,
    }
    os.replace(temporary, bundle)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def unpack(bundle: Path, manifest_path: Path, output: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('schema') != 'machine-library.bundle.v1':
        raise ValueError('Unsupported machine release manifest')
    if digest(bundle) != manifest['bundle_sha256']:
        raise ValueError('Compressed machine release checksum mismatch')
    if output.exists():
        if digest(output) != manifest['database_sha256']:
            raise ValueError('Refusing to overwrite a different existing machine database')
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + '.partial')
        try:
            with lzma.open(bundle, 'rb') as source, temporary.open('wb') as destination:
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    destination.write(chunk)
            if temporary.stat().st_size != manifest['database_bytes'] or digest(temporary) != manifest['database_sha256']:
                raise ValueError('Expanded machine database checksum mismatch')
            if active_run(temporary) != manifest['run']:
                raise ValueError('Machine run differs from the release manifest')
            os.replace(temporary, output)
        finally:
            if temporary.exists():
                temporary.unlink()
    if active_run(output) != manifest['run']:
        raise ValueError('Machine run differs from the release manifest')
    return {'ok': True, 'run': manifest['run'], 'database_bytes': output.stat().st_size,
            'database_sha256': manifest['database_sha256']}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    packing = commands.add_parser('pack')
    packing.add_argument('--db', type=Path, required=True)
    packing.add_argument('--bundle', type=Path, required=True)
    packing.add_argument('--manifest', type=Path, required=True)
    expanding = commands.add_parser('unpack')
    expanding.add_argument('--bundle', type=Path, required=True)
    expanding.add_argument('--manifest', type=Path, required=True)
    expanding.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = pack(args.db, args.bundle, args.manifest) if args.command == 'pack' else unpack(args.bundle, args.manifest, args.output)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
