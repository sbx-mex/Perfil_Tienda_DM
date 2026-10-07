from __future__ import annotations
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from cleanup_obsolete import ALLOWED, candidates, clean


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'; self.root.mkdir()
        self.manifest = Path('scripts/obsolete-files.json')
        self.write(str(self.manifest), json.dumps({'obsoleteFiles':sorted(ALLOWED)}))
        self.write('index.html', '<script src="app.js"></script><link href="styles.css" rel="stylesheet">')
        self.write('app.js', "fetch('data/dashboard.json')")
        self.write('styles.css', 'body{color:green}')

    def write(self, name, text):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text, encoding='utf-8'); return path

    def test_audit_never_deletes_and_apply_is_idempotent(self):
        old = self.write('data.js', 'old')
        report = clean(self.root, self.manifest)
        self.assertEqual(report['remaining'], ['data.js']); self.assertTrue(old.exists())
        report = clean(self.root, self.manifest, True)
        self.assertEqual(report['removed'], ['data.js']); self.assertFalse(old.exists())
        self.assertEqual(clean(self.root, self.manifest, True)['removed'], [])

    def test_current_assets_engines_and_exports_are_preserved(self):
        paths = ['assets/icon.svg','assets/icon-192.png','exports.js','data/exports.json','data/engines/Query.xlsx','data/engines/mix/Base_Mix_01.csv']
        for path in paths: self.write(path, 'current' if not path.endswith('.js') else 'const current=1;')
        for name in ALLOWED: self.write(name, 'old')
        report = clean(self.root, self.manifest, True)
        self.assertEqual(set(report['removed']), ALLOWED)
        for path in paths: self.assertTrue((self.root / path).exists(),path)

    def test_any_html_reference_blocks_all_deletions(self):
        self.write('index.html', '<script src="data.js?v=2"></script>')
        for name in ['data.js','style.css']: self.write(name, 'old')
        with self.assertRaisesRegex(ValueError, 'index.html -> data.js'): clean(self.root, self.manifest, True)
        self.assertTrue((self.root / 'data.js').exists()); self.assertTrue((self.root / 'style.css').exists())

    def test_referenced_missing_file_is_still_reported_as_broken(self):
        self.write('app.js', "const CORE=['./data.js'];")
        with self.assertRaisesRegex(ValueError, 'data.js'): clean(self.root, self.manifest)

    def test_css_imports_are_followed_and_subdirectory_icons_are_not_legacy(self):
        self.write('index.html', '<link href="assets/new.css" rel="stylesheet"><img src="assets/icon.svg">')
        self.write('assets/icon.svg','current'); self.write('icon.svg','old')
        self.write('assets/new.css', '@import "../style.css";')
        with self.assertRaisesRegex(ValueError, 'assets/new.css -> style.css'): clean(self.root, self.manifest, True)
        self.write('assets/new.css', 'body {background:url("icon.svg")}')
        self.assertEqual(clean(self.root, self.manifest, True)['removed'], ['icon.svg'])
        self.assertTrue((self.root / 'assets/icon.svg').exists())

    def test_manifest_and_nested_scripts_are_dependencies(self):
        self.write('manifest.webmanifest', json.dumps({'icons':[{'src':'icon-192.png'}]}))
        with self.assertRaisesRegex(ValueError, 'manifest.webmanifest -> icon-192.png'): clean(self.root, self.manifest)
        self.write('manifest.webmanifest', '{}'); self.write('app.js', "load('assets/helper.js')")
        self.write('assets/helper.js', "fetch('../Store_Master_Audit.csv')")
        with self.assertRaisesRegex(ValueError, 'Store_Master_Audit.csv'): clean(self.root, self.manifest)

    def test_python_paths_distinguish_mix_manifest_from_legacy_root_manifest(self):
        self.write('scripts/build_data.py', 'mix_manifest = engines / "mix" / "manifest.json"')
        self.assertEqual(clean(self.root, self.manifest)['references'], [])
        self.write('scripts/build_data.py', 'source = engines / "Base_Mix.csv"')
        with self.assertRaisesRegex(ValueError, 'data/engines/Base_Mix.csv'): clean(self.root, self.manifest)

    def test_artifact_file_list_is_a_runtime_dependency(self):
        self.write('scripts/stage_site.py', 'FILES=("data.js",)\nASSETS=("icon.svg",)\nDATA=("exports.json",)')
        with self.assertRaisesRegex(ValueError, 'scripts/stage_site.py -> data.js'): clean(self.root, self.manifest)

    def test_unapproved_absolute_duplicate_and_parent_paths_are_blocked(self):
        for names in [['app.js'],['../data.js'],['/data.js'],['data.js','data.js'],['data\\engines\\Base_Mix.csv']]:
            self.write(str(self.manifest),json.dumps({'obsoleteFiles':names}))
            with self.subTest(names=names), self.assertRaises(ValueError): candidates(self.root,self.manifest)

    def test_directory_and_symlinks_cannot_be_deleted(self):
        (self.root / 'data.js').mkdir()
        with self.assertRaises(ValueError): candidates(self.root,self.manifest)
        (self.root / 'data.js').rmdir()
        external = Path(self.temp.name) / 'external'; external.write_text('keep')
        (self.root / 'data.js').symlink_to(external)
        with self.assertRaises(ValueError): candidates(self.root,self.manifest)
        self.assertEqual(external.read_text(),'keep')

    def test_symlink_parent_cannot_redirect_engine_cleanup(self):
        outside = Path(self.temp.name) / 'engines'; outside.mkdir(); (outside/'Base_Mix.csv').write_text('keep')
        (self.root/'data').mkdir(); (self.root/'data/engines').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError): candidates(self.root,self.manifest)
        self.assertTrue((outside/'Base_Mix.csv').exists())

    def test_failed_second_removal_restores_the_first(self):
        self.write('data.js','a'); self.write('style.css','b'); replace=os.replace
        def fail(source,target):
            if Path(source)==self.root/'style.css': raise OSError('injected')
            return replace(source,target)
        with patch('cleanup_obsolete.os.replace',side_effect=fail), self.assertRaises(OSError): clean(self.root,self.manifest,True)
        self.assertEqual((self.root/'data.js').read_text(),'a'); self.assertEqual((self.root/'style.css').read_text(),'b')

    def test_report_is_atomic_and_cannot_overwrite_project_files(self):
        self.write('data.js','old'); output=Path(self.temp.name)/'report.json'
        report=clean(self.root,self.manifest,True,output)
        self.assertEqual(json.loads(output.read_text()),report)
        self.write('data.js','old')
        with self.assertRaises(ValueError): clean(self.root,self.manifest,True,self.root/'index.html')
        self.assertTrue((self.root/'data.js').exists())
        with patch('cleanup_obsolete.write_report',side_effect=OSError('injected')), self.assertRaises(OSError): clean(self.root,self.manifest,True,output)
        self.assertEqual((self.root/'data.js').read_text(),'old')

    def test_real_repository_has_no_legacy_dependency(self):
        report=clean(ROOT,Path('scripts/obsolete-files.json'))
        self.assertEqual(report['references'],[])
        self.assertIn('exports.js',report['checkedSources'])
        self.assertIn('scripts/build_exports.py',report['checkedSources'])

if __name__=='__main__': unittest.main()
