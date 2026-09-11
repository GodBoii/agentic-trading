"""Build a dated, read-only execution audit from saved broker and scanner evidence."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
from statistics import median


IST = timezone(timedelta(hours=5, minutes=30))


def timestamp(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt.replace(tzinfo=IST).timestamp() if dt.tzinfo is None else dt.timestamp()


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def field(result: str, name: str):
    match = re.search(rf"^- {re.escape(name)}: (.*)$", result, re.MULTILINE)
    return match.group(1).strip() if match else None


def weighted(fills):
    quantity = sum(float(t["tradedQuantity"]) for t in fills)
    price = sum(float(t["tradedQuantity"]) * float(t["tradedPrice"]) for t in fills) / quantity if quantity else None
    return quantity, price


def compact_order(order):
    return {k: order.get(k) for k in (
        "orderId", "algoId", "tradingSymbol", "securityId", "exchangeSegment", "transactionType",
        "orderType", "orderStatus", "quantity", "filledQty", "price", "triggerPrice", "createTime",
        "updateTime", "exchangeTime", "omsErrorDescription", "correlationId")}


def classify_protection(super_order, exits, open_quantity):
    legs = {leg["legName"]: leg for leg in super_order.get("legDetails", [])}
    stop = legs.get("STOP_LOSS_LEG")
    target = legs.get("TARGET_LEG")
    if not stop or not target:
        return "missing_legs", "A protective leg is absent from the broker snapshot."
    if not super_order.get("filledQty"):
        return "unfilled", "Entry never filled. Cancelled protective legs do not imply an unprotected position."
    if open_quantity and stop["orderStatus"] in {"CANCELLED", "REJECTED", "EXPIRED"}:
        return "unprotected_open", "The same-venue position remains open while its stop leg is cancelled or inactive."
    if any(o["orderStatus"] == "TRADED" for o in exits):
        if stop["orderStatus"] == "TRADED":
            return "stop_exit", "Broker reports an SL exit and a linked filled child order."
        if target["orderStatus"] == "TRADED":
            return "target_exit", "Broker reports a target exit and a linked filled child order. The cancelled SL is expected after that exit."
    if stop["orderStatus"] == "PENDING" and not open_quantity:
        return "orphan_pending", "Position is closed, but the Super Order still reports pending protective legs."
    if stop["orderStatus"] == "CANCELLED":
        return "cancelled_protection", "SL is cancelled and no linked protective exit filled. A separate order must be reconciled."
    return "unverified", "The available snapshots do not establish the completed protection lifecycle."


def build(source: Path) -> dict:
    evidence = load(source / "evidence.json")
    prices = load(source / "charts.json")
    sessions = load(source / "session-times.json")
    broker = load(source / "broker-refreshed.json")
    accounts = broker["accounts"]
    if len(accounts) != 1:
        raise ValueError("This report requires a separate reconciliation per account")
    account = accounts[0]
    for name in ("orders", "super_orders", "trades", "positions"):
        if account[name]["status"] != "success":
            raise ValueError(f"Broker {name} did not load successfully")
    orders = account["orders"]["data"]
    super_orders = account["super_orders"]["data"]
    fills = account["trades"]["data"]
    positions = account["positions"]["data"]
    signal_by_id = {s["event_id"]: s for s in evidence["signals"]}
    if len(signal_by_id) != len(evidence["signals"]):
        raise ValueError("Duplicate event IDs require reconciliation")
    start_by_event = {s["session_id"].split("-")[1]: s["created_at"] for s in sessions if s["session_id"].startswith("intra-")}
    runs, attempts = {}, []
    reasons = Counter()
    for event in evidence["decisions"]:
        eid = event["event_id"]
        for user in (event.get("decision") or {}).get("user_results", []):
            results = (user.get("result") or {}).get("results") or []
            if not results:
                reasons[user.get("status_code") or "no_result"] += 1
                runs[eid] = {"reason": user.get("status_code") or "no_result", "agent_start": None}
            for result in results:
                candidate = result.get("candidate") or {}
                metadata = result.get("agent_metadata") or {}
                decision = result.get("decision") or {}
                ran = bool(metadata)
                reason = "ai_ran" if ran else decision.get("remarks") or decision.get("execution_status") or "unknown"
                reasons[reason] += 1
                run = {
                    "reason": reason, "agent_start": start_by_event.get(eid) if ran else None,
                    "preparation_start": timestamp((candidate.get("timing_context") or {}).get("analysis_started_at_utc")) if ran else None,
                    "finished": timestamp(event.get("finished_at_utc")),
                    "model_seconds": (metadata.get("metrics") or {}).get("duration"),
                    "decision": decision, "report": result.get("report_text") if ran else None,
                    "attempts": [],
                }
                for item in metadata.get("timeline", []):
                    if item.get("type") != "stock_agent_tool_call_completed" or item.get("tool_name") != "place_protected_intraday_order":
                        continue
                    text = item.get("result") or ""
                    attempt = {"event_id": eid, "tool_time": timestamp(item.get("created_at")),
                               "args": item.get("tool_args") or {}, "result": text,
                               "status": field(text, "status"), "order_id": field(text, "order_id"),
                               "reason": field(text, "remarks"), "broker_status_at_return": field(text, "broker_order_status")}
                    attempts.append(attempt)
                    run["attempts"].append(attempt)
                runs[eid] = run
    accepted = {a["order_id"]: a for a in attempts if a.get("order_id")}
    if set(accepted) != {s["orderId"] for s in super_orders}:
        raise ValueError("AI submissions and broker Super Orders do not match")

    trade_records = []
    assigned_fills = set()
    parent_ids = set(accepted)
    for super_order in sorted(super_orders, key=lambda s: s["createTime"]):
        oid = super_order["orderId"]
        attempt = accepted[oid]
        args = attempt["args"]
        signal = signal_by_id[attempt["event_id"]]
        legs = {leg["legName"]: leg for leg in super_order.get("legDetails", [])}
        stop, target = legs.get("STOP_LOSS_LEG"), legs.get("TARGET_LEG")
        entry_fills = [t for t in fills if t["orderId"] == oid]
        qty, entry = weighted(entry_fills)
        if qty != super_order.get("filledQty", 0):
            raise ValueError(f"Fill quantity does not reconcile for {oid}")
        linked = [o for o in orders if str(o.get("algoId")) == oid]
        exit_ids = {o["orderId"] for o in linked}
        exit_fills = [t for t in fills if t["orderId"] in exit_ids]
        external = False
        # A standalone close is attributed only when one same-venue candidate exists.
        if qty and not exit_fills:
            same_venue = [t for t in fills if t["orderId"] not in parent_ids
                          and not any(t["orderId"] == o["orderId"] and str(o.get("algoId")) in parent_ids for o in orders)
                          and (t["exchangeSegment"], str(t["securityId"])) == (super_order["exchangeSegment"], str(super_order["securityId"]))
                          and t["transactionType"] != super_order["transactionType"]
                          and timestamp(t["exchangeTime"]) >= min(timestamp(t["exchangeTime"]) for t in entry_fills)]
            if len({t["orderId"] for t in same_venue}) == 1:
                exit_fills = same_venue
                external = True
        exit_qty, exit_price = weighted(exit_fills)
        if exit_qty > qty:
            raise ValueError(f"Exit exceeds entry quantity for {oid}")
        open_position = next((p for p in positions if (p["exchangeSegment"], str(p["securityId"])) ==
                              (super_order["exchangeSegment"], str(super_order["securityId"]))), {})
        protection, explanation = classify_protection(super_order, linked, float(open_position.get("netQty", 0)))
        side = super_order["transactionType"]
        geometry = args.get("stop_loss_price", 0) < args.get("entry_price", 0) < args.get("target_price", 0) if side == "BUY" else args.get("target_price", 0) < args.get("entry_price", 0) < args.get("stop_loss_price", 0)
        match = bool(stop and target and abs(float(stop["price"]) - args["stop_loss_price"]) < 1e-8
                     and abs(float(target["price"]) - args["target_price"]) < 1e-8)
        initial_confirmed = bool(re.search(r"\| STOP_LOSS_LEG \|[^\n]*\| PENDING \|", attempt["result"])
                                 and re.search(r"\| TARGET_LEG \|[^\n]*\| PENDING \|", attempt["result"]))
        pnl = (exit_price - entry) * exit_qty * (1 if side == "BUY" else -1) if qty and exit_qty == qty else None
        for t in [*entry_fills, *exit_fills]:
            assigned_fills.add(str(t.get("exchangeTradeId")) + ":" + t["orderId"])
        record = {
            "order_id": oid, "event_id": attempt["event_id"], "key": f"{super_order['exchangeSegment']}|{super_order['securityId']}",
            "name": signal.get("display_name") or signal["symbol"], "symbol": super_order["tradingSymbol"],
            "side": side, "order_type": super_order["orderType"], "status": super_order["orderStatus"],
            "quantity": super_order["quantity"], "filled_quantity": qty,
            "submitted": timestamp(super_order["createTime"]), "tool_time": attempt["tool_time"],
            "entry_time": min((timestamp(t["exchangeTime"]) for t in entry_fills), default=None),
            "entry_price": entry, "planned_entry": args.get("entry_price"),
            "exit_time": max((timestamp(t["exchangeTime"]) for t in exit_fills), default=None),
            "exit_price": exit_price, "exit_quantity": exit_qty, "realized_pnl": round(pnl, 2) if pnl is not None else None,
            "stop": args.get("stop_loss_price"), "target": args.get("target_price"), "trailing_jump": args.get("trailing_jump", 0),
            "stop_status": stop.get("orderStatus") if stop else None, "target_status": target.get("orderStatus") if target else None,
            "initial_legs_confirmed": initial_confirmed, "geometry_valid": geometry, "broker_prices_match": match,
            "protection": protection, "explanation": explanation, "standalone_exit": external,
            "linked_orders": [compact_order(o) for o in linked], "same_venue_open_quantity": open_position.get("netQty", 0),
            "broker_entry": compact_order(super_order),
            "fills": [{k: t.get(k) for k in ("orderId", "exchangeTradeId", "exchangeSegment", "securityId", "transactionType", "tradedQuantity", "tradedPrice", "exchangeTime")} for t in [*entry_fills, *exit_fills]],
        }
        trade_records.append(record)

    stocks = {}
    all_outcomes = []
    for eid, signal in signal_by_id.items():
        key = f"{signal['exchange_segment']}|{signal['security_id']}"
        chart = prices["charts"].get(key, {})
        stock = stocks.setdefault(key, {"key": key, "name": signal.get("display_name") or signal["symbol"],
                                        "symbol": signal["symbol"], "exchange": signal["exchange_segment"],
                                        "bars": chart.get("bars", []), "observations": chart.get("rows", 0), "signals": [], "trades": []})
        run = runs.get(eid, {"reason": "not_dispatched", "agent_start": None})
        outcome = chart.get("outcomes", {}).get(eid)
        if outcome:
            all_outcomes.append({**outcome, "family": signal["setup_type"]})
        stock["signals"].append({"id": eid, "time": timestamp(signal["created_at"]),
                                 "armed": timestamp(signal["armed_at"]), "price": signal["price"],
                                 "family": signal["setup_type"], "direction": signal["direction"],
                                 "rank": signal.get("activity", {}).get("rank"), "run": run, "outcome": outcome})
    for trade in trade_records:
        stocks[trade["key"]]["trades"].append(trade["order_id"])
    for stock in stocks.values():
        stock["signals"].sort(key=lambda s: s["time"])
    delay = [r["agent_start"] - timestamp(signal_by_id[eid]["created_at"]) for eid, r in runs.items() if r.get("agent_start")]
    first_attempt = [min(a["tool_time"] for a in r["attempts"]) - timestamp(signal_by_id[eid]["created_at"]) for eid, r in runs.items() if r.get("attempts")]
    closed = [t for t in trade_records if t["realized_pnl"] is not None]
    pnl_total = round(sum(t["realized_pnl"] for t in closed), 2)
    if abs(pnl_total - sum(p["realizedProfit"] for p in positions)) > .02:
        raise ValueError("Closed trade P&L does not reconcile to broker positions")
    histogram = evidence["stage2"]["latency_histograms"]["operations"]["ingress"]
    stats = {
        "signals": len(signal_by_id), "stocks": len(stocks), "dispatched": len(evidence["decisions"]),
        "ai_runs": len(start_by_event), "placement_calls": len(attempts), "submitted_orders": len(super_orders),
        "filled_entries": sum(t["filled_quantity"] > 0 for t in trade_records), "closed_entries": len(closed),
        "wins": sum(t["realized_pnl"] > 0 for t in closed), "losses": sum(t["realized_pnl"] < 0 for t in closed),
        "realized_pnl": pnl_total, "open_pnl": round(sum(p["unrealizedProfit"] for p in positions), 2),
        "signal_to_ai_median_seconds": median(delay), "signal_to_ai_max_seconds": max(delay),
        "signal_to_first_order_attempt_median_seconds": median(first_attempt),
        "initial_protected_orders": sum(t["initial_legs_confirmed"] and t["geometry_valid"] and t["broker_prices_match"] for t in trade_records),
        "reasons": dict(reasons), "families": dict(Counter(s["setup_type"] for s in signal_by_id.values())),
        "placement_failures": dict(Counter(a["reason"] or "unknown" for a in attempts if a["status"] != "success")),
        "protection_counts": dict(Counter(t["protection"] for t in trade_records)),
        "packet_delay_over250_pct": sum(histogram["counts"][11:]) / histogram["observations"] * 100,
        "outcome_count": len(all_outcomes),
        "median_next_5m_range_pct": median(o["range_5m_pct"] for o in all_outcomes),
        "positive_direction_5m_pct": sum(o["return_5m_pct"] > 0 for o in all_outcomes) / len(all_outcomes) * 100,
        "max_confirmation_seconds": max(timestamp(s["triggered_at"]) - timestamp(s["armed_at"]) for s in signal_by_id.values()),
    }
    open_positions = [{k: p.get(k) for k in ("tradingSymbol", "exchangeSegment", "securityId", "netQty", "buyAvg", "sellAvg", "unrealizedProfit")} for p in positions if p["netQty"]]
    additional_fills = [{k: t.get(k) for k in ("tradingSymbol", "orderId", "exchangeTradeId", "exchangeSegment", "securityId", "transactionType", "tradedQuantity", "tradedPrice", "exchangeTime")} for t in fills if str(t.get("exchangeTradeId")) + ":" + t["orderId"] not in assigned_fills]
    return {"date": "2026-09-09", "broker_as_of": broker["retrieved_at"], "stats": stats,
            "stocks": sorted(stocks.values(), key=lambda s: s["name"]), "trades": trade_records,
            "open_positions": open_positions, "additional_fills": additional_fills,
            "additional_orders": [compact_order(o) for o in orders if o["tradingSymbol"] == "TCC" and o["exchangeSegment"] == "NSE_EQ"],
            "stage2": evidence["stage2"], "stage1_after_close": evidence["stage1"],
            "source_manifest": evidence["manifest"], "chart_files": len(prices["manifest"]),
            "broker_sha256": hashlib.sha256((source / "broker-refreshed.json").read_bytes()).hexdigest(),
            "sources": [{"name": "Dhan Super Order lifecycle", "url": "https://dhan.co/support/orders-and-positions/super-orders-on-dhan/how-is-a-super-order-executed/"},
                        {"name": "Dhan Super Order API", "url": "https://dhanhq.co/docs/v2/super-order/"}],
            "limitations": ["Initial TP/SL prices are confirmed, but no complete historical leg-status or modification stream was retained. Continuous protection and who modified/cancelled an order cannot be proved.",
                            "Candles are reconstructed from recorded one-second observations, not an exchange-complete tick tape. Missing minutes are not filled in.",
                            "AI start uses native Agno run creation time from Supabase, accurate to one second. Preparation start and order-attempt times are separately labelled.",
                            "Realized P&L is reconciled from fills and broker positions. It is before fees and excludes still-open TCC positions.",
                            "Initial TP/SL lines show the submitted configuration, not proof that those values stayed active throughout the trade.",
                            "The uploaded screenshot explains Dhan order badges; it is not used as dated evidence for September 9 trades."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(report["stats"], indent=2))
