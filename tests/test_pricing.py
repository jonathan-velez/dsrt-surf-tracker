"""Offline price-baseline regression tests; production state is never touched."""
import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('pricing', Path(__file__).resolve().parents[1]/'pricing/server.py')
pricing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pricing)

class PricingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        self.now = dt.datetime(2026, 10, 10, 12, tzinfo=pricing.TZ)
        self.rows = json.loads((Path(__file__).parent/'fixtures/sessions.json').read_text())
        self.base = self.collect()

    def collect(self, rows=None, now=None):
        return pricing.collect(now=now or self.now, fetch=lambda month: copy.deepcopy(self.rows if rows is None else rows), state=self.state)

    def test_expiry_last_group_and_new_sessions_are_silent(self):
        self.assertEqual(self.collect(self.rows[:2]), self.base)
        new = copy.deepcopy(self.rows[0]); new['_id'] = 'new'; new['currentPrice'] = 99
        self.assertEqual(self.collect(self.rows[:2]+[new]), self.base)
        self.assertEqual(self.collect(), self.base)

    def test_increase_decrease_and_updated_baseline(self):
        rows = copy.deepcopy(self.rows); rows[0]['currentPrice'] = 200
        first = self.collect(rows)
        self.assertIn('price 220 -> 200', first)
        self.assertEqual(self.collect(rows), first)
        rows[0]['currentPrice'] = 210
        second = self.collect(rows)
        self.assertIn('price 200 -> 210', second)
        self.assertIn('Price change #2', second)
        self.assertEqual(self.collect(rows), second)
        self.assertIn('price 210 -> 220', self.collect())

    def test_missing_session_reappears_with_price_change(self):
        self.collect(self.rows[1:])
        rows = copy.deepcopy(self.rows); rows[0]['currentPrice'] = 205
        self.assertIn('price 220 -> 205', self.collect(rows))

    def test_expired_session_is_not_compared(self):
        rows = copy.deepcopy(self.rows); rows[0]['currentPrice'] = 1
        self.assertEqual(self.collect(rows, self.now+dt.timedelta(days=2)), self.base)
        stored = json.loads((self.state/'latest.json').read_text())
        self.assertEqual(set(stored['sessions']), {'fixture-next-monday'})

    def test_nonprice_edits_are_silent(self):
        rows = copy.deepcopy(self.rows)
        for row in rows:
            row.update(sessiontype='Renamed', direction='Right', available=0, sessionlimit=99, blocked=True)
            row['currentPrice'] = 220.0
        self.assertEqual(self.collect(rows[::-1]), self.base)
        for row in rows:
            del row['currentPrice']
        self.assertEqual(self.collect(rows), self.base)

    def test_private_and_bay_excluded(self):
        rows = copy.deepcopy(self.rows)
        for key, value in [('privateSession', True), ('waveClass', 'bay')]:
            new = copy.deepcopy(rows[0]); new.update(_id='excluded', currentPrice=999); new[key] = value
            self.assertEqual(self.collect(rows+[new]), self.base)

    def test_failures_preserve_baseline_and_recovery(self):
        path = self.state/'latest.json'
        baseline = path.read_bytes()
        invalid = [[], {}, [{'waveClass': 'reef'}]]
        for field, value in [('currentPrice', 'bad'), ('currentPrice', -1), ('currentPrice', float('nan')), ('currentPrice', True), ('dateid', '2026-02-30'), ('starttime', '8:00'), ('_id', ''), ('privateSession', 'true')]:
            rows = copy.deepcopy(self.rows); rows[0][field] = value; invalid.append(rows)
        for rows in invalid:
            with self.subTest(rows=rows):
                with self.assertRaises((ValueError, TypeError)):
                    self.collect(rows)
                self.assertEqual(path.read_bytes(), baseline)
        def unavailable(month):
            raise OSError('network unavailable')
        with self.assertRaises(OSError):
            pricing.collect(self.now, unavailable, self.state)
        self.assertEqual(path.read_bytes(), baseline)
        self.assertEqual(self.collect(), self.base)

    def test_conflicting_duplicates_fail(self):
        duplicate = copy.deepcopy(self.rows[0]); duplicate['currentPrice'] = 100
        with self.assertRaises(ValueError):
            self.collect(self.rows+[duplicate])
        self.assertEqual(self.collect(self.rows+[self.rows[0]]), self.base)

    def test_restart_reads_durable_baseline_and_payload(self):
        rows = copy.deepcopy(self.rows); rows[1]['currentPrice'] = 225
        report = self.collect(rows)
        reloaded = importlib.util.module_from_spec(spec); spec.loader.exec_module(reloaded)
        self.assertEqual(reloaded.collect(self.now, lambda month: rows, self.state), report)
        self.assertIn('price 225 -> 220', self.collect())

    def test_month_year_rollover_is_silent_and_fetches_current_month(self):
        for now in [dt.datetime(2026,11,1,tzinfo=pricing.TZ), dt.datetime(2027,1,1,tzinfo=pricing.TZ)]:
            rows = copy.deepcopy(self.rows[:1]); rows[0].update(_id=now.strftime('%Y-%m'), dateid=now.strftime('%Y-%m-02'))
            months = []
            def fetch(month):
                months.append(month); return rows
            self.assertEqual(pricing.collect(now, fetch, self.state), self.base)
            self.assertEqual(months, [now.strftime('%Y-%m')])

if __name__ == '__main__':
    unittest.main()
