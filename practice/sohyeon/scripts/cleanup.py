"""Project-scoped cleanup. Plan first, archive it, then apply with fresh checks."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

APP = 'sohyeon-cicd-app'
STATE = Path.home() / '.local/share/sohyeon-cicd/state'
CONFIG = Path('/etc/nginx/conf.d/sohyeon.conf')
CANDIDATE = Path('/etc/nginx/sohyeon.candidate')
LABEL = 'io.sohyeon.project=sohyeon-cicd'
OWNER = 'sohyeon'
RELEASE = re.compile(r'v[0-9]+-[0-9a-f]{12}-[0-9]+')


def docker(*args):
    command = ['docker', '--host', 'unix:///var/run/docker.sock', *args]
    if os.environ.get('SOHYEON_DOCKER_SUDO') == '1':
        # Remote helpers retain the deployment user's HOME and file ownership.
        # Only read operations go through sudo; Ansible performs guarded mutations.
        if not (args[:1] == ('ps',) or args[:2] in (
                ('container', 'inspect'), ('image', 'inspect'), ('image', 'ls'))):
            raise ValueError('Privileged helper permits Docker inspection only')
        command = ['sudo', '-n', '--', *command]
    return subprocess.check_output(command, text=True).strip()


def validate_archive(path, release):
    """Reject archives that would import foreign tags or unowned images."""
    with tarfile.open(safe_path(path), 'r:*') as archive:
        def read_json(name):
            member = archive.getmember(name)
            if not member.isfile() or member.size > 1024 * 1024:
                raise ValueError('Invalid image archive metadata')
            with archive.extractfile(member) as source:
                return json.load(source)
        manifest = read_json('manifest.json')
        if len(manifest) != 1 or manifest[0].get('RepoTags') != [f'{APP}:{release}']:
            raise ValueError('Archive must contain only the assigned project release')
        config = read_json(manifest[0]['Config'])
        labels = config.get('config', {}).get('Labels') or {}
        if (labels.get('io.sohyeon.owner') != OWNER
                or labels.get('io.sohyeon.project') != 'sohyeon-cicd'
                or labels.get('io.sohyeon.release') != release):
            raise ValueError('Archive image ownership or release is unconfirmed')


def inspect(kind, ref):
    return json.loads(docker(kind, 'inspect', ref))[0]


def write_json(path, data):
    path = Path(path)
    safe_path(path)
    temporary = path.with_name(path.name + '.tmp')
    safe_path(temporary)
    with temporary.open('w') as out:
        os.chmod(temporary, 0o600)
        json.dump(data, out, indent=2)
        out.write('\n')
    temporary.replace(path)


def safe_path(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError(f'Refusing symlink: {path}')
    return path


def file_entry(path):
    path = safe_path(path)
    stat = path.stat()
    if not path.is_file():
        raise ValueError(f'Not a regular file: {path}')
    return {'kind': 'file', 'path': str(path),
            'identity': [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns]}


def owned(metadata):
    labels = metadata.get('Config', {}).get('Labels') or {}
    return (labels.get('io.sohyeon.project') == 'sohyeon-cicd'
            and labels.get('io.sohyeon.owner') == OWNER)


def allowed_file(scope, path):
    path = safe_path(path)
    if scope == 'app':
        return (path.parent == STATE.parent / 'tmp' and path.name.startswith(APP + '-')
                and path.name.endswith('.tar')
                and RELEASE.fullmatch(path.name[len(APP) + 1:-4]) is not None)
    return scope == 'lb' and (path == CANDIDATE or (
        path.parent == CONFIG.parent
        and re.fullmatch(r'sohyeon\.conf\.\d+\.\d{4}-\d{2}-\d{2}@\d{2}:\d{2}:\d{2}~', path.name)))


def record_file(scope, path):
    """Called immediately after this deployment creates a disposable file."""
    if not allowed_file(scope, path):
        raise ValueError('Not an allowed project temporary file')
    registry = safe_path(STATE / f'owned-files-{scope}.json')
    entries = json.loads(registry.read_text()) if registry.exists() else {}
    entry = file_entry(path)
    entries[entry['path']] = entry
    # Drop records for already removed files without touching any unrecorded paths.
    entries = {name: value for name, value in entries.items() if Path(name).exists()}
    write_json(registry, entries)


def recorded_files(scope):
    registry = safe_path(STATE / f'owned-files-{scope}.json')
    if not registry.exists():
        return []
    result = []
    for name, entry in json.loads(registry.read_text()).items():
        if not allowed_file(scope, name):
            raise ValueError('Unexpected path in ownership registry')
        if Path(name).exists() and file_entry(name) == entry:
            result.append(entry)
    return result


def remove_test(name, release):
    """Post-build cleanup may stop only this release's explicitly owned test container."""
    if not re.fullmatch(r'sohyeon-cicd-test-[0-9]+', name):
        raise ValueError('Invalid test container name')
    ids = docker('ps', '-aq', '--filter', f'name=^/{name}$').split()
    for cid in ids:
        current = inspect('container', cid)
        labels = current.get('Config', {}).get('Labels') or {}
        if (not owned(current) or labels.get('io.sohyeon.role') != 'test'
                or labels.get('io.sohyeon.release') != release):
            raise ValueError('Refusing to remove a test container with unconfirmed ownership')
        docker('container', 'rm', '--force', cid)


