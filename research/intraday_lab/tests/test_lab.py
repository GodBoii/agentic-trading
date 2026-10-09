"""Behavior tests for causality, accounting, exposure, and uncertain exits."""

from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pyarrow as pa
import pyarrow.parquet as pq

from research.intraday_lab.costs import order_fees, round_trip_fees
from research.intraday_lab.audit import audit_raw
from research.intraday_lab.data import load_session, select_universe
from research.intraday_lab.domain import ExecutionConfig, PolicyConfig, Tick
from research.intraday_lab.policy import MomentumPolicy
from research.intraday_lab.replay import ReplayEngine


BASE = int(datetime.fromisoformat("2026-08-19T10:00:00+05:30").timestamp() * 1_000_000)


def tick(second: int, midpoint: float = 100.0, sid: int = 1, **changes) -> Tick:
    return replace(Tick(BASE + second * 1_000_000, sid, f"TEST{sid}", midpoint - .01,
                        midpoint + .01, midpoint, 99.0, 10_000, 10_000, 0.0, True, True), **changes)


def policy(**changes) -> PolicyConfig:
    return replace(PolicyConfig(), lookback_seconds=60, confirmation_seconds=10,
                   minimum_move_bps=2, confirmation_move_bps=0.5,
                   target_bps=10, stop_bps=10, horizon_seconds=5, **changes)


def execution(**changes) -> ExecutionConfig:
    return replace(ExecutionConfig(), starting_equity=20_000, maximum_position_value=10_000,
                   risk_per_trade=100, maximum_daily_loss=500, **changes)


def rising(sid: int = 1) -> list[Tick]:
    return [tick(i, 100 + i * .001, sid) for i in range(62)]


