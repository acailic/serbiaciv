#!/usr/bin/env python3
"""Report local source-cache and published data sizes; no network requests.

Raw sizes describe the current cache, not bytes transferred in a particular build.
Gzip sizes are independently compressed local estimates, not observed HTTP traffic.
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def report(raw_dir: Path, interim_dir: Path, web_data: Path) -> dict:
    def files(directory: Path):
        return sorted(p for p in directory.rglob('*') if p.is_file()) if directory.is_dir() else []

    raw = {}
    if raw_dir.is_dir():
        for path in files(raw_dir):
            relative = path.relative_to(raw_dir)
            group = relative.parts[0] if len(relative.parts) > 1 else '.'
            entry = raw.setdefault(group, {'files': 0, 'bytes': 0})
            entry['files'] += 1
            entry['bytes'] += path.stat().st_size

    published = {}
    for path in files(web_data):
        content = path.read_bytes()
        published[path.relative_to(web_data).as_posix()] = {
            'bytes': len(content),
            'gzip_bytes': len(gzip.compress(content, mtime=0)),
        }
    interim_files = files(interim_dir)
    return {
        'raw_cache': raw,
        'interim': {'files': len(interim_files), 'bytes': sum(p.stat().st_size for p in interim_files)},
        'published_data': published,
        'published_totals': {'bytes': sum(v['bytes'] for v in published.values()),
                             'gzip_bytes': sum(v['gzip_bytes'] for v in published.values())},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, default=ROOT / 'data/raw')
    parser.add_argument('--interim', type=Path, default=ROOT / 'data/interim')
    parser.add_argument('--web-data', type=Path, default=ROOT / 'web/data')
    args = parser.parse_args()
    print(json.dumps(report(args.raw, args.interim, args.web_data), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
