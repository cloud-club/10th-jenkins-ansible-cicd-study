"""Pure validation for the personal release archive. Never log raw inspect data."""
from copy import deepcopy
import re

HOSTS = ('app1', 'app2', 'app3')
APP_ENV = ('APP_VERSION', 'GIT_SHA', 'RELEASE_ID', 'APP_INSTANCE')

def require(condition, message):
    if not condition:
        raise ValueError(message)

def validate_release_id(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', value)
            is not None and value not in ('.', '..'), 'Invalid release or operation identifier')
    return value

def metadata(value):
    require(isinstance(value, dict) and set(value) == {'version', 'gitSha', 'release'}, 'Invalid build metadata')
    require(all(isinstance(v, str) and v and '\x00' not in v for v in value.values()), 'Invalid build metadata')
    validate_release_id(value['release'])
    return value

def runtime(value, host, build):
    require(isinstance(value, dict) and set(value) == {'entrypoint', 'command', 'restart_policy', 'environment'},
            'Invalid runtime fields')
    require(value['restart_policy'] == 'unless-stopped', 'Unsupported restart policy')
    require(isinstance(value['entrypoint'], list) and value['entrypoint'], 'Unsupported entrypoint')
    require(isinstance(value['command'], list), 'Unsupported command')
    require(all(isinstance(x, str) and '\x00' not in x for x in value['entrypoint'] + value['command']),
            'Unsupported command arguments')
    require(value['environment'] == {'APP_VERSION': build['version'], 'GIT_SHA': build['gitSha'],
            'RELEASE_ID': build['release'], 'APP_INSTANCE': host}, 'Runtime metadata mismatch')
    return value

def validate_release_manifest(value):
    require(isinstance(value, dict) and value.get('schema_version') == 1, 'Unsupported release manifest')
    required = {'schema_version', 'release_id', 'metadata', 'image', 'runtime', 'nginx_sha256',
                'origin', 'created_at', 'bootstrap'}
    require(set(value) == required, 'Invalid release manifest fields')
    release = validate_release_id(value['release_id'])
    build = metadata(value['metadata'])
    require(build['release'] == release, 'Release metadata mismatch')
    image = value['image']
    require(isinstance(image, dict) and set(image) == {'id', 'archive_sha256', 'archive_name'}, 'Invalid image record')
    require(isinstance(image['id'], str) and re.fullmatch(r'sha256:[0-9a-f]{64}', image['id']) is not None,
            'Invalid image ID')
    for checksum in (image['archive_sha256'], value['nginx_sha256']):
        require(isinstance(checksum, str) and re.fullmatch(r'[0-9a-f]{64}', checksum) is not None, 'Invalid SHA-256')
    require(image['archive_name'] == 'image.tar', 'Unsupported archive name')
    require(isinstance(value['runtime'], dict) and set(value['runtime']) == set(HOSTS), 'Expected exactly three hosts')
    for host in HOSTS:
        runtime(value['runtime'][host], host, build)
    origin = value['origin']
    require(isinstance(origin, dict) and set(origin) == {'job', 'build', 'git_sha'}, 'Invalid origin')
    require(origin['git_sha'] == build['gitSha'], 'Origin SHA mismatch')
    require(origin['job'] is None or isinstance(origin['job'], str), 'Invalid origin Job')
    require(origin['build'] is None or isinstance(origin['build'], (str, int)), 'Invalid origin build')
    require(isinstance(value['created_at'], str) and bool(value['created_at']), 'Missing archive timestamp')
    require(type(value['bootstrap']) is bool, 'Invalid bootstrap flag')
    return deepcopy(value)

def validate_release_state(value, allow_legacy=False):
    require(isinstance(value, dict) and value.get('active_slot') in ('a', 'b'), 'Invalid active slot')
    build = metadata(value.get('metadata'))
    if 'schema_version' not in value:
        require(allow_legacy and set(value) == {'active_slot', 'metadata'}, 'Legacy state requires migration')
        return deepcopy(value)
    require(value['schema_version'] == 1 and set(value) == {'schema_version', 'active_slot', 'metadata',
        'release_id', 'previous_release', 'operation_id', 'operation_type'}, 'Invalid deployment state')
    require(validate_release_id(value['release_id']) == build['release'], 'State release mismatch')
    if value['previous_release'] is not None:
        validate_release_id(value['previous_release'])
        require(value['previous_release'] != value['release_id'], 'Previous release must differ')
    require(value['operation_type'] in ('DEPLOY', 'ROLLBACK', 'BOOTSTRAP'), 'Invalid operation type')
    if value['operation_id'] is not None:
        validate_release_id(value['operation_id'])
    require((value['operation_type'] == 'BOOTSTRAP') == (value['operation_id'] is None), 'Invalid operation identity')
    require(value['operation_type'] == 'DEPLOY' or value['previous_release'] is None, 'Invalid rollback target')
    return deepcopy(value)