def containers():
    ids = docker('ps', '-aq').split()
    return [inspect('container', cid) for cid in ids]


def snapshot(release):
    """Keep the exact previous image and private run configuration before replacement."""
    path = STATE / 'previous-container.json'
    safe_path(path)
    if path.exists() and json.loads(path.read_text())['target'] == release:
        return  # Retrying this release must not overwrite its recovery reference.
    current = inspect('container', APP)
    if not current['State']['Running']:
        raise ValueError('Previous container is not running')
    write_json(path, {'target': release, 'container': current})


def protected_images(scope, release, protection_dir):
    protected = {inspect('image', f'{APP}:{release}')['Id']}
    if scope == 'app':
        state = json.loads(safe_path(STATE / 'previous-container.json').read_text())
        if state['target'] != release:
            raise ValueError('Recovery snapshot is for another release')
        current = inspect('container', APP)
        if not current['State']['Running'] or current['Image'] not in protected:
            raise ValueError('Current application does not match the successful deployment')
        previous = state['container']['Image']
        inspect('image', previous)  # A missing recovery image must stop cleanup.
        protected.add(previous)
    elif scope == 'agent':
        files = list(Path(protection_dir).glob('cleanup-plan-sohyeon-app*.json'))
        if len(files) != 3:
            raise ValueError('Expected protection plans from all three application servers')
        for path in files:
            plan = json.loads(path.read_text())
            if plan['release'] != release or plan['scope'] != 'app':
                raise ValueError('Invalid application protection plan')
            protected.update(plan['protected_images'])
    protected.update(c['Image'] for c in containers())  # Include stopped and other-project containers.
    return protected


def make_plan(scope, release, protection_dir=None):
    candidates, protected = [], set()
    if scope in ('app', 'agent'):
        protected = protected_images(scope, release, protection_dir)
        if scope == 'agent':
            for container in containers():
                labels = container['Config'].get('Labels') or {}
                if (owned(container)
                        and labels.get('io.sohyeon.role') == 'test'
                        and re.fullmatch(r'/sohyeon-cicd-test-[0-9]+', container['Name'])
                        and container['State']['Status'] in ('exited', 'created')):
                    candidates.append({'kind': 'container', 'id': container['Id']})
        # Repository name alone is not ownership proof; older unlabelled images stay.
        tags = docker('image', 'ls', '--format', '{{.Repository}}:{{.Tag}}', APP).splitlines()
        for tag in sorted(set(tags)):
            if tag.split(':')[0] != APP or tag.endswith(':<none>'):
                continue
            meta = inspect('image', tag)
            if owned(meta) and meta['Id'] not in protected:
                candidates.append({'kind': 'image', 'ref': tag, 'id': meta['Id']})
        # Only project-labelled dangling images are owned; shared build cache is never pruned.
        ids = docker('image', 'ls', '-q', '--no-trunc', '--filter', 'dangling=true',
                     '--filter', f'label={LABEL}').splitlines()
        for iid in sorted(set(ids)):
            if owned(inspect('image', iid)) and iid not in protected:
                candidates.append({'kind': 'image', 'ref': iid, 'id': iid})
    if scope == 'lb':
        previous = safe_path(STATE / 'nginx.previous.conf')
        if not previous.is_file():
            raise ValueError('Missing known-good Nginx backup')
        if ' down' in re.sub(r'(?m)#.*$', '', CONFIG.read_text()):
            raise ValueError('An upstream is still excluded')
    if scope in ('app', 'lb'):
        candidates.extend(recorded_files(scope))
    return {'scope': scope, 'release': release, 'protected_images': sorted(protected),
            'candidates': sorted(candidates, key=lambda item: (item['kind'], item.get('ref', item.get('path', item.get('id')))))}


