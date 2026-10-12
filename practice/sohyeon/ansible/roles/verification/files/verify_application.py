"""Check all HTTP contracts in one remote invocation without changing files."""
import json
import sys
from urllib.request import urlopen


def verify(options):
    def get(path):
        with urlopen(options['url'].rstrip('/') + path, timeout=float(options['timeout'])) as response:
            if response.status != 200:
                raise ValueError(f'{path}: expected HTTP 200')
            return response.read().decode()

    def require(condition, message):
        if not condition:
            raise ValueError(message)

    require(get('/health').strip() == 'OK', 'Health response is not OK')
    content = get('/')
    service = {'content': content}
    try:
        data = json.loads(content)
    except ValueError:
        data = None
    legacy = data is None
    if legacy:
        require(options['bootstrap'] and not options['release'], 'Legacy response requires bootstrap without a target release')
        require(content.strip() == 'Sohyeon Jenkins + Ansible CI/CD', 'Unexpected legacy response')
    else:
        require(isinstance(data, dict), 'Service response must be an object')
        ready = json.loads(get('/ready'))
        require(data.get('ready') is True and ready == data, 'Readiness and service response differ or are not ready')
        require(data.get('server_id') == options['host'], 'Wrong server identity')
        require(data.get('service') == options['app'], 'Wrong service identity')
        require(bool(data.get('release_id')) and bool(data.get('git_revision')), 'Missing release metadata')
        require(not options['release'] or data['release_id'] == options['release'], 'Wrong release')
        service['json'] = data
    version = get('/version')
    require(bool(version.strip()), 'Empty version')
    require(legacy or version.strip() == data.get('version'), 'Version and service response differ')
    require(not options['release'] or version.strip() == options['version'], 'Wrong version')
    return {'service_response': service, 'version_response': {'content': version}, 'legacy_response': legacy}


if __name__ == '__main__':
    try:
        print(json.dumps(verify(json.loads(sys.argv[1]))))
    except Exception as error:
        print(f'Application verification failed: {error}', file=sys.stderr)
        sys.exit(1)
