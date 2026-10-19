"""External Docker boundary double, with inspect/load/run/remove side effects."""
import json
import os
from pathlib import Path
import sys

root = Path(os.environ['FAKE_DOCKER_ROOT'])
state_file = root / 'docker-state.json'
state = json.loads(state_file.read_text())
args = sys.argv[1:]
log = root / 'docker-calls.json'
calls = json.loads(log.read_text()) if log.exists() else []
calls.append(args)
log.write_text(json.dumps(calls))

def finish(value=None, code=0):
    state_file.write_text(json.dumps(state))
    if value is not None: print(json.dumps(value))
    sys.exit(code)

if args[:2] == ['container', 'inspect']:
    value = state['containers'].get(args[2]); finish([value] if value else None, 0 if value else 1)
if args[:2] == ['image', 'inspect']:
    value = state['images'].get(args[2]); finish([value] if value else None, 0 if value else 1)
if args[:1] == ['load']:
    state['images'][state['load_image']['Id']] = state['load_image']; finish()
if args[:2] == ['container', 'rm']:
    state['containers'].pop(args[-1], None); finish()
if args[:1] == ['run']:
    image_id = args[-1]; image = state['images'][image_id]
    name = args[args.index('--name') + 1]
    publish = args[args.index('--publish') + 1].split(':')
    environment = dict(x.split('=', 1) for x in image['Config']['Env'])
    for i, value in enumerate(args):
        if value == '--env':
            k, v = args[i + 1].split('=', 1); environment[k] = v
    config = dict(image['Config'], Env=[k + '=' + v for k,v in environment.items()])
    state['containers'][name] = {'Name': '/' + name, 'Image': image_id, 'Config': config,
        'State': {'Running': True}, 'Mounts': [], 'NetworkSettings': {'Networks': {'bridge': {}}},
        'HostConfig': {'PortBindings': {publish[1] + '/tcp': [{'HostIp': '', 'HostPort': publish[0]}]},
            'RestartPolicy': {'Name': 'unless-stopped', 'MaximumRetryCount': 0}, 'NetworkMode': 'bridge'}}
    finish()
finish(code=2)
