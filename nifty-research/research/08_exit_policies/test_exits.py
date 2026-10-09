from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pandas as pd
import pytest

spec=importlib.util.spec_from_file_location("exit_study",Path(__file__).with_name("study.py"))
study=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=study
spec.loader.exec_module(study)


def mark(at, gross, thesis=None):
    return dict(timestamp=at,gross_pnl=gross,net_liquidation=gross if gross is not None else None,
                thesis_ret_1_bps=thesis)


def quote(at,bid,ask,sid="1",strike=24000.):
    return dict(timestamp=at,security_id=sid,expiry="2026-08-25",strike=strike,
                option_type="CE",bid=bid,ask=ask)


def test_first_observed_threshold_wins_without_future_choice():
    at=pd.Timestamp("2026-08-20T04:00:01Z")
    path=[mark(at,0),mark(at+pd.Timedelta(seconds=5),-11),mark(at+pd.Timedelta(seconds=10),25)]
    stamp,reason,threshold=study.first_trigger(path,study.ExitPolicy("test",.10,.20),100,1,at+pd.Timedelta(minutes=5))
    assert stamp==at+pd.Timedelta(seconds=5)
    assert reason=="stop"
    assert threshold==-10


def test_missing_samples_resume_at_overshoot_not_threshold():
    at=pd.Timestamp("2026-08-20T04:00:00Z")
    entry=at+pd.Timedelta(seconds=1)
    path=[mark(entry,0),mark(entry+pd.Timedelta(seconds=5),None),mark(entry+pd.Timedelta(seconds=10),-1000)]
    book=study.helpers.IndexedBook(pd.DataFrame([quote(entry+pd.Timedelta(seconds=11),80,81)]))
    strategy=study.helpers.Strategy("long_call",(study.helpers.Leg("CE",24000.,1,99.,100.,"1","2026-08-25"),))
    result=study.evaluate_exit(strategy,book,dict(date="2026-08-20",decision_at=at,signal_bps=3),path,
                               study.ExitPolicy("test",.10,.20),5,study.ResearchConfig())
    assert result["gross_pnl"]==-20*65
    assert result["stop_overshoot_rupees"]==10*65
    assert result["missing_monitor_samples"]==1
    assert not result["sampled_monitor_complete"]


def test_bid_ask_spread_liquidation_excludes_midpoint_fills():
    at=pd.Timestamp("2026-08-20T04:00:00Z")
    entry=at+pd.Timedelta(seconds=1)
    book=study.helpers.IndexedBook(pd.DataFrame([quote(entry+pd.Timedelta(minutes=5,seconds=1),95,105)]))
    strategy=study.helpers.Strategy("long_call",(study.helpers.Leg("CE",24000.,1,99.,100.,"1","2026-08-25"),))
    result=study.evaluate_exit(strategy,book,dict(date="2026-08-20",decision_at=at,signal_bps=3),[mark(entry,0)],
                               study.ExitPolicy("time"),5,study.ResearchConfig())
    assert result["gross_pnl"]==-5*65
    assert result["net_pnl"] < result["gross_pnl"]


def test_exit_after_trigger_uses_latency_not_trigger_quote():
    at=pd.Timestamp("2026-08-20T04:00:00Z")
    entry=at+pd.Timedelta(seconds=1)
    trigger=entry+pd.Timedelta(seconds=5)
    book=study.helpers.IndexedBook(pd.DataFrame([quote(trigger,89,90),quote(trigger+pd.Timedelta(seconds=1),80,81)]))
    strategy=study.helpers.Strategy("long_call",(study.helpers.Leg("CE",24000.,1,99.,100.,"1","2026-08-25"),))
    result=study.evaluate_exit(strategy,book,dict(date="2026-08-20",decision_at=at,signal_bps=3),[mark(trigger,-11*65)],
                               study.ExitPolicy("stop",.10,.20),5,study.ResearchConfig())
    assert result["gross_pnl"]==-20*65


def test_contract_identity_cannot_switch_at_stop():
    at=pd.Timestamp("2026-08-20T04:00:00Z")
    entry=at+pd.Timedelta(seconds=1)
    book=study.helpers.IndexedBook(pd.DataFrame([quote(entry+pd.Timedelta(minutes=5,seconds=1),100,101,strike=24050)]))
    strategy=study.helpers.Strategy("long_call",(study.helpers.Leg("CE",24000.,1,99.,100.,"1","2026-08-25"),))
    with pytest.raises(ValueError,match="identity"):
        study.evaluate_exit(strategy,book,dict(date="2026-08-20",decision_at=at,signal_bps=3),[mark(entry,0)],
                            study.ExitPolicy("time"),5,study.ResearchConfig())


def test_unpriced_exit_retained():
    at=pd.Timestamp("2026-08-20T04:00:00Z")
    entry=at+pd.Timedelta(seconds=1)
    book=study.helpers.IndexedBook(pd.DataFrame([quote(entry,99,100)]))
    strategy=study.helpers.Strategy("long_call",(study.helpers.Leg("CE",24000.,1,99.,100.,"1","2026-08-25"),))
    result=study.evaluate_exit(strategy,book,dict(date="2026-08-20",decision_at=at,signal_bps=3),[mark(entry,0)],
                               study.ExitPolicy("time"),5,study.ResearchConfig())
    assert result["status"]=="unpriced_exit"
    assert "net_pnl" not in result
    assert result["contracts"][0]["security_id"]=="1"


def test_thesis_backward_freshness_and_direction():
    at=pd.Timestamp("2026-08-20T04:00:00Z")
    frame=pd.DataFrame(dict(decision_at=[at,at+pd.Timedelta(minutes=1)],ret_1_bps=[3,-4]))
    assert study.thesis_at(frame,at+pd.Timedelta(seconds=5))==3
    assert study.thesis_at(frame,at-pd.Timedelta(seconds=1)) is None
    assert study.thesis_at(frame,at+pd.Timedelta(minutes=3)) is None
    path=[mark(at,0,3),mark(at+pd.Timedelta(minutes=1),0,-4)]
    assert study.first_trigger(path,study.ExitPolicy("thesis",thesis_reversal=True),100,1,at+pd.Timedelta(minutes=5))[1]=="thesis"


def test_entry_schedule_independent_of_forward_labels():
    at=pd.Timestamp("2026-08-20T04:00:00Z")
    frame=pd.DataFrame([dict(date="2026-08-20",decision_at=at+pd.Timedelta(minutes=i),close=24000,
                             ret_5_bps=3,complete_minute=True,target_bps=float("nan")) for i in (0,5,31)])
    rows=study.entry_schedule(frame)
    assert len(rows)==2
    assert rows[1]["decision_at"]==at+pd.Timedelta(minutes=31)


def test_trailing_uses_past_peak_and_reprices_later():
    at=pd.Timestamp("2026-08-20T04:00:01Z")
    path=[mark(at,10),mark(at+pd.Timedelta(seconds=5),30),mark(at+pd.Timedelta(seconds=10),9)]
    stamp,reason,threshold=study.first_trigger(path,study.ExitPolicy("trail",trailing_fraction=.20),100,1,
                                             at+pd.Timedelta(minutes=5))
    assert reason=="trailing" and threshold==10
    assert stamp==at+pd.Timedelta(seconds=10)
