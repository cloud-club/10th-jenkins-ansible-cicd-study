"""Remove only this build's explicitly recorded temporary directory."""
import json
import os
from pathlib import Path
import re
import shutil


def cleanup(path, job, build):
    if not path:
        return
    root = Path(path)
    if not re.fullmatch(r'/tmp/sohyeon-ci\.[A-Za-z0-9]{8}', path):
        raise ValueError('Unexpected build temporary directory')
    if root.is_symlink():
        raise ValueError('Refusing a symlink temporary directory')
    if not root.exists():
        return
    marker = root / 'build-info.json'
    if not job or not build or marker.is_symlink():
        raise ValueError('Missing or invalid build identity')
    expected = dict(owner='sohyeon', project='sohyeon-cicd', job=job, build=build)
    if json.loads(marker.read_text()) != expected:
        raise ValueError('Temporary directory belongs to another build')
    shutil.rmtree(root)


if __name__ == '__main__':
    cleanup(os.environ.get('BUILD_TMPDIR'), os.environ.get('JOB_NAME'),
            os.environ.get('BUILD_NUMBER'))
