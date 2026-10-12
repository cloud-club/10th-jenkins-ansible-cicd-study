"""Build temporary directories must remain isolated during cleanup."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'cleanup_build_tmp', Path(__file__).resolve().parents[1] / 'scripts/cleanup_build_tmp.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BuildTmpTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(subprocess.check_output(
            ['mktemp', '-d', '/tmp/sohyeon-ci.XXXXXXXX'], text=True).strip())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.marker = self.root / 'build-info.json'
        self.marker.write_text(json.dumps(dict(
            owner='sohyeon', project='sohyeon-cicd', job='sohyeon/test', build='7')))

    def test_matching_build_removed_without_following_child_symlink(self):
        with tempfile.TemporaryDirectory() as other:
            sentinel = Path(other) / 'keep'
            sentinel.write_text('other build')
            (self.root / 'link').symlink_to(other, target_is_directory=True)
            module.cleanup(str(self.root), 'sohyeon/test', '7')
            self.assertFalse(self.root.exists())
            self.assertTrue(sentinel.exists())

    def test_other_job_or_build_preserved(self):
        for job, build in [('other/test', '7'), ('sohyeon/test', '8')]:
            with self.subTest(job=job, build=build), self.assertRaises(ValueError):
                module.cleanup(str(self.root), job, build)
            self.assertTrue(self.marker.exists())

    def test_unscoped_path_and_symlink_rejected(self):
        with self.assertRaises(ValueError):
            module.cleanup('/tmp', 'sohyeon/test', '7')
        self.marker.unlink()
        self.root.rmdir()
        self.root.symlink_to('/tmp', target_is_directory=True)
        try:
            with self.assertRaises(ValueError):
                module.cleanup(str(self.root), 'sohyeon/test', '7')
        finally:
            self.root.unlink()
