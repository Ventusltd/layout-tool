"""Verify original bytes, JavaScript syntax and local HTML dependency paths."""
import argparse
import hashlib
import json
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class Resources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
        self.inline = []
        self.script = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        for key in ('src', 'href'):
            if values.get(key):
                self.urls.append((tag, values[key]))
        if tag == 'script' and not values.get('src') and values.get('type', '') in ('', 'text/javascript', 'module'):
            self.script = []

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.script is not None:
            self.inline.append(''.join(self.script))
            self.script = None


def verify(root, manifest, source=None):
    errors, scripts, resources, cross_owner_links = [], 0, 0, 0
    if manifest.get('schema') != 'globalgrid.original-runtime.v1':
        errors.append('unsupported baseline schema')
    if source:
        # A publication worktree can have advanced; git show still reads exactly the pinned revision.
        exists = subprocess.run(['git', '-C', str(source), 'cat-file', '-e', manifest['origin']['commit'] + '^{commit}'], capture_output=True)
        if exists.returncode:
            errors.append('pinned origin commit missing from source checkout')
    listed = {item['path'] for item in manifest['files']}
    cross_owner = {item['path']: item for item in manifest.get('crossOwnerNavigation', [])}
    for item in manifest['files']:
        path = (root / item['path']).resolve()
        if not path.is_relative_to(root.resolve()):
            errors.append('file escapes immutable release'); continue
        try:
            raw = path.read_bytes()
        except OSError:
            errors.append('missing file: ' + item['path']); continue
        if len(raw) != item['bytes'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
            errors.append('baseline bytes changed: ' + item['path'])
        blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if blob != item['gitBlob']:
            errors.append('original Git blob mismatch: ' + item['path'])
        if source:
            result = subprocess.run(['git', '-C', str(source), 'show', manifest['origin']['commit'] + ':' + item['path']], capture_output=True)
            if result.returncode or result.stdout != raw:
                errors.append('origin revision differs: ' + item['path'])
        chunks = []
        if path.suffix == '.js':
            chunks.append(raw.decode('utf8'))
        if path.suffix == '.html':
            parser = Resources(); parser.feed(raw.decode('utf8')); chunks.extend(parser.inline)
            for tag, url in parser.urls:
                parsed = urlsplit(url)
                if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith('/'):
                    continue
                resources += 1
                resolved = (path.parent / unquote(parsed.path)).resolve()
                relative = resolved.relative_to(root.resolve()).as_posix() if resolved.is_relative_to(root.resolve()) else None
                if tag == 'a' and relative in cross_owner:
                    import re
                    dependency = cross_owner[relative]
                    if not re.fullmatch('[0-9a-f]{40}', dependency.get('commit', '')) or not re.fullmatch('[0-9a-f]{64}', dependency.get('manifestSha256', '')):
                        errors.append('unbound cross-owner navigation: ' + relative)
                    cross_owner_links += 1
                    continue
                if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
                    errors.append('missing relative HTML resource: ' + item['path'] + ' -> ' + url)
                elif resolved.relative_to(root.resolve()).as_posix() not in listed:
                    errors.append('unmanifested relative HTML resource: ' + url)
        for chunk in chunks:
            if not chunk.strip(): continue
            with tempfile.TemporaryDirectory() as temp:
                script = Path(temp) / 'parse.js'; script.write_text(chunk, encoding='utf8')
                result = subprocess.run(['node', '--check', str(script)], capture_output=True, text=True)
                scripts += 1
                if result.returncode: errors.append('JavaScript parse failure: ' + item['path'] + ': ' + result.stderr[-500:])
    for app in manifest['applications']:
        if app['entry'] not in listed: errors.append('application entry is not manifested: ' + app['id'])
    return {'ok': not errors, 'generation': manifest['generation'], 'origin': manifest['origin'],
            'files': len(listed), 'javascriptParses': scripts, 'relativeHtmlResources': resources, 'declaredCrossOwnerLinks': cross_owner_links,
            'errors': errors, 'scope': 'Byte preservation, syntax and declared local dependencies; no browser behavior or engineering acceptance claim.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--source', type=Path)
    parser.add_argument('--expected-origin')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    latest = json.loads((args.root / 'latest.json').read_bytes())
    manifest_path = args.root / latest['manifest']; raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != latest['manifestSha256']:
        raise SystemExit('latest pointer manifest digest mismatch')
    manifest = json.loads(raw)
    if args.expected_origin and manifest['origin']['commit'] != args.expected_origin:
        raise SystemExit('baseline origin differs from required source revision')
    if manifest['generation'] != latest['generation']:
        raise SystemExit('latest pointer generation mismatch')
    result = verify(manifest_path.parent, manifest, args.source)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print(json.dumps(result))
    raise SystemExit(0 if result['ok'] else 1)


if __name__ == '__main__':
    main()
