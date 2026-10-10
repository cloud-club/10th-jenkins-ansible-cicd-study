"""Verify pinned Galaxy dependencies and module resolution without contacting Docker."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PINS = {'community.docker': '4.8.1', 'community.library_inventory_filtering_v1': '1.0.0'}
MODULES = ('docker_container_info', 'docker_host_info', 'docker_image_load',
           'docker_image_info', 'docker_container', 'docker_image_remove')


def check():
    for name, version in PINS.items():
        namespace, collection = name.split('.')
        directory = ROOT / '.ansible/collections/ansible_collections' / namespace / collection
        actual = json.loads((directory / 'MANIFEST.json').read_text())['collection_info']['version']
        if actual != version:
            raise RuntimeError(f'{name}: expected {version}, got {actual}')
    result = subprocess.run(['ansible-doc', '--json', *['community.docker.' + name for name in MODULES]],
                            check=True, capture_output=True, text=True)
    docs = json.loads(result.stdout)
    for name in MODULES:
        filename = Path(docs['community.docker.' + name]['doc']['filename']).resolve()
        if not filename.is_relative_to(ROOT / '.ansible/collections'):
            raise RuntimeError(f'{name} resolved outside project-local collection')
    print('Galaxy pins and six community.docker modules verified')


if __name__ == '__main__':
    check()
