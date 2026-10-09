import importlib
import unittest
from dataclasses import replace

from research.intraday_lab.domain import Tick, PolicyConfig

s = importlib.import_module("research.16_relative_volume.strategy")


def tape(n=180):
    ticks = [Tick(600_000_000 + i * 1_000_000, 1, "A", 99.99 + i * .001,
                  100.01 + i * .001, 100, 100, 10000, 10000, 0, True, True) for i in range(n)]
    return ticks, {(t.security_id,t.at_us): i*100 for i,t in enumerate(ticks)}


class VolumeTests(unittest.TestCase):
    def test_completed_bar_needs_next_minute_quote(self):
        ticks, volume = tape()
        prefix,_ = s.completed_bars(ticks[:120],volume,PolicyConfig())
        full,_ = s.completed_bars(ticks,volume,PolicyConfig())
        self.assertEqual(prefix, [])
        self.assertEqual(len(full),1)
        self.assertEqual(full[0].available_us, ticks[120].at_us)
        self.assertEqual(full[0].volume,6000)

    def test_future_prefix_does_not_rewrite_bar(self):
        ticks,volume=tape(240)
        prefix,_=s.completed_bars(ticks[:181],volume,PolicyConfig())
        volume[(1,ticks[-1].at_us)] = 90000000
        full,_=s.completed_bars(ticks,volume,PolicyConfig())
        self.assertEqual(prefix,full[:len(prefix)])

    def test_reset_rejects_negative_volume(self):
        ticks,volume=tape()
        volume[(1,ticks[100].at_us)] = 1
        bars,counts=s.completed_bars(ticks,volume,PolicyConfig())
        self.assertEqual(bars,[])
        self.assertEqual(counts['cumulative_resets'],1)

    def test_baseline_requires_three_sessions_and_policy_copies_it(self):
        bar=s.VolumeBar(1,10,720000000,100,10)
        self.assertEqual(s.fit_baseline({'a':[bar],'b':[bar]}),{})
        baseline=s.fit_baseline({'a':[bar],'b':[bar],'c':[bar]})
        p=s.RelativeVolumePolicy(PolicyConfig(),[bar],baseline,'continuation')
        baseline[(1,bar.time_of_day)]=999999
        self.assertEqual(p.baseline[(1,bar.time_of_day)],100)

    def test_unknown_quote_and_missing_volume_reject_minutes(self):
        ticks,volume=tape()
        ticks[100]=replace(ticks[100],data_fresh=None)
        self.assertEqual(s.completed_bars(ticks,volume,PolicyConfig())[0],[])
        ticks,volume=tape()
        volume.pop((1,ticks[100].at_us))
        self.assertEqual(s.completed_bars(ticks,volume,PolicyConfig())[0],[])


if __name__=='__main__':
    unittest.main()
