import importlib.util
from pathlib import Path
import pandas as pd
import pytest

spec=importlib.util.spec_from_file_location('execution_study',Path(__file__).with_name('study.py'))
study=importlib.util.module_from_spec(spec);spec.loader.exec_module(study)


def predictions():
    at=pd.Timestamp('2026-08-20T04:00Z')
    return pd.DataFrame([{'date':'2026-08-20','decision_at':at,'close':24000,'prediction_momentum':3}])


def test_latency_retains_original_contract():
    at=pd.Timestamp('2026-08-20T04:00Z')
    rows=[{'timestamp':at,'security_id':'old','expiry':'2026-08-25','strike':24000,'option_type':'CE','bid':99,'ask':100},
          {'timestamp':at+pd.Timedelta(seconds=3),'security_id':'old','expiry':'2026-08-25','strike':24000,'option_type':'CE','bid':102,'ask':103},
          {'timestamp':at+pd.Timedelta(seconds=303),'security_id':'old','expiry':'2026-08-25','strike':24000,'option_type':'CE','bid':110,'ask':111}]
    ledger,counts=study.replay(predictions(),{'2026-08-20':study.QuoteBook(pd.DataFrame(rows),2)},'momentum','single',3)
    assert counts['priced']==1 and ledger[0]['contracts']==['old']
    assert ledger[0]['gross_pnl']==455
    assert ledger[0]['net_by_slippage']['0.1']>ledger[0]['net_by_slippage']['0.5']>ledger[0]['net_by_slippage']['1.0']


def test_future_entry_quote_does_not_create_candidate():
    at=pd.Timestamp('2026-08-20T04:00:01Z')
    frame=pd.DataFrame([{'timestamp':at,'security_id':'old','expiry':'2026-08-25','strike':24000,'option_type':'CE','bid':99,'ask':100}])
    ledger,counts=study.replay(predictions(),{'2026-08-20':study.QuoteBook(frame,2)},'momentum','single',1)
    assert not ledger and counts['missing_candidate']==1


def test_pairing_uses_contract_identity():
    common={'date':'2026-08-20','decision_at':'time','policy':'p','structure':'s','status':'priced','net_by_slippage':{'0.1':1}}
    assert study.paired_comparison([{**common,'contracts':['a']}],[{**common,'contracts':['b']}])['common_priced_entries']==0


@pytest.mark.parametrize('field,new_value', [('expiry', '2026-09-01'), ('strike', 24050), ('option_type', 'PE')])
def test_changed_contract_identity_at_delayed_entry_fails(field, new_value):
    at = pd.Timestamp('2026-08-20T04:00Z')
    initial = {'timestamp': at, 'security_id': 'old', 'expiry': '2026-08-25',
               'strike': 24000, 'option_type': 'CE', 'bid': 99, 'ask': 100}
    delayed = {**initial, 'timestamp': at + pd.Timedelta(seconds=3), field: new_value}
    book = study.QuoteBook(pd.DataFrame([initial, delayed]), 2)
    with pytest.raises(ValueError, match='Contract identity changed before delayed entry: old'):
        study.replay(predictions(), {'2026-08-20': book}, 'momentum', 'single', 3)


@pytest.mark.parametrize('signal', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_signal_rejects_before_quote_lookup(signal):
    frame = predictions()
    frame['prediction_momentum'] = signal
    ledger, counts = study.replay(frame, {}, 'momentum', 'single', 3)
    assert not ledger
    assert counts == {'invalid_signal': 1}