class FeeTests(unittest.TestCase):
    def test_sell_tax_and_buy_stamp_are_assigned_to_correct_legs(self):
        buy = order_fees(100, 1000, is_buy=True)
        sell = order_fees(100, 1000, is_buy=False)
        self.assertEqual(float(buy.stt), 0)
        self.assertEqual(float(buy.stamp), 3)
        self.assertEqual(float(sell.stt), 25)
        self.assertEqual(float(sell.stamp), 0)
        self.assertEqual(float(buy.brokerage), 20)
        self.assertEqual(round_trip_fees(100, 100, 1000, long=True), 82.68)

    def test_short_leg_values_change_costs_in_correct_direction(self):
        expected = float(order_fees(100, 100, is_buy=False).total + order_fees(95, 100, is_buy=True).total)
        self.assertEqual(round_trip_fees(100, 95, 100, long=False), expected)

    def test_small_order_cost_is_not_constant_in_basis_points(self):
        small = round_trip_fees(100, 100, 100, long=True) / 10000
        big = round_trip_fees(100, 100, 10000, long=True) / 1000000
        self.assertGreater(small, big)

    def test_invalid_money_is_rejected(self):
        for value in (0, -1, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                order_fees(value, 10, is_buy=True)


class PolicyTests(unittest.TestCase):
    def test_history_never_uses_future_ticks(self):
        a = MomentumPolicy(policy())
        b = MomentumPolicy(policy())
        prefix_a = [a.on_tick(t) for t in rising()]
        prefix_b = [b.on_tick(t) for t in rising()]
        a.on_tick(tick(62, 200))
        b.on_tick(tick(62, 50))
        self.assertEqual(prefix_a, prefix_b)
        self.assertTrue(any(signal is not None for signal, _ in prefix_a))

    def test_gap_requires_new_warmup(self):
        engine = MomentumPolicy(policy())
        for item in rising():
            engine.on_tick(item)
        signal, reason = engine.on_tick(tick(120, 100.3))
        self.assertIsNone(signal)
        self.assertEqual(reason, "warming_history")

    def test_unknown_freshness_and_crossed_quote_fail_closed(self):
        for bad in (tick(0, trade_age_seconds=None), tick(0, bid=101, ask=100),
                    tick(0, connection_warm=False)):
            self.assertEqual(MomentumPolicy(policy()).on_tick(bad)[1], "unusable_observation")

    def test_vwap_filter_is_explicit(self):
        engine = MomentumPolicy(policy(require_vwap_alignment=True))
        signals = [engine.on_tick(replace(item, vwap=101.0)) for item in rising()]
        self.assertFalse(any(signal is not None for signal, _ in signals))
        self.assertIn("vwap_alignment", [reason for _, reason in signals])

    def test_receipt_proxy_does_not_change_strict_unknown_freshness(self):
        unknown = tick(0, data_fresh=None, connection_warm=None, trade_age_seconds=None)
        self.assertFalse(unknown.usable(5))
        self.assertTrue(unknown.usable(5, receipt_proxy=True))
        self.assertFalse(replace(unknown, data_fresh=False).usable(5, receipt_proxy=True))


class ReplayTests(unittest.TestCase):
    def test_entry_and_exit_execute_on_later_observations(self):
        engine = ReplayEngine(policy(), execution())
        engine.run([*rising(), tick(62, 100.30), tick(63, 100.28)])
        self.assertEqual(len(engine.trades), 1)
        trade = engine.trades[0]
        self.assertGreater(trade.entry_us, trade.signal_us)
        self.assertEqual(trade.exit_us, BASE + 63_000_000)
        self.assertGreaterEqual(trade.entry_price, tick(61, 100.061).ask)
        self.assertLessEqual(trade.exit_price, tick(63, 100.28).bid)
        self.assertAlmostEqual(trade.net_pnl, trade.gross_pnl - trade.fees)

    def test_no_same_tick_execution_even_at_zero_latency(self):
        engine = ReplayEngine(policy(), execution(latency_ms=0))
        engine.run(rising()[:-1])
        self.assertEqual(len(engine.positions), 0)
        self.assertEqual(len(engine.entries), 1)

    def test_large_entry_jump_cancels_instead_of_chasing(self):
        engine = ReplayEngine(policy(), execution())
        engine.run([*rising()[:-1], tick(61, 102)])
        self.assertEqual(len(engine.positions), 0)
        self.assertEqual(engine.counts["entry_canceled_drift_or_spread"], 1)

    def test_missing_future_exit_is_unresolved_not_fake_closed(self):
        engine = ReplayEngine(policy(), execution())
        report = engine.run(rising())
        self.assertFalse(report["complete"])
        self.assertEqual(report["trades"], 0)
        self.assertEqual(len(report["unresolved_positions"]), 1)

    def test_pending_entry_expires_during_other_instrument_activity(self):
        engine = ReplayEngine(policy(), execution(order_ttl_seconds=1))
        engine.run([*rising()[:-1], tick(62, sid=2)])
        self.assertEqual(len(engine.entries), 0)
        self.assertEqual(engine.counts["entry_expired"], 1)

    def test_slots_include_pending_orders(self):
        engine = ReplayEngine(policy(), execution(maximum_positions=2))
        observations = sorted([item for sid in range(1, 5) for item in rising(sid)[:-1]],
                              key=lambda item: (item.at_us, item.security_id))
        report = engine.run(observations)
        self.assertLessEqual(report["maximum_slots_used"], 2)
        self.assertEqual(len(engine.entries), 2)
        self.assertGreater(engine.counts["risk_slots"], 0)
        self.assertLessEqual(report["maximum_committed_value"], 20_000)

    def test_repeat_run_is_identical(self):
        ticks = [*rising(), tick(62, 100.30), tick(63, 100.28)]
        a = ReplayEngine(policy(), execution()).run(ticks)
        b = ReplayEngine(policy(), execution()).run(ticks)
        self.assertEqual(a, b)

    def test_no_trade_is_valid_under_cost_gate(self):
        cfg = replace(policy(), require_cost_room=True, target_bps=1)
        engine = ReplayEngine(cfg, execution())
        engine.run(rising())
        self.assertEqual(len(engine.positions), 0)
        self.assertGreater(engine.counts["risk_cost_room"], 0)

    def test_loss_halt_blocks_entries_but_manages_open_position(self):
        engine = ReplayEngine(policy(), replace(execution(), maximum_daily_loss=1))
        engine.run([*rising(), tick(62, 99.0), tick(63, 98.9)])
        self.assertTrue(engine.loss_halted)
        self.assertEqual(len(engine.trades), 1)
        self.assertEqual(len(engine.positions), 0)

    def test_out_of_order_and_cross_session_observations_are_rejected(self):
        engine = ReplayEngine(policy(), execution())
        engine.on_tick(tick(2))
        with self.assertRaises(ValueError):
            engine.on_tick(tick(1))
        with self.assertRaises(ValueError):
            engine.on_tick(tick(86402))

    def test_small_account_does_not_exceed_reserved_cash(self):
        engine = ReplayEngine(policy(), replace(execution(), starting_equity=1000))
        engine.run(rising())
        self.assertLessEqual(engine.maximum_committed_value, 1000)

    def test_fill_rechecks_position_value_after_price_change(self):
        engine = ReplayEngine(policy(), replace(execution(), maximum_position_value=10_008.01))
        engine.run([*rising()[:-1], tick(61, 100.08)])
        self.assertEqual(len(engine.positions), 0)
        self.assertEqual(engine.counts["entry_canceled_revalidated_risk"], 1)

    def test_short_profit_and_fees_are_accounted(self):
        engine = ReplayEngine(policy(), execution())
        falling = [tick(i, 100 - i * .001) for i in range(62)]
        engine.run([*falling, tick(62, 99.7), tick(63, 99.72)])
        self.assertEqual(len(engine.trades), 1)
        trade = engine.trades[0]
        self.assertEqual(trade.side, "SHORT")
        self.assertGreater(trade.gross_pnl, 0)


class DataTests(unittest.TestCase):
    def test_raw_audit_keeps_negative_clock_offset(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "2026-08-19/raw-depth"
            raw.mkdir(parents=True)
            rows = [{"received_at": "2026-08-19T10:00:00+05:30", "security_id": 1,
                     "packet_json": json.dumps({"type": "Full Data", "LTT": "10:00:02"}),
                     "capture_scope": "hot_only"}]
            pq.write_table(pa.Table.from_pylist(rows), raw / "packets.parquet")
            report = audit_raw(root, "2026-08-19", {1}, 100)
            self.assertEqual(report["counts"]["negative_trade_age"], 1)
            self.assertEqual(report["trade_age_quantiles_seconds"]["0.5"], -2)

    def test_raw_capture_without_scope_is_explicitly_unknown(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "2026-08-19/raw-depth"
            raw.mkdir(parents=True)
            row = {"received_at": "2026-08-19T10:00:00+05:30", "security_id": 1,
                   "packet_json": json.dumps({"LTT": "09:59:59"})}
            pq.write_table(pa.Table.from_pylist([row]), raw / "packets.parquet")
            report = audit_raw(root, "2026-08-19", {1}, 100)
            self.assertEqual(report["counts"]["scope_unknown"], 1)

    def test_universe_uses_nested_historical_adv_and_excludes_unknown(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "universe.json"
            stocks = [{"security_id": sid, "symbol": str(sid), "exchange_segment": "NSE_EQ",
                       "historical": {"adv_20_cr": adv}} for sid, adv in ((1, 2), (2, 100), (3, None))]
            path.write_text(json.dumps({"summary": {"market_date": "2026-08-18"}, "stocks": stocks}))
            selected, _ = select_universe(path, ["2026-08-19"], 1)
            self.assertEqual(selected[0]["security_id"], 2)

    def test_universe_cannot_come_from_replay_date(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "universe.json"
            path.write_text(json.dumps({"summary": {"market_date": "2026-08-19"}, "stocks": []}))
            with self.assertRaises(ValueError):
                select_universe(path, ["2026-08-19"], 2)

    def test_loader_keeps_venue_identity_and_reports_duplicates(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            tape = root / "2026-08-19/one-second"
            tape.mkdir(parents=True)
            row = {"received_at": "2026-08-19T10:00:00+05:30", "security_id": 1,
                   "exchange_segment": "NSE_EQ", "symbol": "T", "last_price": 100.,
                   "best_bid": 99.99, "best_ask": 100.01, "vwap": 100.,
                   "bid_quantity_5": 1000., "ask_quantity_5": 1000.,
                   "last_trade_age_seconds": 0., "data_fresh": True, "connection_warm": True}
            rows = [row, row, {**row, "exchange_segment": "BSE_EQ"},
                    {**row, "received_at": "2026-08-19T10:00:01+05:30"}]
            pq.write_table(pa.Table.from_pylist(rows), tape / "test.parquet")
            ticks, report = load_session(root, "2026-08-19", [1])
            self.assertEqual(len(ticks), 1)
            self.assertEqual(report["diagnostics"]["duplicate_identity_rows"], 2)
            self.assertEqual(report["diagnostics"]["selected_rows_read"], 3)
            self.assertEqual(len(report["normalized_tape_sha256"]), 64)

    def test_missing_flags_remain_unknown_and_are_counted(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            tape = root / "2026-08-19/one-second"
            tape.mkdir(parents=True)
            row = {"received_at": "2026-08-19T10:00:00+05:30", "security_id": 1,
                   "exchange_segment": "NSE_EQ", "symbol": "T", "last_price": 100.,
                   "best_bid": 99.99, "best_ask": 100.01, "bid_quantity_5": 1000.,
                   "ask_quantity_5": 1000.}
            pq.write_table(pa.Table.from_pylist([row]), tape / "test.parquet")
            ticks, report = load_session(root, "2026-08-19", [1])
            self.assertIsNone(ticks[0].data_fresh)
            self.assertIsNone(ticks[0].connection_warm)
            self.assertEqual(report["diagnostics"]["missing_data_fresh_flag"], 1)
            self.assertEqual(report["diagnostics"]["usable_at_5s_age"], 0)
            self.assertEqual(report["diagnostics"]["usable_receipt_proxy"], 1)


if __name__ == "__main__":
    unittest.main()
