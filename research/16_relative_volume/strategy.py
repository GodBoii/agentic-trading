"""Completed-minute incremental RVOL; same-time baseline fixed on development only."""

from dataclasses import dataclass
from statistics import mean

from research.intraday_lab.domain import PolicyConfig, Side, Signal, Tick

MINUTE = 60_000_000


@dataclass(frozen=True)
class VolumeBar:
    security_id: int
    minute: int
    available_us: int
    volume: float
    move_bps: float

    @property
    def time_of_day(self) -> int:
        return (self.minute + 330) % 1440


def completed_bars(ticks: list[Tick], volumes: dict, config: PolicyConfig) -> tuple[list[VolumeBar], dict]:
    groups = {}
    bars = []
    resets = rejected = 0
    for tick in ticks:
        state = groups.setdefault(tick.security_id, {"minute": None, "items": [], "anchor": None,
                                                     "valid": True, "last_volume": None})
        value = volumes.get((tick.security_id, tick.at_us))
        minute = tick.at_us // MINUTE
        if state["minute"] is not None and minute != state["minute"]:
            items, anchor = state["items"], state["anchor"]
            start = state["minute"] * MINUTE
            if (state["valid"] and anchor is not None and len(items) >= 40 and
                    start - anchor[0].at_us <= 2_000_000 and
                    items[-1][0].at_us >= start + 58_000_000 and
                    tick.at_us <= start + 62_000_000):
                increment = items[-1][1] - anchor[1]
                if increment >= 0:
                    bars.append(VolumeBar(tick.security_id, state["minute"], tick.at_us, increment,
                                          (items[-1][0].midpoint / anchor[0].midpoint - 1) * 10000))
            else:
                rejected += 1
            state["anchor"] = items[-1] if items and state["valid"] else None
            state["items"] = []
            state["valid"] = True
        state["minute"] = minute
        valid = value is not None and tick.usable(config.maximum_trade_age_seconds,
                      receipt_proxy=config.freshness_mode == "receipt_proxy")
        if value is not None and state["last_volume"] is not None and value < state["last_volume"]:
            resets += 1
            valid = False
        if state["items"] and tick.at_us - state["items"][-1][0].at_us > 15_000_000:
            valid = False
        if not valid:
            state["valid"] = False
        if value is not None:
            state["items"].append((tick, value))
            state["last_volume"] = value
    return bars, {"bars": len(bars), "cumulative_resets": resets, "rejected_minutes": rejected,
                  "end_of_file_partial_minutes": len(groups)}


def fit_baseline(sessions: dict[str, list[VolumeBar]]) -> dict[tuple[int, int], float]:
    observations = {}
    for bars in sessions.values():
        for bar in bars:
            observations.setdefault((bar.security_id, bar.time_of_day), []).append(bar.volume)
    return {key: mean(values) for key, values in observations.items()
            if len(values) >= 3 and mean(values) > 0}


class RelativeVolumePolicy:
    def __init__(self, config: PolicyConfig, bars: list[VolumeBar], baseline: dict, method: str):
        if method not in {"continuation", "climax_reversal"}:
            raise ValueError("unknown RVOL hypothesis")
        self.config = config
        self.events = {(b.security_id, b.available_us): b for b in bars}
        self.baseline = dict(baseline)
        self.method = method
        self.previous = {}

    def on_tick(self, tick: Tick) -> tuple[Signal | None, str]:
        bar = self.events.get((tick.security_id, tick.at_us))
        if bar is None:
            return None, "between_completed_minutes"
        if not tick.usable(self.config.maximum_trade_age_seconds,
                           receipt_proxy=self.config.freshness_mode == "receipt_proxy"):
            self.previous.pop(tick.security_id, None)
            return None, "unusable_observation"
        if tick.spread_bps > self.config.maximum_spread_bps:
            return None, "spread"
        expected = self.baseline.get((bar.security_id, bar.time_of_day))
        previous = self.previous.get(tick.security_id)
        self.previous[tick.security_id] = bar
        if expected is None:
            return None, "insufficient_three_day_baseline"
        ratio = bar.volume / expected
        if self.method == "continuation":
            if ratio < 2 or abs(bar.move_bps) < 5:
                return None, "volume_or_move"
            side = Side.LONG if bar.move_bps > 0 else Side.SHORT
        else:
            if previous is None or previous.minute + 1 != bar.minute:
                return None, "warming_confirmation"
            old_expected = self.baseline.get((previous.security_id, previous.time_of_day))
            if (old_expected is None or previous.volume / old_expected < 3 or
                    abs(previous.move_bps) < 10 or bar.move_bps * previous.move_bps >= 0 or abs(bar.move_bps) < 3):
                return None, "no_climax_reversal"
            side = Side.LONG if bar.move_bps > 0 else Side.SHORT
        return Signal(tick.at_us, tick.security_id, side, tick.midpoint, bar.move_bps, ratio), "signal"
