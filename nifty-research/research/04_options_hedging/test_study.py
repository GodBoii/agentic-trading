from __future__ import annotations

from dataclasses import replace
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location("hedging_study", Path(__file__).with_name("study.py"))
study = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = study
spec.loader.exec_module(study)


def quote(stamp, sid="1", kind="CE", strike=24000., bid=100., ask=101.):
    return dict(timestamp=pd.Timestamp(stamp), security_id=sid, expiry="2026-08-25",
                strike=strike, option_type=kind, bid=bid, ask=ask)


def test_quotes_never_look_forward_and_expire():
    frame = pd.DataFrame([quote("2026-08-20T04:00:00Z"), quote("2026-08-20T04:00:02Z", bid=200., ask=201.)])
    book = study.IndexedBook(frame)
    assert book.snapshot(pd.Timestamp("2026-08-20T03:59:59Z")) == {}
    assert book.snapshot(pd.Timestamp("2026-08-20T04:00:01Z"))["1"]["bid"] == 100
    assert book.snapshot(pd.Timestamp("2026-08-20T04:00:05Z")) == {}


def test_identity_and_crossed_quotes_rejected():
    with pytest.raises(ValueError, match="identity"):
        study.IndexedBook(pd.DataFrame([quote("2026-08-20T04:00:00Z"), quote("2026-08-20T04:00:02Z", strike=24050)]))
    with pytest.raises(ValueError, match="Invalid quotes"):
        study.IndexedBook(pd.DataFrame([quote("2026-08-20T04:00:00Z", bid=101., ask=100.)]))


def test_unpriced_exit_keeps_position_and_halts_date():
    at = pd.Timestamp("2026-08-20T04:00:00Z")
    book = study.IndexedBook(pd.DataFrame([quote(at), quote(at+pd.Timedelta(seconds=1))]))
    rows = [dict(date="2026-08-20", decision_at=at, close=24000.),
            dict(date="2026-08-20", decision_at=at+pd.Timedelta(minutes=10), close=24000.)]
    ledger, counts = study.replay_day(rows, book, "long_call", 5, study.ResearchConfig())
    assert len(ledger) == 1
    assert ledger[0]["status"] == "unpriced_exit"
    assert counts["unpriced_exit"] == 1
    assert ledger[0]["missing_path_marks"] > 0


def test_one_second_latency_and_fixed_contract():
    at = pd.Timestamp("2026-08-20T04:00:00Z")
    frame = pd.DataFrame([quote(at, bid=100., ask=101.),
                          quote(at+pd.Timedelta(seconds=1), bid=110., ask=111.),
                          quote(at+pd.Timedelta(minutes=5,seconds=1), bid=120.,ask=121.)])
    ledger, _ = study.replay_day([dict(date="2026-08-20",decision_at=at,close=24000.)],
                                study.IndexedBook(frame), "long_call",5,study.ResearchConfig())
    assert ledger[0]["contracts"][0]["ask"] == 111
    assert ledger[0]["gross_pnl"] == 9*65
    assert ledger[0]["net_pnl"] < ledger[0]["gross_pnl"]
    assert ledger[0]["margin"] is None


def test_iron_condor_terminal_risk_bounded_and_credit_costs():
    at = pd.Timestamp("2026-08-20T04:00:00Z")
    rows = [quote(at,str(i),kind,strike,bid,ask) for i,(kind,strike,bid,ask) in enumerate([
        ("PE",23900.,20.,21.),("PE",23950.,35.,36.),("CE",24050.,35.,36.),("CE",24100.,20.,21.),
        ("CE",24000.,60.,61.),("PE",24000.,60.,61.)])]
    snapshot = {row["security_id"]:row for row in rows}
    strategy = study.candidates(snapshot,24000.)["iron_condor"]
    risk = strategy.expiry_risk(65)
    assert risk["net_entry_debit"] == -28*65
    assert risk["max_loss_before_costs"] == 22*65
    assert risk["max_profit_before_costs"] == 28*65
    assert study.entry_economic(strategy,65)
    pnl,cost = study.liquidation(strategy,snapshot,study.ResearchConfig())
    assert pnl == -4*65
    assert cost > 8*20


def test_candidate_choice_tie_is_deterministic():
    at = pd.Timestamp("2026-08-20T04:00:00Z")
    snapshot = {str(i):quote(at,str(i),"CE",strike) for i,strike in enumerate((24000.,24050.))}
    candidate = study.candidates(snapshot,24025.)["long_call"]
    assert candidate.legs[0].strike == 24000.


def test_mismatched_fixed_contract_rejected():
    leg = study.Leg("CE",24000.,1,100.,101.,"1","2026-08-25")
    strategy = study.Strategy("long_call",(leg,))
    with pytest.raises(ValueError, match="identity"):
        study.reprice(strategy,{"1":quote("2026-08-20T04:00:00Z",strike=24050.)})


def test_synthetic_costs_cannot_improve_same_path_hedge():
    result = study.synthetic_hedging(samples=100)
    assert result["status"] == "SYNTHETIC_ONLY"
    for frequency in (1,5,15,30,60):
        rows = [row for row in result["results"] if row["rebalance_minutes"]==frequency]
        assert rows[0]["mean_pnl_points"] > rows[1]["mean_pnl_points"] > rows[2]["mean_pnl_points"]
        assert rows[0]["mean_cost_points"] == 0


def test_expiry_boundary_blocked_without_future_filter():
    at=pd.Timestamp("2026-08-20T09:55:00Z")
    book=study.IndexedBook(pd.DataFrame([quote(at)]))
    ledger,counts=study.replay_day([dict(date="2026-08-20",decision_at=at,close=24000.)],book,
                                 "long_call",5,study.ResearchConfig())
    assert ledger == []
    assert counts["session_close"] == 1
