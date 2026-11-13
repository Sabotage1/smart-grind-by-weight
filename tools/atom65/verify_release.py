#!/usr/bin/env python3
"""Validate committed release payloads and the matching installed source."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
RELEASE = ROOT / 'release/atom65-build19'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--meshes', action='store_true')
    args = parser.parse_args()
    for line in (RELEASE / 'SHA256SUMS').read_text().splitlines():
        sha, name = line.split(None, 1)
        path = (RELEASE / name.strip()).resolve()
        assert path.is_relative_to(RELEASE), name
        assert digest(path) == sha, name
    metadata = json.loads((RELEASE / 'source-metadata/source-sha256.json').read_text())
    for name, sha in metadata.items():
        path = RELEASE / 'source-metadata/git_info.h' if name == 'include/git_info.h' else ROOT / name
        assert digest(path) == sha, name
    manifest = json.loads((ROOT / '3d_files/atom65/MANIFEST.json').read_text())
    for item in manifest['files']:
        path = ROOT / '3d_files/atom65' / item['path']
        assert path.stat().st_size == item['bytes'] and digest(path) == item['sha256'], str(path)
    plugin = ROOT / 'integrations/decaid/atom65.reaplugin'
    with ZipFile(RELEASE / 'atom65-profile-sync-0.1.0.zip') as archive:
        assert json.loads(archive.read('manifest.json'))['version'] == '0.1.0'
    latest = ROOT / 'release/decaid-atom65-0.1.1'
    sha, filename = (latest / 'SHA256SUMS').read_text().split()
    assert digest(latest / filename) == sha
    with ZipFile(latest / filename) as archive:
        assert archive.testzip() is None
        for name in ['manifest.json', 'plugin.js']:
            assert archive.read(name) == (plugin / name).read_bytes(), name
    for name in ['install_ble.py', 'requirements-ble.txt']:
        assert (RELEASE / name).read_bytes() == (ROOT / 'tools/atom65' / name).read_bytes(), name
    for path in [ROOT / 'README.md', *list((ROOT / 'docs/atom65').glob('*.md')), ROOT / '3d_files/atom65/README.md', ROOT / 'integrations/decaid/README.md']:
        for link in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            if re.match(r'^[a-zA-Z]+:', link) or link.startswith('#'):
                continue
            target = unquote(link.split('#')[0])
            assert (path.parent / target).exists(), f'{path.relative_to(ROOT)}: {link}'
    from PIL import Image
    for path in (ROOT / 'docs/atom65/images').glob('*.jpg'):
        exif = Image.open(path).getexif()
        assert set(exif) == {274} and exif[274] == 6, 'Unexpected photo metadata'
    if args.meshes:
        import trimesh
        for path in (ROOT / '3d_files/atom65').rglob('*.stl'):
            mesh = trimesh.load_mesh(path)
            assert mesh.is_watertight and mesh.volume > 0 and len(mesh.split()) == 1, path.name
    print('PASS: release hashes, installed firmware source and latest plugin, CAD manifest, portable updater, local links and photo metadata' + (', five meshes' if args.meshes else ''))


if __name__ == '__main__':
    try:
        main()
    except (AssertionError, KeyError, ValueError, OSError) as error:
        print('FAIL:', error, file=sys.stderr)
        raise
