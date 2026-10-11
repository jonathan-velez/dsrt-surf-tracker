"""Disposable, offline test harness; no Python code is used by the monitor."""
import copy
import sys
sys.path.insert(0, "/app")
import json
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import requests
import jq
import arrow
from unittest.mock import patch
from changedetectionio.jinja2_custom import render
from apprise import Apprise

ROOT = Path('/work')
BASE = 'http://127.0.0.1:5000/api/v1'
url_template = json.loads((ROOT / 'config/watch.json').read_text())['url']
for instant, month in [('2026-10-31T23:59:59-07:00', '2026-10'), ('2026-11-01T00:00:00-07:00', '2026-11'), ('2027-01-01T00:00:00-08:00', '2027-01')]:
    with patch('arrow.now', return_value=arrow.get(instant)):
        assert render(url_template) == f'https://ep.dsrtsurf.com/api/sessions/with/{month}?upcoming=true'
print('PASS date templates: month and year rollover', flush=True)
for notification_url in ['ntfy://your-unguessable-topic', 'ntfys://ntfy.example.com/your-topic']:
    assert Apprise().add(notification_url)
print('PASS ntfy URL parsing (no delivery attempted)', flush=True)
for _ in range(60):
    try:
        state = json.loads(Path('/datastore/changedetection.json').read_text())
        client = requests.Session()
        client.headers['x-api-key'] = state['settings']['application']['api_access_token']
        if client.get(BASE + '/watch', timeout=2).ok:
            break
    except (OSError, ValueError, requests.RequestException):
        pass
    time.sleep(1)
else:
    raise RuntimeError('changedetection startup timed out')

def api(method, path, **kwargs):
    response = client.request(method, BASE + path, timeout=10, **kwargs)
    response.raise_for_status()
    return response.json() if response.content else None

# Only disposable default watches are removed.
for uid in api('GET', '/watch'):
    api('DELETE', '/watch/' + uid)
fixture = json.loads((ROOT / 'tests/fixtures/sessions.json').read_text())
body, status = json.dumps(fixture).encode(), 200
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass
server = HTTPServer(('127.0.0.1', 8088), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
expression = ' '.join(line for line in (ROOT / 'filters/sessions.jq').read_text().splitlines() if not line.startswith('#'))
watch = json.loads((ROOT / 'config/watch.json').read_text())
watch.update(url='http://127.0.0.1:8088/sessions', include_filters=['jq:' + expression], paused=False)
uid = api('POST', '/watch', json=watch)['uuid']
path = '/watch/' + uid
api('GET', path + '?recheck=true')

def fetch(data, expected, name, code=200):
    global body, status
    before = api('GET', path)
    previous_history = api('GET', path + '/history')
    # Snapshot keys and last_checked use whole seconds.
    time.sleep(1.1)
    body = data if isinstance(data, bytes) else json.dumps(data).encode()
    status = code
    api('GET', path + '?recheck=true')
    for _ in range(600):
        after = api('GET', path)
        if after['check_count'] > before['check_count']:
            break
        time.sleep(.2)
    else:
        raise AssertionError(name + ': check timed out')
    history = api('GET', path + '/history')
    if expected == 'error':
        assert after['last_error'], (name, after)
        assert history == previous_history, (name, 'error overwrote baseline')
    else:
        assert not after['last_error'], (name, after['last_error'])
        assert len(history) == len(previous_history) + (expected == 'change'), (name, history, previous_history)
    assert after['notification_alert_count'] == 0, name
    print('PASS integration:', name, flush=True)

for _ in range(600):
    initial = api('GET', path)
    if initial['history_n'] == 1:
        break
    time.sleep(.2)
else:
    raise AssertionError(('initial baseline failed', initial))
print('PASS integration: initial baseline', flush=True)
fetch(fixture, 'same', 'unchanged repeat')
for name, expression, expected in [
    ('availability', 'map(.available=0 | .effectiveAvailable=0 | .incart=9)', 'same'),
    ('capacity', 'map(.sessionlimit=99 | .effectiveMax=99)', 'same'),
    ('direction availability', '.[1].available=0', 'same'),
    ('ordering', 'reverse', 'same'),
    ('session expires but tier remains', 'del(.[3])', 'same'),
    ('blocked sold-out retained', 'map(.blocked=true | .available=0)', 'same'),
    ('fallback numeric formatting', 'map(del(.currentPrice))', 'same'),
    ('private excluded', '. + [.[0] | .privateSession=true | .currentPrice=12500]', 'same'),
    ('weekday decrease', '.[2].currentPrice-=10', 'change'),
    ('weekend decrease', '.[0].currentPrice-=10', 'change'),
    ('increase', '.[0].currentPrice+=10', 'change'),
    ('new discounted tier', '. + [.[0] | .currentPrice-=20]', 'change'),
    ('rename', 'map(.sessiontype="Renamed")', 'change'),
    ('new type', '. + [.[0] | .sessiontype="New type"]', 'change'),
    ('different direction price', '.[1].currentPrice+=15', 'change'),
    ('last tier expires', 'del(.[2:4])', 'change'),
]:
    data = jq.compile(expression).input_value(copy.deepcopy(fixture)).first()
    fetch(data, expected, name)
    if expected == 'change':
        fetch(fixture, 'change', name + ' restore')
for name, data, code in [
    ('invalid JSON', b'{invalid', 200),
    ('empty response', [], 200),
    ('wrong shape', {}, 200),
    ('invalid effective price', jq.compile('map(.currentPrice="bad")').input_value(fixture).first(), 200),
    ('API unavailable 503', b'service unavailable', 503),
]:
    fetch(data, 'error', name, code)
fetch(fixture, 'same', 'recovery preserves baseline')
# Connection refusal as well as HTTP errors must preserve history.
api('PUT', path, json={'url':'http://127.0.0.1:8089/unavailable'})
fetch(fixture, 'error', 'connection refused')
api('PUT', path, json={'url':'http://127.0.0.1:8088/sessions'})
fetch(fixture, 'same', 'connection recovery')
print('All HTTP/jq/history integration tests passed; notifications stayed muted.', flush=True)