def env_dict(entries):
    require(isinstance(entries, list), 'Missing image environment')
    result = {}
    for entry in entries:
        require(isinstance(entry, str) and '=' in entry, 'Invalid environment entry')
        name, value = entry.split('=', 1)
        require(name not in result, 'Duplicate environment entry')
        result[name] = value
    return result

def capture_release_runtime(container, image, host, slot):
    require(host in HOSTS and slot in ('a', 'b'), 'Invalid personal container scope')
    require(container.get('Image') == image.get('Id'), 'Container image differs from inspected image')
    require(container.get('Name') in ('/taehyeon-app-' + slot,
        '/taehyeon-app' if slot == 'a' else '/taehyeon-app-' + slot), 'Invalid personal container name')
    config, defaults, options = container.get('Config', {}), image.get('Config', {}), container.get('HostConfig', {})
    require(not container.get('Mounts'), 'Volumes are not supported')
    require(options.get('PortBindings') == {'8080/tcp': [{'HostIp': '', 'HostPort': str({'a':20001, 'b':21001}[slot])}]}
        or options.get('PortBindings') == {'8080/tcp': [{'HostIp': '0.0.0.0', 'HostPort': str({'a':20001, 'b':21001}[slot])}]},
        'Unsupported published ports')
    require(options.get('RestartPolicy') == {'Name': 'unless-stopped', 'MaximumRetryCount': 0}, 'Unsupported restart policy')
    require(options.get('NetworkMode') in ('bridge', 'default'), 'Unsupported network mode')
    require(set(container.get('NetworkSettings', {}).get('Networks', {})) == {'bridge'}, 'Unsupported network attachments')
    for field in ('Privileged', 'ReadonlyRootfs', 'PublishAllPorts', 'AutoRemove', 'Binds', 'Mounts', 'VolumesFrom',
                  'CapAdd', 'CapDrop', 'Devices', 'DeviceRequests', 'SecurityOpt', 'ExtraHosts', 'Dns', 'DnsSearch',
                  'DnsOptions', 'Links', 'Tmpfs', 'PidMode', 'UTSMode', 'UsernsMode', 'Memory', 'MemorySwap',
                  'MemoryReservation', 'NanoCpus', 'CpuShares', 'CpuQuota', 'CpusetCpus', 'CpusetMems',
                  'Ulimits', 'Sysctls', 'GroupAdd', 'DeviceCgroupRules'):
        require(not options.get(field), 'Unsupported container option: ' + field)
    require(options.get('IpcMode', 'private') == 'private', 'Unsupported IPC mode')
    require(not options.get('LogConfig', {}).get('Config'), 'Custom logging options are unsupported')
    for field in ('Entrypoint', 'Cmd', 'User', 'WorkingDir', 'Labels', 'Healthcheck', 'StopSignal'):
        require(config.get(field) == defaults.get(field), 'Container changes image defaults: ' + field)
    actual_env, image_env = env_dict(config.get('Env')), env_dict(defaults.get('Env'))
    require({k:v for k,v in actual_env.items() if k not in APP_ENV} ==
            {k:v for k,v in image_env.items() if k not in APP_ENV}, 'Unsupported environment overrides')
    require(all(k in actual_env for k in APP_ENV), 'Missing application environment')
    build = {'version': actual_env['APP_VERSION'], 'gitSha': actual_env['GIT_SHA'], 'release': actual_env['RELEASE_ID']}
    metadata(build)
    value = {'entrypoint': config.get('Entrypoint') or [], 'command': config.get('Cmd') or [],
        'restart_policy': 'unless-stopped', 'environment': {k:actual_env[k] for k in APP_ENV}}
    return deepcopy(runtime(value, host, build))

class FilterModule:
    def filters(self):
        return {name: globals()[name] for name in ('validate_release_id', 'validate_release_manifest',
                                                  'validate_release_state', 'capture_release_runtime')}
