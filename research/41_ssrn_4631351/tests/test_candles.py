from importlib import import_module

import numpy as np
import pandas as pd
import pytest

model = import_module("research.41_ssrn_4631351.candle_run")


def candles(close: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"date": ["2025-01-02"] * len(close), "open": close,
                         "high": np.array(close) + 0.1, "low": np.array(close) - 0.1,
                         "close": close, "volume": [100] * len(close)})


@pytest.mark.parametrize("confirmed", [False, True])
def test_vwap_decisions_are_invariant_to_future_candles(confirmed: bool) -> None:
    original = candles([100 + i * 0.04 for i in range(12)])
    changed = original.copy()
    changed.loc[8:, ["open", "high", "low", "close"]] *= 10
    changed.loc[8:, "volume"] *= 100
    assert np.array_equal(model.candle_directions(original, confirmed=confirmed)[:8],
                          model.candle_directions(changed, confirmed=confirmed)[:8])


def test_execution_uses_next_open_and_reconciles_fees() -> None:
    day = candles([99, 100, 101])
    result, trades = model.simulate_day(day, np.array([1, 0, 0]), 100_000, 0)
    assert len(trades) == 1
    trade = trades[0]
    assert trade["entry_index"] == 1
    assert trade["exit_index"] == 2
    assert trade["entry_price"] == 100
    assert trade["exit_price"] == 101
    assert trade["gross_pnl"] == trade["quantity"]
    assert result.net_pnl == pytest.approx(result.gross_pnl - result.fees)
    assert result.ending_equity == pytest.approx(result.starting_equity + result.net_pnl)


def test_adverse_slippage_lowers_flat_price_result() -> None:
    day = candles([100, 100, 100])
    zero, _ = model.simulate_day(day, np.array([-1, -1, -1]), 100_000, 0)
    adverse, trades = model.simulate_day(day, np.array([-1, -1, -1]), 100_000, 5)
    assert adverse.net_pnl < zero.net_pnl < 0
    assert trades[-1]["exit_reason"] == "session_close"
    assert trades[-1]["entry_price"] < trades[-1]["exit_price"]


def test_zero_volume_produces_no_direction_before_first_volume() -> None:
    day = candles([100, 101, 102])
    day.loc[:1, "volume"] = 0
    assert list(model.candle_directions(day, confirmed=False)[:2]) == [0, 0]
