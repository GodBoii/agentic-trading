import importlib.util
from pathlib import Path

import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location('transfer_study', Path(__file__).with_name('study.py'))
study = importlib.util.module_from_spec(spec); spec.loader.exec_module(study)
AT = pd.Timestamp('2026-08-20T04:00Z')


def predictions(signals=(3.,), policy='price_near'):
    return pd.DataFrame([{'date': '2026-08-20', 'decision_at': AT+pd.Timedelta(minutes=i),
        'horizon_minutes': 1, 'close': 24000., f'prediction_{policy}': signal} for i, signal in enumerate(signals)])


def quote(seconds, sid='old', strike=24000., bid=99., ask=100., **changes):
    return {'timestamp': AT+pd.Timedelta(seconds=seconds), 'security_id': sid,
        'expiry': '2026-08-25', 'strike': strike, 'option_type': 'CE', 'bid': bid, 'ask': ask, **changes}


def book(rows):
    return {'2026-08-20': study.QuoteBook(pd.DataFrame(rows), 2.)}


def test_alignment_sides_and_real_costs():
    ledger, counts = study.replay(predictions(), book([quote(0), quote(1, bid=102, ask=103),
        quote(60, bid=110, ask=111)]), 'price_near', 'single', .5)
    row = ledger[0]
    assert counts['priced'] == 1
    assert pd.Timestamp(row['exit_at']) == AT+pd.Timedelta(seconds=60)
    assert pd.Timestamp(row['exit_at'])-pd.Timestamp(row['entry_at']) == pd.Timedelta(seconds=59)
    assert row['gross_pnl'] == 7*65
    assert row['order_count'] == 2 and row['estimated_charges_excluding_slippage'] > 40
    assert row['net_pnl'] == pytest.approx(row['gross_pnl']-row['estimated_charges_excluding_slippage']-13)
    assert row['roundtrip_half_spread_diagnostic'] == 65


def test_spread_sides_and_four_orders():
    rows = [quote(0), quote(0, sid='wing', strike=24050, bid=79, ask=80),
        quote(1), quote(1, sid='wing', strike=24050, bid=79, ask=80),
        quote(60, bid=110, ask=111), quote(60, sid='wing', strike=24050, bid=82, ask=83)]
    ledger, counts = study.replay(predictions(), book(rows), 'price_near', 'vertical', .5)
    row = ledger[0]
    assert counts['priced'] == 1
    assert row['entry_debit'] == (100-79)*65
    assert row['gross_pnl'] == ((110-100)-(83-79))*65
    assert row['order_count'] == 4


def test_unpriced_exit_stops_reentry_for_date():
    rows = [quote(0), quote(1), quote(120), quote(121), quote(180, bid=110, ask=111)]
    ledger, counts = study.replay(predictions((3.,3.,3.)), book(rows), 'price_near', 'single', .5)
    assert len(ledger) == 1 and ledger[0]['status'] == 'unpriced_exit'
    assert counts['blocked_by_exposure'] == 2
    assert not study.summarize(ledger, counts)['complete_valuation']


def test_future_quote_cannot_create_candidate():
    ledger, counts = study.replay(predictions(), book([quote(1), quote(60)]), 'price_near', 'single', .5)
    assert not ledger and counts['missing_candidate'] == 1


@pytest.mark.parametrize('phase,seconds', [('delayed_entry', 1), ('exit', 60)])
@pytest.mark.parametrize('field,value', [('expiry','2026-09-01'), ('strike',24050), ('option_type','PE')])
def test_contract_identity_fails_at_each_boundary(phase, seconds, field, value):
    rows = [quote(0), quote(1), quote(60)]
    rows[1 if seconds == 1 else 2][field] = value
    with pytest.raises(ValueError, match=f'Contract identity changed at {phase}'):
        study.replay(predictions(), book(rows), 'price_near', 'single', .5)


@pytest.mark.parametrize('signal', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_signal_cannot_trade(signal):
    ledger, counts = study.replay(predictions((signal,)), {}, 'price_near', 'single', .5)
    assert not ledger and counts['invalid_evidence'] == 1


def test_exact_threshold_trades_and_smaller_signal_does_not():
    rows = book([quote(0), quote(1), quote(60)])
    ledger, _ = study.replay(predictions((.5,)), rows, 'price_near', 'single', .5)
    assert len(ledger) == 1
    ledger, counts = study.replay(predictions((.499,)), rows, 'price_near', 'single', .5)
    assert not ledger and counts['no_trade_signal'] == 1


def test_other_forecast_horizon_rejected():
    frame = predictions(); frame['horizon_minutes'] = 5
    with pytest.raises(ValueError, match='one-minute forecasts'):
        study.replay(frame, {}, 'price_near', 'single', .5)


def test_zero_reference_has_no_quote_lookup_or_positions():
    ledger, counts = study.replay(predictions((0.,)), {}, 'price_near', 'single', .5)
    assert not ledger and counts['no_trade_signal'] == 1
    assert study.summarize(ledger, counts)['conditional_net_pnl'] == 0


def test_bearish_forecast_buys_put_and_cannot_use_call():
    rows = [quote(0), quote(1), quote(60, bid=200, ask=201)]
    rows.extend([quote(0, sid='put', option_type='PE'), quote(1, sid='put', option_type='PE'),
        quote(60, sid='put', option_type='PE', bid=110, ask=111)])
    ledger, _ = study.replay(predictions((-3.,)), book(rows), 'price_near', 'single', .5)
    assert ledger[0]['strategy'] == 'long_put'
    assert ledger[0]['contracts'][0]['security_id'] == 'put'
    assert ledger[0]['gross_pnl'] == 10*65
