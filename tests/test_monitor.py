import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('monitor', ROOT / 'monitor/run.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
NOW = dt.datetime(2026, 10, 11, 22, tzinfo=m.availability.TZ)


class MonitorTests(unittest.TestCase):
    def test_pricing_change_and_failed_fetch_preserve_baseline(self):
        raw = json.loads((ROOT / 'tests/fixtures/sessions.json').read_text())
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            self.assertFalse(m.pricing(state, NOW, lambda _: raw))
            self.assertEqual([], list((state / 'outbox').glob('*.json')))
            changed = copy.deepcopy(raw)
            changed[0]['currentPrice'] -= 10
            self.assertTrue(m.pricing(state, NOW + dt.timedelta(hours=3), lambda _: changed))
            self.assertEqual(1, len(list((state / 'outbox').glob('*.json'))))
            prior = (state / 'pricing/latest.json').read_bytes()
            with self.assertRaises(subprocess.CalledProcessError):
                m.pricing(state, NOW, lambda _: [])
            self.assertEqual(prior, (state / 'pricing/latest.json').read_bytes())
            with self.assertRaises(OSError):
                m.pricing(state, NOW, lambda _: (_ for _ in ()).throw(OSError()))
            self.assertEqual(prior, (state / 'pricing/latest.json').read_bytes())

    def test_watch_specific_delivery(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            m.enqueue(state, 'pricing', NOW, 'Price changed')
            m.enqueue(state, 'availability', NOW, 'Daily report')
            with patch.dict(m.os.environ, {'PRICING_NTFY_URL': 'https://ntfy.example/test',
                                          'AVAILABILITY_NTFY_URL': ''}):
                with patch.object(m.urllib.request, 'urlopen') as send:
                    m.notify(state)
                    self.assertEqual(1, send.call_count)
            remaining = list((state / 'outbox').glob('*.json'))
            self.assertEqual(1, len(remaining))
            self.assertEqual('availability', m.read(remaining[0])['kind'])

    def test_daily_cache_failure_and_retention(self):
        raw = {'_id': 'a', 'dateid': '2026-11-20', 'starttime': '10:00',
               'sessiontype': 'Turns', 'direction': 'Left', 'waveClass': 'reef',
               'audience': 'public', 'sessionlimit': 10, 'available': 8,
               'incart': 0, 'blocked': False, 'bookingMode': 'bookable'}
        fetch = lambda month: [raw] if month == '2026-11' else []
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            self.assertTrue(m.daily(state, NOW, fetch))
            self.assertFalse(m.daily(state, NOW, fetch))
            prior = (state / 'availability/latest.json').read_bytes()
            with self.assertRaises(ValueError):
                m.daily(state, NOW + dt.timedelta(days=1), lambda _: [])
            self.assertEqual(prior, (state / 'availability/latest.json').read_bytes())
            self.assertTrue(m.daily(state, NOW + dt.timedelta(days=1), fetch))
            self.assertEqual(1, len(list((state / 'outbox').glob('*.json'))))
            m.prune(state, 1, NOW + dt.timedelta(days=2, minutes=1))
            self.assertEqual(['latest.json'], [p.name for p in (state / 'availability').glob('*.json')])

    def test_delivery_failure_keeps_pending_alert(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            m.enqueue(state, 'pricing', NOW, 'Price changed')
            with patch.object(m.urllib.request, 'urlopen', side_effect=OSError):
                with self.assertRaises(OSError):
                    m.notify(state, 'https://ntfy.example/test')
            self.assertEqual(1, len(list((state / 'outbox').glob('*.json'))))

    def test_initial_and_existing_data_branch_restore(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def git(*args, cwd=root):
                return subprocess.run(['git', *args], cwd=cwd, check=True,
                                      text=True, capture_output=True).stdout
            git('init')
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.com')
            m.save(root / 'source.json', {'source': True})
            git('add', 'source.json')
            git('commit', '-m', 'Source')
            git('worktree', 'add', '--detach', '--no-checkout', 'state', 'HEAD')
            state = root / 'state'
            git('switch', '--orphan', 'monitor-data', cwd=state)
            m.save(state / 'pricing/latest.json', {'groups': ['baseline']})
            git('add', '--all', cwd=state)
            git('commit', '-m', 'Data', cwd=state)
            revision = git('rev-parse', 'HEAD', cwd=state).strip()
            git('worktree', 'add', '--detach', 'restored', revision)
            self.assertEqual({'groups': ['baseline']}, m.read(root / 'restored/pricing/latest.json'))
            self.assertFalse((root / 'restored/source.json').exists())


if __name__ == '__main__':
    unittest.main()
