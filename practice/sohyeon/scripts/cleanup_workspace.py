"""Remove only numbered artifact directories whose archive succeeded in this job."""
import json
import os
from pathlib import Path
import re
import shutil

from cleanup import safe_path


def cleanup(root, job):
    if not job:
        raise ValueError('Jenkins job identity is required')
    root = safe_path(root)
    if not root.is_dir():
        return
    for directory in root.iterdir():
        if not re.fullmatch(r'[0-9]+', directory.name):
            continue
        safe_path(directory)
        marker = safe_path(directory / '.archived')
        if directory.is_dir() and marker.is_file():
            try:
                owner = json.loads(marker.read_text())
            except (ValueError, OSError):
                continue
            if owner != {'owner': 'sohyeon', 'project': 'sohyeon-cicd', 'job': job}:
                continue
            # Do not traverse an unexpected linked path in an artifact tree.
            for path in directory.rglob('*'):
                safe_path(path)
            shutil.rmtree(directory)


if __name__ == '__main__':
    cleanup(Path('.artifacts'), os.environ.get('JOB_NAME'))
