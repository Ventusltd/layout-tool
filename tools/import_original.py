"""Import an immutable original runtime from an explicit GlobalGrid Git revision."""
import argparse
import datetime
import hashlib
import json
import re
import subprocess
from pathlib import Path


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--generation', required=True)
    parser.add_argument('--apps', nargs='+', default=['module-layout', 'cable-geometry-visualiser', 'dc-ac-lv-topology-review'])
    parser.add_argument('--gis-producer-commit', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.commit) or not re.fullmatch(r'\d{12}', args.generation):
        parser.error('full source SHA and 12-digit generation required')
    base = Path(__file__).resolve().parents[1]
    target = base / 'releases' / args.generation
    if target.exists():
        parser.error('immutable generation already exists')
    prefixes = ['solar-bess-topology-v7/' + app for app in args.apps]
    paths = git(args.source, 'ls-tree', '-r', '--name-only', args.commit, '--', *prefixes).decode().splitlines()
    paths = [p for p in paths if Path(p).suffix in {'.html', '.js', '.css'}]
    if not paths:
        parser.error('no original runtime files')
    contents = {p: git(args.source, 'show', args.commit + ':' + p) for p in paths}
    required = set()
    external = set()
    for raw in contents.values():
        text = raw.decode('utf8')
        required.update(re.findall(r'\.\./\.\./(repd_grid_atlasv8/data/[\w.-]+)', text))
        external.update(re.findall(r'https?://[^\s\"\'<>`]+', text))
    for relative in sorted(required):
        contents[relative] = git(args.source, 'show', args.commit + ':' + relative)
    manifest = {
        'schema': 'globalgrid.original-runtime.v1', 'generation': args.generation,
        'createdAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'origin': {'repository': 'Ventusltd/globalgrid2050', 'commit': args.commit},
        'applications': [{'id': app, 'entry': 'solar-bess-topology-v7/' + app + '/index.html'} for app in args.apps],
        'policy': 'Original runtime and required relative data bytes copied unchanged; no generated full-code reports.',
        'rootOriginDependencies': ['/grid_substations.geojson', '/dist/repd_master.json'],
        'externalLiteralUrls': sorted(external),
        'externalScope': 'Literal URL inventory, not exhaustive dynamic dependency closure. External libraries, styles, tiles and geocoding remain external. Root-absolute data requires the GlobalGrid origin or an explicit hosting adapter.',
        'files': []}
    if not re.fullmatch(r'[0-9a-f]{40}', args.gis_producer_commit):
        parser.error('full GIS producer commit required for cross-owner navigation')
    manifest['crossOwnerNavigation'] = [{
        'path': 'solar-bess-topology-v7/gis-sld-financial-sandbox/index.html',
        'repository': 'Ventusltd/gis-sld-sandbox', 'commit': args.gis_producer_commit,
        'entry': 'releases/202609051855/solar-bess-topology-v7/gis-sld-financial-sandbox/index.html',
        'manifestSha256': '90190a0846717b5203305a8c08301fb26ed58e015b992272e0999272091a0916',
        'rule': 'Consumer composes this separately owned sibling route; no GIS implementation copied into layout-tool.'}]
    for relative, raw in sorted(contents.items()):
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        manifest['files'].append({'path': relative, 'bytes': len(raw),
                                  'sha256': hashlib.sha256(raw).hexdigest(),
                                  'gitBlob': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(),
                                  'role': 'relative-data' if relative in required else 'runtime'})
    raw_manifest = (json.dumps(manifest, indent=2) + '\n').encode()
    (target / 'manifest.json').write_bytes(raw_manifest)
    latest = {'schema': 'globalgrid.original-runtime-pointer.v1', 'generation': args.generation,
              'manifest': 'releases/' + args.generation + '/manifest.json',
              'manifestSha256': hashlib.sha256(raw_manifest).hexdigest()}
    (base / 'latest.json').write_text(json.dumps(latest, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'generation': args.generation, 'files': len(contents), 'bytes': sum(map(len, contents.values())), 'manifestSha256': latest['manifestSha256']}))


if __name__ == '__main__':
    main()
