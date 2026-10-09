import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location("indicators_study", Path(__file__).with_name("study.py"))
study = importlib.util.module_from_spec(spec); spec.loader.exec_module(study)


def synthetic():
    times = pd.date_range("2026-08-20T03:46Z", periods=80, freq="min")
    close = np.arange(80, dtype=float) + 24000
    return pd.DataFrame({"decision_at": times, "date": "2026-08-20", "segment": 0, "security_id": "1",
        "close": close, "high": close + .1, "low": close - .1, "complete_minute": True,
        "minutes_from_open": np.arange(1,81), "ret_5_bps": 3.0})


def test_future_changes_preserve_past_signals():
    frame = synthetic(); before = study.build_signals(frame)
    frame.loc[frame.index >= 50, ["close", "high", "low"]] = 1
    after = study.build_signals(frame)
    pd.testing.assert_frame_equal(before.loc[:49, list(study.RULES)], after.loc[:49, list(study.RULES)])


def test_no_label_crosses_gap_or_restart():
    frame = synthetic(); frame.loc[frame.index >= 40, "segment"] = 1
    result = study.build_signals(frame)
    assert result.loc[35:39, "target_5"].isna().all()
    assert result.loc[40:59, "ema_8_21"].eq(0).all()


def test_missing_opening_minute_disables_opening_range():
    frame = synthetic(); frame.loc[4, "complete_minute"] = False
    assert study.build_signals(frame)["opening_15_breakout"].eq(0).all()


def test_sign_flip_and_holm():
    assert study.sign_flip_pvalue(np.ones(4)) == 1/16
    assert study.sign_flip_pvalue(np.array([1,2])) is None
    assert study.holm([.01,.04,.2,None]) == [.04,.12,.4,None]


def test_rsi_monotonic_and_flat():
    assert study.rsi(pd.Series(np.arange(40))).iloc[-1] == 100
    assert study.rsi(pd.Series([10.]*40)).iloc[-1] == 50


def test_exponential_histories_forget_incomplete_pre_gap_prices():
    original = synthetic()
    original.loc[39, "complete_minute"] = False
    changed = original.copy()
    changed.loc[:38, ["close", "high", "low"]] = 1_000_000.0
    first = study.build_signals(original)
    second = study.build_signals(changed)
    columns = ["ema_8_21", "rsi_14_reversal"]
    pd.testing.assert_frame_equal(first.loc[60:, columns], second.loc[60:, columns])
    assert first.loc[40:59, "ema_8_21"].eq(0).all()


def test_exponential_histories_reset_on_missing_timestamp():
    original = synthetic().drop(index=39)
    changed = original.copy()
    changed.loc[:38, ["close", "high", "low"]] = 1_000_000.0
    first = study.build_signals(original).set_index("decision_at")
    second = study.build_signals(changed).set_index("decision_at")
    after = original.loc[60, "decision_at"]
    pd.testing.assert_frame_equal(first.loc[after:, ["ema_8_21", "rsi_14_reversal"]],
                                  second.loc[after:, ["ema_8_21", "rsi_14_reversal"]])


def test_opening_range_does_not_emit_on_incomplete_current_minute():
    frame = synthetic()
    frame.loc[30, "complete_minute"] = False
    result = study.build_signals(frame)
    assert result.loc[30, "opening_15_breakout"] == 0
    assert result.loc[31, "opening_15_breakout"] == 1
