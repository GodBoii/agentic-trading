from dataclasses import replace
from importlib import import_module

import pytest

from research.intraday_lab.domain import PolicyConfig, Side, Tick

strategy = import_module("research.41_ssrn_4631351.strategy")


def observation(second: int, price: float, vwap: float = 100.0) -> Tick:
    return Tick(
        at_us=(1_800_000_000 + second) * 1_000_000,
        security_id=1,
        symbol="TEST",
        bid=price - 0.005,
        ask=price + 0.005,
        last=price,
        vwap=vwap,
        bid_quantity_5=10_000,
        ask_quantity_5=10_000,
        trade_age_seconds=0.0,
        data_fresh=True,
        connection_warm=True,
    )


def test_combination_agreement_and_disagreement() -> None:
    closes = [100, 100.02, 100.04, 100.06, 100.08, 100.10]
    assert strategy.directional_evidence(closes, 99.99, confirmed=True)[0] is Side.LONG
    assert strategy.directional_evidence(closes, 101.0, confirmed=True)[0] is None
    assert strategy.directional_evidence(closes[::-1], 101.0, confirmed=True)[0] is Side.SHORT


def test_path_efficiency_rejects_choppy_price_history() -> None:
    result = strategy.directional_evidence([100, 101, 99, 101, 100.1, 100.2], 99, confirmed=True)
    assert result[0] is None
    assert result[3] == "confirmation_failed"


def test_equal_vwap_is_flat_and_invalid_values_rejected() -> None:
    assert strategy.directional_evidence([100], 100, confirmed=False)[0] is None
    with pytest.raises(ValueError):
        strategy.directional_evidence([float("nan")], 100, confirmed=False)
    with pytest.raises(ValueError):
        strategy.directional_evidence([100], 0, confirmed=False)


def test_signal_uses_completed_bar_and_delays_until_next_minute() -> None:
    policy = strategy.VWAPDirectionPolicy(PolicyConfig(name="vwap_direction"))
    for second in range(60):
        assert policy.on_tick(observation(second, 101.0))[0] is None
    # New minute price is below VWAP. Decision must still use previous close above VWAP.
    signal, reason = policy.on_tick(observation(60, 99.0))
    assert reason == "signal"
    assert signal.side is Side.LONG
    assert signal.at_us == observation(60, 99.0).at_us
    assert signal.reference_midpoint == 99.0


def test_incomplete_bar_and_unusable_tick_do_not_emit_signal() -> None:
    policy = strategy.VWAPDirectionPolicy(PolicyConfig(name="vwap_direction"))
    for second in range(20, 60):
        policy.on_tick(observation(second, 101))
    assert policy.on_tick(observation(60, 101))[0] is None
    stale = replace(observation(61, 101), trade_age_seconds=500)
    assert policy.on_tick(stale)[1] == "unusable_observation"


def test_confirmation_needs_six_completed_closes() -> None:
    result = strategy.directional_evidence([100, 101], 99, confirmed=True)
    assert result[0] is None
    assert result[3] == "warming_confirmation"
