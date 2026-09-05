import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from verify_derived import verify, ENTRY, CARTRIDGE, SOURCE, INSERTION


class DerivedRelease(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); self.root = Path(temp.name)
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.PIPE).decode().strip()
        self.git = git; git('init', '-q'); git('config', 'user.name', 'Fixture'); git('config', 'user.email', 'fixture@example.invalid'); git('config', 'core.autocrlf', 'false')
        self.basegen = '202609051858'; self.gen = '202609051959'
        self.original = {ENTRY: b'<html><body><script src="app.js"></script><a href="../sibling/index.html">Sibling</a></body></html>',
                         ENTRY.replace('index.html', 'app.js'): b'const calculation = 120;'}
        files = []
        for path, raw in self.original.items():
            self.write(f'releases/{self.basegen}/' + path, raw); files.append(self.record(path, raw))
        manifest = {'schema': 'globalgrid.original-runtime.v1', 'generation': self.basegen, 'files': files}
        raw = self.encode(manifest); self.write(f'releases/{self.basegen}/manifest.json', raw)
        self.write('latest.json', self.encode({'generation': self.basegen, 'manifest': f'releases/{self.basegen}/manifest.json', 'manifestSha256': self.sha(raw)}))
        git('add', '.'); git('commit', '-qm', 'baseline'); self.commit = git('rev-parse', 'HEAD')
        self.release = self.root / 'releases' / self.gen
        cartridge = b'(() => { const guarded = true; })();'; self.write(SOURCE, cartridge)
        derived = {**self.original, CARTRIDGE: cartridge}; derived[ENTRY] = derived[ENTRY].replace(b'</body>', INSERTION.encode() + b'</body>')
        self.manifest = {'schema': 'globalgrid.derived-runtime.v1', 'generation': self.gen,
            'baseline': {'commit': self.commit, 'generation': self.basegen, 'manifestSha256': self.sha(raw)},
            'applications': [{'id': 'module-layout', 'entry': ENTRY}],
            'composition': {'entry': ENTRY, 'insertBefore': '</body>', 'insertion': INSERTION},
            'cartridge': {'path': CARTRIDGE, 'sourcePath': SOURCE},
            'crossOwnerNavigation': [{'path': 'solar-bess-topology-v7/sibling/index.html', 'repository': 'Ventusltd/sibling', 'commit': 'b' * 40, 'manifestSha256': 'c' * 64}],
            'files': []}
        for path, contents in derived.items():
            self.write(f'releases/{self.gen}/' + path, contents)
            role = 'composed-entry' if path == ENTRY else 'cartridge' if path == CARTRIDGE else 'original'
            self.manifest['files'].append({**self.record(path, contents), 'role': role})
        self.pin()

    @staticmethod
    def encode(value): return (json.dumps(value, indent=2) + '\n').encode()
    @staticmethod
    def sha(raw): return hashlib.sha256(raw).hexdigest()
    def write(self, path, raw):
        p = self.root / path; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(raw)
    def record(self, path, raw): return {'path': path, 'bytes': len(raw), 'sha256': self.sha(raw)}
    def pin(self):
        raw = self.encode(self.manifest); self.write(f'releases/{self.gen}/manifest.json', raw)
        self.write('derived-latest.json', self.encode({'generation': self.gen, 'manifest': f'releases/{self.gen}/manifest.json', 'manifestSha256': self.sha(raw)}))
    def replace(self, path, raw):
        self.write(f'releases/{self.gen}/' + path, raw)
        next(x for x in self.manifest['files'] if x['path'] == path).update(self.record(path, raw)); self.pin()
    def refused(self, text):
        result = verify(self.root); self.assertFalse(result['ok'], result); self.assertIn(text, ' '.join(result['errors']))

    def test_valid_release_passes_despite_dirty_unrelated_baseline_worktree(self):
        self.write(f'releases/{self.basegen}/' + ENTRY, b'dirty working copy')
        result = verify(self.root); self.assertTrue(result['ok'], result); self.assertEqual(result['files'], 3)

    def test_formula_change_fails_even_with_rehashed_manifest(self):
        self.replace(ENTRY.replace('index.html', 'app.js'), b'const calculation = 121;'); self.refused('original runtime changed')

    def test_extra_entry_change_fails_even_with_rehashed_manifest(self):
        self.replace(ENTRY, (self.release / ENTRY).read_bytes().replace(b'Sibling', b'Changed')); self.refused('single insertion')

    def test_cartridge_must_match_maintained_source(self):
        self.replace(CARTRIDGE, b'const other = 1;'); self.refused('maintained cartridge differs')

    def test_unknown_role_traversal_duplicate_and_missing_member_fail(self):
        original = copy.deepcopy(self.manifest)
        for mutate, message in [
            (lambda m: m['files'][0].update(role='unverified'), 'unknown file role'),
            (lambda m: m['files'][0].update(path='../outside'), 'path traversal'),
            (lambda m: m['files'].append(copy.deepcopy(m['files'][0])), 'duplicate'),
            (lambda m: m['files'].pop(), 'closure')]:
            self.manifest = copy.deepcopy(original); mutate(self.manifest); self.pin(); self.refused(message)

    def test_missing_or_unpinned_sibling_fails(self):
        original = copy.deepcopy(self.manifest)
        self.manifest['crossOwnerNavigation'] = []; self.pin(); self.refused('missing or unmanifested')
        self.manifest = original; self.manifest['crossOwnerNavigation'][0]['commit'] = 'main'; self.pin(); self.refused('unbound cross-owner')

    def test_github_repository_url_is_supported_but_other_host_is_not(self):
        pin = self.manifest['crossOwnerNavigation'][0]
        pin['repository'] = 'https://github.com/Ventusltd/sibling'; self.pin()
        self.assertTrue(verify(self.root)['ok'])
        pin['repository'] = 'https://wrong.example/Ventusltd/sibling'; self.pin(); self.refused('unbound cross-owner')

    def test_baseline_and_pointer_hashes_are_checked(self):
        self.manifest['baseline']['manifestSha256'] = '0' * 64; self.pin(); self.refused('baseline manifest hash')
        (self.release / 'manifest.json').write_bytes(b'{}'); self.refused('derived manifest pointer hash')

    def test_syntax_is_checked_even_when_cartridge_matches_source(self):
        raw = b'function broken('; self.write(SOURCE, raw); self.replace(CARTRIDGE, raw); self.refused('JavaScript parse failure')


if __name__ == '__main__':
    unittest.main()
