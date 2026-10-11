"""Portable batch monitor: Python stdlib + jq, filesystem state, optional ntfy."""
import argparse
import datetime as dt
import difflib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('availability', ROOT / 'availability/server.py')
availability = importlib.util.module_from_spec(spec)
spec.loader.exec_module(availability)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    tmp.replace(path)


def read(path):
    return json.loads(path.read_text()) if path.exists() else None


def enqueue(state, kind, now, body):
    key = now.strftime('%Y%m%dT%H%M%S%f%z') + '-' + kind + '-' + uuid.uuid4().hex
    save(state / 'outbox' / (key + '.json'), {'kind': kind, 'body': body})


def destination(kind):
    return os.environ.get('PRICING_NTFY_URL' if kind == 'pricing' else 'AVAILABILITY_NTFY_URL', '')


def pricing(state, now, fetch=availability.fetch_month):
    raw = fetch(now.strftime('%Y-%m'))
    result = subprocess.run(['jq', '-f', str(ROOT / 'filters/sessions.jq')],
                            input=json.dumps(raw), text=True, capture_output=True, check=True)
    groups = json.loads(result.stdout)
    path = state / 'pricing/latest.json'
    previous = read(path)
    current = {'schema_version': 1, 'captured_at': now.isoformat(), 'groups': groups}
    changed = previous is not None and previous['groups'] != groups
    body = 'DSRT published pricing changed (may include schedule changes).\nhttps://book.dsrtsurf.com/app.html#/calendar\n'
    if changed:
        body += ''.join(difflib.unified_diff(
            json.dumps(previous['groups'], indent=2, sort_keys=True).splitlines(True),
            json.dumps(groups, indent=2, sort_keys=True).splitlines(True), fromfile='previous', tofile='current'))
    if previous is None or changed:
        save(state / 'pricing/history' / (now.strftime('%Y%m%dT%H%M%S%f%z') + '.json'),
             dict(current, raw=raw, report=body if changed else 'Initial baseline.'))
    save(path, current)
    if changed:
        enqueue(state, 'pricing', now, body)
    return changed


def daily(state, now, fetch=availability.fetch_month):
    folder = state / 'availability'
    previous = read(folder / 'latest.json')
    body = availability.collect(now, fetch, folder)
    current = read(folder / 'latest.json')
    if previous is None or previous['slot'] != current['slot']:
        # Always retain the report; only enqueue daily delivery after baseline.
        if previous is not None:
            enqueue(state, 'availability', now, body)
        return True
    return False


def prune(state, days, now):
    cutoff = now.timestamp() - days * 86400
    for folder in (state / 'pricing/history', state / 'availability'):
        for path in folder.glob('*.json'):
            if path.name == 'latest.json':
                continue
            # Snapshot capture time travels with the data across hosts/checkouts.
            captured = dt.datetime.fromisoformat(read(path)['captured_at']).timestamp()
            if captured < cutoff:
                path.unlink()


def notify(state, url=None):
    for path in sorted((state / 'outbox').glob('*.json')):
        message = read(path)
        target = destination(message['kind']) if url is None else url
        if not target:
            continue
        if not target.startswith('https://'):
            raise ValueError('Notification destination must use HTTPS')
        # Large availability reports can exceed ntfy message limits. Link to
        # retained history through the configured repository URL instead.
        body = message['body']
        if len(body.encode()) > 3500:
            body = body.split('\n\nCHANGES')[0]
            body = body.encode()[:2800].decode(errors='ignore')
            body += '\nFull report: ' + os.environ.get('REPORT_URL', 'monitor-data branch')
        request = urllib.request.Request(target, data=body.encode(), method='POST',
            headers={'Content-Type': 'text/plain; charset=utf-8'})
        with urllib.request.urlopen(request, timeout=20) as response:
            response.read()
        path.unlink()  # At-least-once delivery; a crash before the next push may repeat.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--mode', choices=('pricing', 'daily', 'all', 'notify'), default='all')
    parser.add_argument('--retention-days', type=int, default=90)
    parser.add_argument('--notification-test', action='store_true')
    args = parser.parse_args()
    if args.retention_days < 1:
        parser.error('retention must be at least one day')
    now = dt.datetime.now(availability.TZ)
    if args.mode == 'notify':
        notify(args.state)
        return
    errors = []
    for kind, task in (('pricing', pricing), ('availability', daily)):
        if args.mode == 'pricing' and kind != 'pricing':
            continue
        if args.mode == 'daily' and kind != 'availability':
            continue
        try:
            task(args.state, now)
            print(kind + ': collected successfully')
        except Exception as exc:
            # Never include credentials/upstream response bodies in logs.
            errors.append(kind + ': ' + type(exc).__name__)
    prune(args.state, args.retention_days, now)
    if args.notification_test and not errors:
        kind = 'availability' if args.mode == 'daily' else 'pricing'
        if not destination(kind):
            raise SystemExit(f'{kind} notification destination is required for the delivery test')
        enqueue(args.state, kind, now,
                f'DSRT GitHub {kind}: notification delivery test. '
                'This is a setup test, not a detected change.')
    # Keep each watch's independent mute setting. Never send a muted backlog.
    for path in (args.state / 'outbox').glob('*.json'):
        if not destination(read(path)['kind']):
            path.unlink()
    save(args.state / 'status.json', {'checked_at': now.isoformat(), 'errors': errors})
    if errors:
        raise SystemExit('\n'.join(errors))


if __name__ == '__main__':
    main()
