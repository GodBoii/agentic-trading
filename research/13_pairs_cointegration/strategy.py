"""Fixed-pair descriptive research; no cointegration significance or live orders."""

from dataclasses import dataclass
from math import floor, log

import numpy as np

from research.intraday_lab.costs import round_trip_fees
from research.intraday_lab.domain import Tick

PAIR = (4963, 5900)
GRID_US = 60_000_000


@dataclass(frozen=True)
class PairPoint:
    at_us: int
    first: Tick
    second: Tick


def synchronize(ticks: list[Tick], *, receipt_proxy: bool) -> tuple[list[PairPoint], dict]:
    """As-of sampling uses no future quote and rejects old receipt snapshots."""
    selected = [t for t in ticks if t.security_id in PAIR]
    if any(a.at_us > b.at_us for a, b in zip(selected, selected[1:])):
        raise ValueError("tick receipt order must be increasing")
    if not selected:
        return [], {"eligible_points": 0, "candidate_points": 0}
    latest = {}
    cursor = 0
    points = []
    missing_leg = old_receipt = unusable_leg = wide_spread = 0
    start = ((selected[0].at_us + GRID_US - 1) // GRID_US) * GRID_US
    candidates = 0
    for at_us in range(start, selected[-1].at_us + 1, GRID_US):
        candidates += 1
        while cursor < len(selected) and selected[cursor].at_us <= at_us:
            latest[selected[cursor].security_id] = selected[cursor]
            cursor += 1
        if any(sid not in latest for sid in PAIR):
            missing_leg += 1
            continue
        pair = [latest[sid] for sid in PAIR]
        if any(at_us - tick.at_us > 5_000_000 for tick in pair):
            old_receipt += 1
            continue
        if any(not tick.usable(5, receipt_proxy=receipt_proxy) for tick in pair):
            unusable_leg += 1
            continue
        if any(tick.spread_bps > 5 for tick in pair):
            wide_spread += 1
            continue
        points.append(PairPoint(at_us, pair[0], pair[1]))
    return points, {"eligible_points": len(points), "candidate_points": candidates,
                    "rejected_points": candidates - len(points),
                    "missing_leg": missing_leg, "old_receipt": old_receipt,
                    "unusable_leg": unusable_leg, "wide_spread": wide_spread,
                    "observations_by_security": {str(sid): sum(t.security_id == sid for t in selected) for sid in PAIR}}


@dataclass(frozen=True)
class FrozenPair:
    intercept: float
    beta: float
    residual_scale: float
    training_points: int

    def residual(self, point: PairPoint) -> float:
        return log(point.first.midpoint) - self.intercept - self.beta * log(point.second.midpoint)

    def zscore(self, point: PairPoint) -> float:
        return self.residual(point) / self.residual_scale


def fit_pair(points: list[PairPoint]) -> FrozenPair | None:
    if len(points) < 100:
        return None
    x = np.log([p.second.midpoint for p in points])
    y = np.log([p.first.midpoint for p in points])
    if np.std(x) < 1e-8:
        return None
    intercept, beta = np.linalg.lstsq(np.column_stack([np.ones(len(x)), x]), y, rcond=None)[0]
    residual = y - intercept - beta * x
    scale = float(np.std(residual, ddof=2))
    if scale < 1e-8:
        return None
    return FrozenPair(float(intercept), float(beta), scale, len(points))


def ar1_diagnostics(points: list[PairPoint], model: FrozenPair) -> dict:
    """Lag fit drops all gaps/overnights. Half-life assumes a stable AR1, not proof."""
    pairs = [(model.residual(a), model.residual(b)) for a, b in zip(points, points[1:])
             if b.at_us - a.at_us == GRID_US]
    residual = np.array([model.residual(point) for point in points])
    result = {"points": len(points), "regular_lag_pairs": len(pairs),
              "mean_zscore": float(residual.mean() / model.residual_scale) if len(residual) else None,
              "std_zscore": float(residual.std() / model.residual_scale) if len(residual) else None,
              "fraction_abs_z_ge_2": float(np.mean(np.abs(residual) >= 2 * model.residual_scale))
              if len(residual) else None,
              "cointegration_test": "not run; statsmodels unavailable; no p-value or significance claim"}
    if len(pairs) < 30:
        return {**result, "ar1_status": "insufficient_regular_lag_pairs"}
    before, after = np.array(pairs).T
    if np.std(before) < 1e-10:
        return {**result, "ar1_status": "degenerate_residual"}
    intercept, phi = np.linalg.lstsq(np.column_stack([np.ones(len(before)), before]), after, rcond=None)[0]
    half_life = -log(2) / log(phi) if 0 < phi < 1 else None
    return {**result, "ar1_status": "descriptive_fit", "phi": float(phi),
            "ar1_intercept": float(intercept), "implied_half_life_minutes": half_life,
            "half_life_role": "conditional AR1 approximation; not a stationarity test",
            "fraction_distance_to_frozen_mean_shrinks": float(np.mean(np.abs(after) < np.abs(before)))}


def two_leg_outcomes(points: list[PairPoint], model: FrozenPair | None) -> tuple[list[dict], dict]:
    """Non-overlapping coarse fixed-horizon scenarios, not a two-leg OMS backtest."""
    if model is None or model.beta <= 0:
        return [], {"status": "missing_model_or_nonpositive_hedge", "scenarios": 0}
    outcomes = []
    rejected = 0
    next_decision = 0
    for index, decision in enumerate(points):
        if decision.at_us < next_decision or abs(model.zscore(decision)) < 2:
            continue
        # One-minute hypothetical delay, five-minute holding, exact contiguous grid.
        future = points[index:index + 7]
        if len(future) < 7 or any(b.at_us - a.at_us != GRID_US for a, b in zip(future, future[1:])):
            rejected += 1
            continue
        entry, exit_point = future[1], future[6]
        if any(t.at_us <= decision.at_us for t in (entry.first, entry.second)):
            rejected += 1
            continue
        if any(t.at_us <= entry.at_us for t in (exit_point.first, exit_point.second)):
            rejected += 1
            continue
        first_long = model.zscore(decision) < 0
        legs = []
        for sid, first, last, long_side, weight in (
                (PAIR[0], entry.first, exit_point.first, first_long, 1 / (1 + model.beta)),
                (PAIR[1], entry.second, exit_point.second, not first_long, model.beta / (1 + model.beta))):
            entry_price = first.ask * 1.0001 if long_side else first.bid * .9999
            exit_price = last.bid * .9999 if long_side else last.ask * 1.0001
            quantity = floor(100_000 * weight / entry_price)
            if quantity < 1 or quantity > .01 * min(first.bid_quantity_5, first.ask_quantity_5):
                break
            gross = (1 if long_side else -1) * (exit_price - entry_price) * quantity
            fees = round_trip_fees(entry_price, exit_price, quantity, long=long_side)
            legs.append({"security_id": sid, "long": long_side, "quantity": quantity,
                         "entry_price": entry_price, "exit_price": exit_price,
                         "entry_quote_us": first.at_us, "exit_quote_us": last.at_us,
                         "gross": gross, "fees": fees, "net": gross - fees})
        if len(legs) != 2:
            rejected += 1
            continue
        outcomes.append({"decision_us": decision.at_us, "entry_grid_us": entry.at_us,
                         "exit_grid_us": exit_point.at_us, "decision_z": model.zscore(decision),
                         "exit_z": model.zscore(exit_point), "legs": legs,
                         "gross": sum(leg["gross"] for leg in legs),
                         "fees": sum(leg["fees"] for leg in legs),
                         "net": sum(leg["net"] for leg in legs)})
        next_decision = exit_point.at_us + GRID_US
    return outcomes, {"status": "counterfactual_only", "scenarios": len(outcomes),
                      "rejected_scenarios": rejected,
                      "gross": sum(row["gross"] for row in outcomes),
                      "fees": sum(row["fees"] for row in outcomes),
                      "net": sum(row["net"] for row in outcomes)}
