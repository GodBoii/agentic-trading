"""Frozen prior-session slot estimates, with no evaluation-day fitting."""

from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import fmean
from types import MappingProxyType
from typing import Iterable, Mapping

from research.intraday_lab.domain import PolicyConfig, Side, Signal, Tick, session_second

OPEN_SECOND = 9 * 3600 + 15 * 60
SLOT_SECONDS = 1800
SLOT_COUNT = 12
VARIANTS = ("same_slot_mean", "same_slot_unanimous_sign")


def day_of(tick: Tick) -> str:
    # UTC epoch plus fixed IST offset, independent of host timezone.
    return datetime.fromtimestamp(tick.at_us / 1_000_000 + 19_800, timezone.utc).date().isoformat()


def slot_of(tick: Tick) -> tuple[int, float]:
    elapsed = session_second(tick.at_us) - OPEN_SECOND
    return elapsed // SLOT_SECONDS, elapsed % SLOT_SECONDS + tick.at_us % 1_000_000 / 1_000_000


@dataclass(frozen=True, slots=True)
class SlotEstimate:
    returns_bps: tuple[float, ...]

    @property
    def mean_bps(self) -> float:
        return fmean(self.returns_bps)


@dataclass(frozen=True, slots=True)
class SlotModel:
    training_dates: tuple[str, ...]
    mode: str
    estimates: Mapping[tuple[int, int], SlotEstimate]


def fit_model(sessions: Mapping[str, Iterable[Tick]], mode: str) -> tuple[SlotModel, dict]:
    if len(sessions) != 3 or mode not in {"recent_trade", "receipt_proxy"}:
        raise ValueError("exactly three frozen training sessions and a known freshness mode required")
    values: dict[tuple[int, int], list[float]] = {}
    counts = {"observed_slots": 0, "complete_slots": 0, "rejected_slots": 0}
    for day in sorted(sessions):
        buckets: dict[tuple[int, int], list[Tick]] = {}
        for tick in sessions[day]:
            if day_of(tick) != day:
                raise ValueError("training observation date disagrees with declared session")
            slot, _ = slot_of(tick)
            if 0 <= slot < SLOT_COUNT:
                buckets.setdefault((tick.security_id, slot), []).append(tick)
        for key, ticks in buckets.items():
            counts["observed_slots"] += 1
            offsets = [slot_of(t)[1] for t in ticks]
            valid = (len(ticks) >= 60 and offsets[0] <= 10 and offsets[-1] >= 1790
                     and all(t.usable(5, receipt_proxy=mode == "receipt_proxy") for t in ticks)
                     and all(0 < b.at_us - a.at_us <= 15_000_000 for a, b in zip(ticks, ticks[1:])))
            if not valid:
                counts["rejected_slots"] += 1
                continue
            counts["complete_slots"] += 1
            values.setdefault(key, []).append((ticks[-1].midpoint / ticks[0].midpoint - 1) * 10_000)
    estimates = {key: SlotEstimate(tuple(returns)) for key, returns in values.items() if len(returns) == 3}
    model = SlotModel(tuple(sorted(sessions)), mode, MappingProxyType(estimates))
    records = [{"security_id": sid, "slot": slot, "returns_bps": list(estimate.returns_bps),
                "mean_bps": estimate.mean_bps} for (sid, slot), estimate in sorted(estimates.items())]
    return model, {"training_dates": list(model.training_dates), "freshness_mode": mode,
                   "coverage_counts": counts, "three_session_estimates": len(estimates),
                   "records": records}


def model_from_report(report: dict) -> SlotModel:
    dates = tuple(report["training_dates"])
    if len(dates) != 3 or dates != tuple(sorted(set(dates))):
        raise ValueError("model training dates must be three distinct ordered dates")
    mode = report["freshness_mode"]
    if mode not in {"recent_trade", "receipt_proxy"}:
        raise ValueError("unknown model freshness mode")
    estimates = {}
    for record in report["records"]:
        key = int(record["security_id"]), int(record["slot"])
        returns = tuple(float(x) for x in record["returns_bps"])
        if len(returns) != 3 or key in estimates:
            raise ValueError("model requires three returns per unique instrument/slot")
        estimates[key] = SlotEstimate(returns)
    return SlotModel(dates, mode, MappingProxyType(estimates))


class SeasonalityPolicy:
    def __init__(self, config: PolicyConfig, model: SlotModel):
        if config.name not in VARIANTS or model.mode != config.freshness_mode:
            raise ValueError("variant/freshness must match frozen model")
        self.config = config
        self.model = model
        self.seen: set[tuple[int, int]] = set()

    def on_tick(self, tick: Tick) -> tuple[Signal | None, str]:
        if day_of(tick) <= self.model.training_dates[-1]:
            raise ValueError("evaluation must strictly follow every training session")
        slot, offset = slot_of(tick)
        if not 1 <= slot <= 10:
            return None, "outside_entry_slots"
        key = tick.security_id, slot
        if key in self.seen:
            return None, "between_evaluations"
        self.seen.add(key)
        if offset > 10:
            return None, "late_slot_start"
        if not tick.usable(self.config.maximum_trade_age_seconds,
                           receipt_proxy=self.config.freshness_mode == "receipt_proxy"):
            return None, "unusable_observation"
        if tick.spread_bps > self.config.maximum_spread_bps:
            return None, "spread"
        estimate = self.model.estimates.get(key)
        if estimate is None:
            return None, "insufficient_prior_sessions"
        mean = estimate.mean_bps
        if abs(mean) < 10:
            return None, "small_prior_mean"
        side = Side.LONG if mean > 0 else Side.SHORT
        if self.config.name == "same_slot_unanimous_sign" and any(side.sign * value <= 0 for value in estimate.returns_bps):
            return None, "prior_sign_disagreement"
        return Signal(tick.at_us, tick.security_id, side, tick.midpoint, mean,
                      float(sum(side.sign * value > 0 for value in estimate.returns_bps))), "signal"
