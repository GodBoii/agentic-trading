from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

spec=importlib.util.spec_from_file_location("expiry_study",Path(__file__).with_name("study.py"))
study=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=study
spec.loader.exec_module(study)

AT=pd.Timestamp("2026-08-20T04:00:00Z")


def quote(strike: float,mid: float,width: float=.1,kind: str="CE",stamp=AT,expiry="2026-08-25") -> dict:
    return dict(security_id=f"{kind}{strike}",option_type=kind,strike=strike,bid=mid-width/2,
                ask=mid+width/2,timestamp=stamp,expiry=expiry)


def test_black_surface_respects_all_payoff_bounds_and_unequal_strikes():
    years=study.discounted_years("2026-08-25",AT)
    rows=[quote(strike,study.volatility.black_price(24000,strike,years,.1,.2,kind),kind=kind)
          for kind in ("CE","PE") for strike in (23850.,23950.,24000.,24150.)]
    checks=study.shape_checks({row["security_id"]:row for row in rows},AT,.25,.1)
    assert len(checks)==16
    assert all(row["status"]=="within_quoted_bound" for row in checks)


def test_midpoint_violation_covered_by_bidask_is_not_quote_bound_violation():
    rows=[quote(24000.,99.,4.),quote(24050.,100.,4.)]
    result=study.bound_check(rows,[1.,-1.],0.,False,AT,.25,"monotonic",0.)
    assert result["midpoint_violation"]
    assert not result["conditional_quote_violation"]
    assert result["status"]=="midpoint_only_violation"
    assert result["quote_side_value"]==3.


def test_vertical_upper_uses_sell_bid_buy_ask_and_discounted_cap():
    rows=[quote(24000.,100.,1.),quote(24050.,40.,1.)]
    result=study.bound_check(rows,[1.,-1.],49.,True,AT,.25,"upper",.1)
    assert result["quote_side_value"]==59.
    assert result["violation_gap_points"]==10.
    assert result["status"]=="conditional_quote_bound_violation"


def test_general_butterfly_convexity_weights_match_expiry_payoff():
    strikes=(23900.,23950.,24100.)
    rows=[quote(strike,100.,.1) for strike in strikes]
    checks=study.shape_checks({row["security_id"]:row for row in rows},AT,.25)
    butterfly=next(row for row in checks if row["family"]=="butterfly_convexity")
    assert butterfly["weights"]==[.75,-1.,.25]
    for kind in ("CE","PE"):
        spots=np.linspace(23500,24500,1001)
        payoff=sum(weight*np.maximum(spots-strike,0) if kind=="CE" else weight*np.maximum(strike-spots,0)
                   for strike,weight in zip(strikes,butterfly["weights"],strict=True))
        assert payoff.min()>=-1e-8


@pytest.mark.parametrize("stamp,skew,status",[(AT+pd.Timedelta(seconds=1),2.,"future_quote_rejected"),
                                           (AT-pd.Timedelta(seconds=3),2.,"stale_receipt_rejected"),
                                           (AT-pd.Timedelta(seconds=1),.25,"receipt_skew_rejected")])
def test_origin_freshness_and_sync_rejections(stamp,skew,status):
    rows=[quote(24000.,100.),quote(24050.,70.,stamp=stamp)]
    result=study.bound_check(rows,[1.,-1.],0.,False,AT,skew,"monotonic",0.)
    assert result["status"]==status
    assert result["conditional_quote_violation"] is None


def test_same_expiry_requirement():
    rows=[quote(24000.,100.),quote(24050.,70.,expiry="2026-09-01")]
    assert study.receipt_validity(rows,AT,2.)=="mixed_expiry_rejected"


def test_quote_lookup_backward_and_identity_validation():
    row=quote(24000.,100.)
    book=study.hedging.IndexedBook(pd.DataFrame([row]))
    assert not book.snapshot(AT-pd.Timedelta(seconds=1))
    assert book.snapshot(AT+pd.Timedelta(seconds=2))
    assert not book.snapshot(AT+pd.Timedelta(seconds=2,microseconds=1))
    changed=dict(row,strike=24050.,timestamp=AT+pd.Timedelta(seconds=1))
    with pytest.raises(ValueError,match="identity"):
        study.hedging.IndexedBook(pd.DataFrame([row,changed]))


def test_parity_forward_flat_volatility_has_zero_local_wing_difference():
    years=study.discounted_years("2026-08-25",AT)
    rows=[quote(strike,study.volatility.black_price(24000,strike,years,0.,.2,kind),kind=kind)
          for kind in ("CE","PE") for strike in (23900.,24000.,24100.)]
    result=study.iv_wing_snapshot({row["security_id"]:row for row in rows},AT,.25)
    assert result["status"]=="conditional_midpoint_iv"
    assert result["forward"]==pytest.approx(24000.)
    assert result["put_minus_call_iv_percentage_points"]==pytest.approx(0.,abs=1e-8)
    assert result["put_strike"]==23900. and result["call_strike"]==24100.


def test_day_equal_means_do_not_overweight_long_recording_or_lose_gapped_rows():
    frame=pd.DataFrame(dict(date=["a","b","b","b"],group=[0]*4,x=[10.,0.,0.,0.]),index=[1,3,7,20])
    result=study.equal_day_table(frame,["group"],["x"])[0]
    assert result["day_equal"]["x"]==5.
    assert result["rows"]==4 and result["days"]==2
    assert result["daily_rows"]=={"a":1,"b":3}


def test_fixed_straddle_uses_original_ids_and_retains_unpriced_status():
    rows=[]
    for stamp,cmid,pmid in ((AT,100.,90.),(AT+pd.Timedelta(seconds=1),100.,90.),(AT+pd.Timedelta(minutes=5,seconds=1),95.,85.)):
        rows.extend([quote(24000.,cmid,kind="CE",stamp=stamp),quote(24000.,pmid,kind="PE",stamp=stamp)])
    book=study.hedging.IndexedBook(pd.DataFrame(rows))
    source=dict(date="2026-08-20",decision_at=AT,entry_at=AT+pd.Timedelta(seconds=1),
                exit_at=AT+pd.Timedelta(minutes=5,seconds=1),call_id="CE24000.0",put_id="PE24000.0",
                strike=24000.,expiry="2026-08-25",entry_mid=190.,mid_change=-10.,abs_futures_change_points=4.)
    result=study.fixed_straddle_observation(source,book,.25)
    assert result["status"]=="conditional_fixed_straddle"
    assert result["compression_fraction"]==10/190
    assert result["entry_spread_points"]==pytest.approx(.2)
    source["exit_at"]+=pd.Timedelta(seconds=3)
    assert study.fixed_straddle_observation(source,book,.25)["status"]=="missing_quote"
