import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('availability',Path(__file__).parents[1]/'availability/server.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
NOW=dt.datetime(2026,10,11,22,tzinfo=m.TZ)
RAW={'_id':'a','dateid':'2026-10-20','starttime':'10:00','sessiontype':'Turns','direction':'Left','waveClass':'reef','audience':'public','sessionlimit':10,'available':8,'effectiveMax':10,'effectiveAvailable':8,'incart':0,'blocked':False,'bookingMode':'bookable'}

def snapshot(raw):
    return {'captured_at':NOW.isoformat(),'months':{'2026-10':[raw]},'sessions':m.normalize({'2026-10':[raw]},NOW)}

class AvailabilityTests(unittest.TestCase):
    def test_decrease_and_capacity_exclusion(self):
        old=snapshot(RAW); changed=dict(RAW,available=5,effectiveAvailable=5)
        self.assertIn('Possible net booked spots: 3',m.report(old,snapshot(changed),NOW))
        changed.update(sessionlimit=12,effectiveMax=12)
        self.assertIn('Possible net booked spots: 0',m.report(old,snapshot(changed),NOW))
    def test_cart_bay_exclusions(self):
        for extra in ({'incart':1},{'waveClass':'bay'},{'blocked':True}):
            changed=dict(RAW,available=5,effectiveAvailable=5,**extra)
            self.assertIn('Possible net booked spots: 0',m.report(snapshot(RAW),snapshot(changed),NOW))
    def test_overlap_conflict(self):
        self.assertEqual(1,len(m.normalize({'a':[RAW],'b':[RAW]},NOW)))
        with self.assertRaises(ValueError):
            m.normalize({'a':[RAW],'b':[dict(RAW,available=7)]},NOW)
    def test_expiration_not_booking(self):
        old=snapshot(RAW); new=snapshot(dict(RAW,_id='b',dateid='2026-10-22'))
        text=m.report(old,new,dt.datetime(2026,10,21,22,tzinfo=m.TZ))
        self.assertIn('expired sessions: 1',text)
        self.assertNotIn('REMOVED/MISSING',text)
        self.assertIn('Possible net booked spots: 0',text)
    def test_collection_cache_gaps_and_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder); calls=[]
            def fetch(month):
                calls.append(month)
                return [RAW] if month=='2026-10' else []
            body=m.collect(NOW,fetch,state)
            self.assertEqual(13,len(calls))
            self.assertIn('2027-10',calls)
            self.assertEqual(body,m.collect(NOW+dt.timedelta(minutes=5),fetch,state))
            self.assertEqual(13,len(calls))
            prior=(state/'latest.json').read_bytes()
            def fail(month): raise ValueError('upstream failure')
            with self.assertRaises(ValueError): m.collect(NOW+dt.timedelta(days=1),fail,state)
            self.assertEqual(prior,(state/'latest.json').read_bytes())
    def test_malformed_empty_preserves_baseline(self):
        with self.assertRaises(ValueError): m.normalize({'a':[]},NOW)
        with self.assertRaises(ValueError): m.normalize({'a':[dict(RAW,available=None)]},NOW)

if __name__=='__main__': unittest.main()
