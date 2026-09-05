"""Verify an explicit Module derived release without weakening the original baseline gate."""
import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit
from verify import Resources

PREFIX = 'solar-bess-topology-v7/module-layout/'
ENTRY = PREFIX + 'index.html'
CARTRIDGE = PREFIX + 'draw-readiness.js'
SOURCE = 'src/module-layout/draw-readiness.js'
INSERTION = '<script src="./draw-readiness.js"></script>\n'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def safe(root, name):
    if not isinstance(name, str) or '\\' in name or ':' in name:
        raise ValueError('invalid relative path')
    relative = PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or not relative.parts:
        raise ValueError('path traversal refused: ' + name)
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('path escapes release: ' + name)
    return path


def git_bytes(repo, commit, path):
    return subprocess.check_output(['git', '-C', str(repo), 'show', commit + ':' + path], stderr=subprocess.PIPE)


def verify(repo):
    errors = []
    def require(ok, text):
        if not ok:
            raise ValueError(text)
    try:
        pointer = json.loads((repo / 'derived-latest.json').read_bytes())
        generation = pointer['generation']
        require(bool(re.fullmatch(r'\d{12}', generation)), 'invalid generation')
        require(pointer['manifest'] == f'releases/{generation}/manifest.json', 'pointer path/generation mismatch')
        manifest_path = safe(repo, pointer['manifest'])
        raw_manifest = manifest_path.read_bytes()
        require(digest(raw_manifest) == pointer['manifestSha256'], 'derived manifest pointer hash mismatch')
        m = json.loads(raw_manifest)
        require(m['schema'] == 'globalgrid.derived-runtime.v1' and m['generation'] == generation, 'derived schema/generation mismatch')
        baseline = m['baseline']; commit = baseline['commit']; basegen = baseline['generation']
        require(bool(re.fullmatch('[0-9a-f]{40}', commit)), 'full baseline commit required')
        require(bool(re.fullmatch(r'\d{12}', basegen)), 'baseline generation invalid')
        basepath = f'releases/{basegen}/manifest.json'
        original_raw = git_bytes(repo, commit, basepath)
        require(digest(original_raw) == baseline['manifestSha256'], 'pinned baseline manifest hash mismatch')
        original = json.loads(original_raw)
        require(original['schema'] == 'globalgrid.original-runtime.v1' and original['generation'] == basegen, 'baseline schema/generation mismatch')
        pinned_pointer = json.loads(git_bytes(repo, commit, 'latest.json'))
        require(pinned_pointer['manifest'] == basepath and pinned_pointer['manifestSha256'] == baseline['manifestSha256'] and pinned_pointer['generation'] == basegen, 'baseline pointer mismatch')
        require(m['applications'] == [{'id': 'module-layout', 'entry': ENTRY}], 'derived release must own Module only')
        require(m['composition'] == {'entry': ENTRY, 'insertBefore': '</body>', 'insertion': INSERTION}, 'unexpected entry composition')
        require(m['cartridge'] == {'path': CARTRIDGE, 'sourcePath': SOURCE}, 'unexpected cartridge identity')
        originals = {x['path']: x for x in original['files'] if x['path'].startswith(PREFIX)}
        listed = [x['path'] for x in m['files']]
        require(len(listed) == len(set(listed)), 'duplicate manifested path')
        for name in listed:
            safe(manifest_path.parent, name)
        require(set(listed) == set(originals) | {CARTRIDGE}, 'derived closure differs from baseline Module plus cartridge')
        cross_owner = {x['path']: x for x in m.get('crossOwnerNavigation', [])}
        scripts = resources = 0
        for item in m['files']:
            name = item['path']; role = item['role']; path = safe(manifest_path.parent, name); raw = path.read_bytes()
            require(len(raw) == item['bytes'] and digest(raw) == item['sha256'], 'derived file hash mismatch: ' + name)
            require(role in {'original', 'composed-entry', 'cartridge'}, 'unknown file role: ' + name)
            if name == CARTRIDGE:
                require(role == 'cartridge', 'cartridge role mismatch')
                require(raw == safe(repo, SOURCE).read_bytes(), 'maintained cartridge differs from release')
            else:
                before = git_bytes(repo, commit, f'releases/{basegen}/' + name)
                require(digest(before) == originals[name]['sha256'] and len(before) == originals[name]['bytes'], 'baseline file does not match baseline manifest: ' + name)
                if name == ENTRY:
                    require(role == 'composed-entry', 'entry role mismatch')
                    require(before.count(b'</body>') == 1, 'baseline entry must have one insertion anchor')
                    require(raw == before.replace(b'</body>', INSERTION.encode() + b'</body>', 1), 'entry differs beyond declared single insertion')
                else:
                    require(role == 'original' and raw == before, 'original runtime changed: ' + name)
            chunks = [raw.decode('utf8')] if name.endswith('.js') else []
            if name.endswith('.html'):
                parser = Resources(); parser.feed(raw.decode('utf8')); chunks += parser.inline
                for tag, url in parser.urls:
                    parts = urlsplit(url)
                    if parts.scheme or parts.netloc or not parts.path or parts.path.startswith('/'):
                        continue
                    resolved = (path.parent / unquote(parts.path)).resolve()
                    require(resolved.is_relative_to(manifest_path.parent.resolve()), 'HTML dependency escapes release')
                    relative = resolved.relative_to(manifest_path.parent.resolve()).as_posix(); resources += 1
                    if tag == 'a' and relative in cross_owner:
                        pin = cross_owner[relative]
                        require(bool(re.fullmatch('[0-9a-f]{40}', pin.get('commit', ''))) and bool(re.fullmatch('[0-9a-f]{64}', pin.get('manifestSha256', ''))) and bool(re.fullmatch(r'(?:https://github\.com/)?Ventusltd/[A-Za-z0-9_.-]+', pin.get('repository', ''))), 'unbound cross-owner navigation')
                    else:
                        require(relative in listed and resolved.is_file(), 'missing or unmanifested relative HTML resource: ' + url)
            for chunk in chunks:
                if not chunk.strip():
                    continue
                with tempfile.TemporaryDirectory() as temp:
                    script = Path(temp) / 'parse.js'; script.write_text(chunk, encoding='utf8')
                    result = subprocess.run(['node', '--check', str(script)], capture_output=True)
                    require(result.returncode == 0, 'JavaScript parse failure: ' + name); scripts += 1
        return {'ok': True, 'generation': generation, 'manifestSha256': digest(raw_manifest), 'cartridgeSha256': digest(safe(repo, SOURCE).read_bytes()), 'baseline': baseline, 'files': len(listed), 'javascriptParses': scripts, 'relativeHtmlResources': resources, 'scope': 'Derived byte provenance, declared composition and syntax only; no browser or engineering acceptance.'}
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError, TypeError) as error:
        errors.append(str(error))
        return {'ok': False, 'errors': errors}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(); result = verify(args.root)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print(json.dumps(result)); raise SystemExit(not result['ok'])
