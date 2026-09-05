import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('original_verify', Path(__file__).with_name('verify.py'))
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class OriginalRuntime(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'index.html').write_bytes(b'<script src="app.js?v=1"></script>')
        (self.root / 'app.js').write_bytes(b'const original = 1;')
        self.manifest = {'schema': 'globalgrid.original-runtime.v1', 'generation': '202609051855',
                         'origin': {'repository': 'fixture', 'commit': 'a' * 40},
                         'applications': [{'id': 'fixture', 'entry': 'index.html'}], 'files': []}
        for name in ('index.html', 'app.js'):
            raw = (self.root / name).read_bytes()
            self.manifest['files'].append({'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                'gitBlob': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()})

    def test_original_and_query_resource_pass(self):
        result = verify.verify(self.root, self.manifest)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['relativeHtmlResources'], 1)

    def test_changed_formula_bytes_fail(self):
        (self.root / 'app.js').write_bytes(b'const original = 2;')
        result = verify.verify(self.root, self.manifest)
        self.assertTrue(any('baseline bytes changed' in e for e in result['errors']))
        self.assertTrue(any('Git blob mismatch' in e for e in result['errors']))

    def test_missing_dependency_fails(self):
        (self.root / 'app.js').unlink()
        result = verify.verify(self.root, self.manifest)
        self.assertTrue(any('missing relative HTML resource' in e for e in result['errors']))

    def test_invalid_javascript_is_not_excused_by_matching_digest(self):
        raw = b'const broken = ;'
        (self.root / 'app.js').write_bytes(raw)
        self.manifest['files'][1].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
            gitBlob=hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest())
        result = verify.verify(self.root, self.manifest)
        self.assertTrue(any('JavaScript parse failure' in e for e in result['errors']))

    def test_cross_owner_navigation_requires_explicit_pin(self):
        raw = b'<a href="gis/index.html">GIS</a>'
        (self.root / 'index.html').write_bytes(raw)
        self.manifest['files'][0].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
            gitBlob=hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest())
        self.assertFalse(verify.verify(self.root, self.manifest)['ok'])
        self.manifest['crossOwnerNavigation'] = [{'path': 'gis/index.html', 'commit': 'b' * 40, 'manifestSha256': 'c' * 64}]
        result = verify.verify(self.root, self.manifest)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['declaredCrossOwnerLinks'], 1)


if __name__ == '__main__': unittest.main()
