from dataclasses import replace
from datetime import datetime
from importlib import import_module
from math import exp, isfinite, log
import unittest

from research.intraday_lab.domain import Tick

model = import_module("research.18_volatility_forecasts.model")
BASE = int(datetime.fromisoformat("2026-08-19T10:00:00+05:30").timestamp()*1_000_000)
MINUTE = BASE//model.MINUTE_US


def bar(index,close=100,valid=True):
    start=(MINUTE+index)*model.MINUTE_US
    return model.MinuteBar(MINUTE+index,1,close,start,start+55_000_000,valid)


def tick(second,price=100,**changes):
    return replace(Tick(BASE+second*1_000_000,1,"TEST",price-.01,price+.01,price,
                        100,10000,10000,0,True,True),**changes)


class VarianceTests(unittest.TestCase):
    def test_ewma_recursion(self):
        self.assertAlmostEqual(model.ewma_update(2,4,.94),2.12)

    def test_invalid_variances_and_decays_rejected(self):
        for inputs in ((-1,2,.94),(1,-1,.94),(1,2,1),(1,2,float('nan'))):
            with self.assertRaises(ValueError):
                model.ewma_update(*inputs)

    def test_loss_formula_and_zero_target_are_finite(self):
        mse,qlike=model.losses(2,4)
        self.assertEqual(mse,4)
        self.assertAlmostEqual(qlike,log(2)+2)
        self.assertTrue(all(isfinite(x) for x in model.losses(0,0)))

    def test_all_models_seed_same_history_then_diverge_by_recursion(self):
        state=model.VarianceModel()
        for i in range(31):
            state.on_bar(bar(i,100*exp(i*.001)))
        values=state.pending.values
        for value in values.values():
            self.assertAlmostEqual(value,1e-6)
        state.on_bar(bar(31,100*exp(.030)))
        self.assertAlmostEqual(state.pending.values['ewma_094'],.94e-6)
        self.assertAlmostEqual(state.pending.values['ewma_097'],.97e-6)
        self.assertAlmostEqual(state.pending.values['rolling30'],29/30*1e-6)

    def test_future_change_does_not_change_prior_forecast(self):
        state=model.VarianceModel()
        for i in range(31):
            self.assertIsNone(state.on_bar(bar(i,100*exp(i*.001))))
        frozen=dict(state.pending.values)
        at_us=state.pending.at_us
        result=state.on_bar(bar(31,120))
        self.assertEqual(result['forecasts'],frozen)
        self.assertEqual(result['forecast_us'],at_us)
        self.assertLess(result['training_last_received_us'],result['forecast_us'])
        self.assertEqual(result['forecast_us'],bar(31).minute*model.MINUTE_US)

    def test_invalid_bar_resets_pending_and_full_warmup(self):
        state=model.VarianceModel()
        for i in range(31):state.on_bar(bar(i))
        self.assertIsNotNone(state.pending)
        self.assertIsNone(state.on_bar(bar(31,0,False)))
        self.assertIsNone(state.pending)
        for i in range(32,62):
            self.assertIsNone(state.on_bar(bar(i)))

    def test_missing_minute_resets_history(self):
        state=model.VarianceModel()
        for i in range(31):state.on_bar(bar(i))
        self.assertIsNone(state.on_bar(bar(33)))
        self.assertEqual(len(state.squares),0)

    def test_flat_returns_floor_forecasts_preserve_zero_outcomes(self):
        state=model.VarianceModel()
        for i in range(31):state.on_bar(bar(i))
        self.assertTrue(all(x==model.FLOOR for x in state.pending.values.values()))
        result=state.on_bar(bar(31))
        self.assertEqual(result['squared_log_return'],0)

    def test_completed_bar_excludes_next_minute_first_tick(self):
        ticks=[tick(i,100) for i in range(0,60,5)]+[tick(60,110)]
        bars,quality=model.completed_minutes(ticks)
        self.assertEqual(len(bars),1)
        self.assertEqual(bars[0].close,100)
        self.assertTrue(bars[0].valid)
        self.assertEqual(quality['unclosed_final_minutes'],1)

    def test_gap_and_unknown_freshness_invalidate_minute(self):
        for ticks in ([tick(0),tick(40),tick(55),tick(60)],
                      [tick(i,data_fresh=None if i==10 else True) for i in range(0,61,5)]):
            bars,_=model.completed_minutes(ticks)
            self.assertFalse(bars[0].valid)

    def test_late_first_and_missing_last_receipt_invalidate_bar(self):
        for times in ([20,30,40,50,60],[0,5,10,15,60]):
            bars,_=model.completed_minutes([tick(i) for i in times])
            self.assertFalse(bars[0].valid)

    def test_timestamp_order_and_instrument_identity_rejected(self):
        with self.assertRaises(ValueError):model.completed_minutes([tick(10),tick(5)])
        state=model.VarianceModel();state.on_bar(bar(0))
        with self.assertRaises(ValueError):state.on_bar(replace(bar(1),security_id=2))


if __name__ == '__main__':
    unittest.main()