def validate_item(plan, item, protection_dir):
    """Recheck ownership, identity and live references immediately before deletion."""
    if item['kind'] == 'container':
        current = inspect('container', item['id'])
        labels = current.get('Config', {}).get('Labels') or {}
        if (not owned(current) or labels.get('io.sohyeon.role') != 'test'
                or not re.fullmatch(r'/sohyeon-cicd-test-[0-9]+', current['Name'])
                or current['State']['Status'] not in ('exited', 'created')):
            raise ValueError('Test container ownership or state changed')
    elif item['kind'] == 'image':
        metadata = inspect('image', item['ref'])
        if not owned(metadata) or metadata['Id'] != item['id']:
            raise ValueError('Image ownership or reference changed')
        if item['ref'].startswith('sha256:') and metadata.get('RepoTags'):
            raise ValueError('Dangling image acquired tags; ownership must be reviewed')
        if item['id'] in protected_images(plan['scope'], plan['release'], protection_dir):
            raise ValueError('Image became protected')
    elif item['kind'] == 'file':
        if file_entry(item['path']) != item:
            raise ValueError('File changed since planning')
    else:
        raise ValueError('Unsupported cleanup resource')


def begin_result(plan):
    return {'scope': plan['scope'], 'release': plan['release'], 'deleted': [], 'failed': [],
            'protected_images': plan['protected_images']}


def validate_plan(plan, protection_dir):
    if make_plan(plan['scope'], plan['release'], protection_dir) != plan:
        raise ValueError('Resources changed since the archived plan; cleanup stopped')


def apply(plan, protection_dir, result_path):
    # Agent backend. Remote deletion is performed by Ansible Galaxy modules instead.
    result = begin_result(plan)
    try:
        validate_plan(plan, protection_dir)
        for item in plan['candidates']:
            validate_item(plan, item, protection_dir)
            if item['kind'] == 'container':
                docker('container', 'rm', item['id'])
            elif item['kind'] == 'image':
                docker('image', 'rm', '--no-prune', item['ref'])
            else:
                Path(item['path']).unlink()
            result['deleted'].append(item)
    except Exception as error:
        result['failed'].append(str(error))
        raise
    finally:
        write_json(result_path, result)


def module_action(action, plan, args):
    """Guard and journal the remote Ansible module execution without deleting resources."""
    result = begin_result(plan) if action == 'validate-plan' else json.loads(Path(args.result).read_text())
    try:
        if action == 'validate-plan':
            validate_plan(plan, args.protection_dir)
        elif action == 'record-failure':
            result['failed'].append(args.error)
        else:
            item = plan['candidates'][args.index]
            if action == 'check-item':
                validate_item(plan, item, args.protection_dir)
            elif action == 'record-deleted':
                result['deleted'].append(item)
    except Exception as error:
        result['failed'].append(str(error))
        raise
    finally:
        write_json(args.result, result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['snapshot', 'record', 'validate-archive', 'test-cleanup', 'plan', 'apply',
                                      'validate-plan', 'check-item', 'record-deleted', 'record-failure'])
    parser.add_argument('--scope', choices=['app', 'agent', 'lb'], default='app')
    parser.add_argument('--release', required=True)
    parser.add_argument('--index', type=int)
    parser.add_argument('--error', default='Ansible cleanup task failed')
    parser.add_argument('--path')
    parser.add_argument('--container')
    parser.add_argument('--plan')
    parser.add_argument('--result')
    parser.add_argument('--protection-dir')
    args = parser.parse_args()
    if not RELEASE.fullmatch(args.release):
        parser.error('Invalid release ID')
    if args.action == 'validate-archive':
        validate_archive(args.path, args.release)
    elif args.action == 'snapshot':
        snapshot(args.release)
    elif args.action == 'record':
        record_file(args.scope, args.path)
    elif args.action == 'test-cleanup':
        remove_test(args.container, args.release)
    elif args.action == 'plan':
        write_json(args.plan, make_plan(args.scope, args.release, args.protection_dir))
    else:
        plan = json.loads(safe_path(args.plan).read_text())
        if (plan['scope'], plan['release']) != (args.scope, args.release):
            raise ValueError('Plan scope/release mismatch')
        if args.action == 'apply':
            apply(plan, args.protection_dir, args.result)
        else:
            module_action(args.action, plan, args)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Cleanup failed: {error}', file=sys.stderr)
        sys.exit(1)
