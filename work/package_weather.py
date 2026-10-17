"""Publish a fixed CSV snapshot from a local collection, or verify it offline.

No network calls. Raw HTTP responses and credentials are never copied.
The source collection must already contain the reviewed catalog and dictionary.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote, quote_plus

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from weather_collect import OUT, Config, save_json, write_csv
from weather_dataset import read_csv

DEFAULT_SNAPSHOT = ROOT / 'outputs' / 'jeju_weather' / '20261017'
METADATA = (
    'collection_catalog_36.csv', 'field_dictionary.csv', 'api_status.csv',
    'collection_summary.json', 'radar_validation.json',
    'radar_coordinate_validation.json', 'latest/latest.json',
)


def portable_paths(value):
    if isinstance(value, dict):
        return {k: portable_paths(v) for k, v in value.items()}
    if isinstance(value, list):
        return [portable_paths(v) for v in value]
    return value.replace('\\', '/') if isinstance(value, str) else value


def contained(root, relative):
    relative = relative.replace('\\', '/')
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or Path(relative).is_absolute():
        raise ValueError('Snapshot path must stay inside its folder')
    if any(part in {'.env', 'runtime', '.git'} for part in Path(relative).parts):
        raise ValueError('Private path in snapshot')
    return path


def verify(target):
    target = Path(target)
    manifest = json.loads((target / 'MANIFEST.json').read_text('utf-8'))
    for entry in manifest['files']:
        path = contained(target, entry['path'])
        data = path.read_bytes()
        if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError('Snapshot checksum mismatch: ' + entry['path'])
    actual = {p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()}
    expected = {entry['path'] for entry in manifest['files']} | {'MANIFEST.json'}
    if actual != expected:
        raise ValueError('Unlisted or missing snapshot files')
    for entry in read_csv(target / 'file_inventory.csv'):
        path = contained(target, entry['file'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Dataset inventory checksum mismatch')
        if len(read_csv(path)) != int(entry['rows']):
            raise ValueError('Dataset inventory row count mismatch')
    latest = json.loads((target / 'latest' / 'latest.json').read_text('utf-8'))
    for state in latest['sources'].values():
        if not contained(target, state['csv']).is_file():
            raise ValueError('Missing immutable latest CSV')
    return dict(files=len(manifest['files']), dataset_count=len(read_csv(target / 'file_inventory.csv')),
                bytes=sum(e['bytes'] for e in manifest['files']), checksums='passed', api_called=False)


def publish(source, target, static_revision):
    source, target = Path(source), Path(target)
    if not re.fullmatch(r'[0-9a-f]{7,40}', static_revision or ''):
        raise ValueError('Specify the Git revision used by the source static inventory')
    if target.exists() and any(target.iterdir()):
        raise ValueError('Use a new empty snapshot folder; published snapshots are immutable')
    inventory = portable_paths(read_csv(source / 'file_inventory.csv'))
    selected = {row['file'] for row in inventory}
    selected.update(('csv/stations_aws.csv', 'csv/stations_sfc.csv'))
    for relative in list(selected):
        raw = Path(relative).with_name(Path(relative).stem + '_raw.csv').as_posix()
        if contained(source, raw).is_file():
            selected.add(raw)
    selected.update(METADATA)
    selected.update(p.relative_to(source).as_posix() for p in (source / 'quality').glob('*') if p.is_file())
    latest = json.loads((source / 'latest' / 'latest.json').read_text('utf-8'))
    selected.update(state['csv'].replace('\\', '/') for state in latest['sources'].values())
    # Read the key only to exclude it from publication; never put it in metadata.
    key = Config.load(ROOT).key
    forbidden = {v.encode() for v in (key, quote(key, safe=''), quote_plus(key)) if v}
    payloads = {}
    for relative in sorted(selected):
        path = contained(source, relative)
        data = path.read_bytes()
        if any(token in data for token in forbidden):
            raise ValueError('Credential detected; snapshot was not written')
        if len(data) >= 50 * 1024 * 1024:
            raise ValueError('Snapshot file exceeds the project 50 MiB limit')
        if path.suffix == '.json':
            data = (json.dumps(portable_paths(json.loads(data)), ensure_ascii=False, indent=2) + '\n').encode()
        payloads[relative] = data
    target.mkdir(parents=True, exist_ok=True)
    for relative, data in payloads.items():
        destination = contained(target, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    write_csv(target / 'file_inventory.csv', inventory)
    static = read_csv(source / 'static_inventory.csv')
    write_csv(target / 'static_inventory.csv', [dict(
        {k: v for k, v in r.items() if k != 'delivery_path'}, source_git_revision=static_revision) for r in static])
    files = [dict(path=p.relative_to(target).as_posix(), bytes=p.stat().st_size,
                  sha256=hashlib.sha256(p.read_bytes()).hexdigest())
             for p in sorted(target.rglob('*')) if p.is_file()]
    save_json(target / 'MANIFEST.json', dict(
        schema_version=1, published_at_utc=datetime.now(timezone.utc).isoformat(),
        snapshot_type='fixed research snapshot; not a live feed',
        source='Korea Meteorological Administration API Hub',
        source_url='https://apihub.kma.go.kr/', credential_scan='passed',
        raw_http_responses_included=False,
        provenance_note='API results and local raw-response references are audit metadata; raw HTTP files stay local.',
        files=files))
    return verify(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=OUT)
    parser.add_argument('--output', type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument('--static-source-revision', help='Git commit of the static files referenced by the source inventory')
    parser.add_argument('--verify-only', action='store_true', help='Verify without reading .env or calling an API')
    args = parser.parse_args()
    print(json.dumps(verify(args.output) if args.verify_only else publish(args.input, args.output, args.static_source_revision)))
