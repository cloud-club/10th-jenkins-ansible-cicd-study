"""Hand-written release and Docker boundary fixtures; no production builders."""
from copy import deepcopy

IMAGE_ID = 'sha256:' + '1' * 64
META = {'version': '41', 'gitSha': 'oldsha', 'release': 'build-41-oldsha'}

def image():
    return {'Id': IMAGE_ID, 'Config': {'Env': ['PATH=/usr/bin', 'APP_VERSION=41',
        'GIT_SHA=oldsha', 'RELEASE_ID=build-41-oldsha'],
        'Entrypoint': ['java', '-jar', '/app/app.jar'], 'Cmd': None,
        'User': '', 'WorkingDir': '/app', 'Labels': None}}

def container(host='app1', slot='a'):
    config = deepcopy(image()['Config'])
    config['Env'].append('APP_INSTANCE=' + host)
    return {'Image': IMAGE_ID, 'Name': '/taehyeon-app-' + slot,
        'Config': config, 'Mounts': [], 'State': {'Running': True},
        'HostConfig': {'PortBindings': {'8080/tcp': [{'HostIp': '',
            'HostPort': str({'a': 20001, 'b': 21001}[slot])}]},
            'RestartPolicy': {'Name': 'unless-stopped', 'MaximumRetryCount': 0},
            'Privileged': False, 'NetworkMode': 'bridge'},
        'NetworkSettings': {'Networks': {'bridge': {}}}}

def manifest():
    return {'schema_version': 1, 'release_id': 'build-41-oldsha', 'metadata': dict(META),
        'image': {'id': IMAGE_ID, 'archive_sha256': '2' * 64, 'archive_name': 'image.tar'},
        'runtime': {host: {'entrypoint': ['java', '-jar', '/app/app.jar'], 'command': [],
            'restart_policy': 'unless-stopped', 'environment': {
                'APP_VERSION': '41', 'GIT_SHA': 'oldsha',
                'RELEASE_ID': 'build-41-oldsha', 'APP_INSTANCE': host}}
            for host in ('app1', 'app2', 'app3')},
        'nginx_sha256': '3' * 64, 'origin': {'job': None, 'build': None, 'git_sha': 'oldsha'},
        'created_at': '2026-10-19T00:00:00Z', 'bootstrap': True}

def state():
    return {'schema_version': 1, 'active_slot': 'a', 'metadata': dict(META),
        'release_id': 'build-41-oldsha', 'previous_release': None,
        'operation_id': None, 'operation_type': 'BOOTSTRAP'}
