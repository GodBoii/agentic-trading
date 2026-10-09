"""Causal one-minute variance diagnostics, independent of any trading account."""

from collections import Counter, deque
from dataclasses import dataclass
from math import isfinite, log
from statistics import fmean
from typing import Iterable

from research.intraday_lab.domain import Tick

MINUTE_US = 60_000_000
FLOOR = 1e-12
MODEL_NAMES = ("ewma_094", "ewma_097", "rolling30")


def ewma_update(previous: float, squared_return: float, decay: float) -> float:
    if (not all(isfinite(x) for x in (previous,squared_return,decay))
            or previous < 0 or squared_return < 0 or not 0 < decay < 1):
        raise ValueError("finite nonnegative variances and decay in (0,1) required")
    return decay*previous + (1-decay)*squared_return


def losses(predicted: float, observed_squared_return: float, floor: float = FLOOR) -> tuple[float,float]:
    """Gaussian QLIKE form stays defined for a zero return without flooring the target."""
    if (not all(isfinite(x) for x in (predicted,observed_squared_return,floor))
            or predicted < 0 or observed_squared_return < 0 or floor <= 0):
        raise ValueError("finite nonnegative variance/target and positive floor required")
    prediction = max(predicted,floor)
    return (prediction-observed_squared_return)**2, log(prediction)+observed_squared_return/prediction


@dataclass(frozen=True)
class MinuteBar:
    minute: int
    security_id: int
    close: float
    first_us: int
    last_us: int
    valid: bool

    def __post_init__(self) -> None:
        if (self.minute <= 0 or self.security_id <= 0 or not isfinite(self.close) or self.close < 0
                or self.valid and self.close <= 0
                or not self.minute*MINUTE_US <= self.first_us <= self.last_us < self.end_us):
            raise ValueError("valid price, identity and receipt positions within the minute required")

    @property
    def end_us(self) -> int:
        return (self.minute+1)*MINUTE_US


@dataclass(frozen=True)
class Forecast:
    security_id: int
    at_us: int
    training_last_received_us: int
    target_minute: int
    values: dict[str,float]


class VarianceModel:
    def __init__(self, *, warmup: int = 30, variance_floor: float = FLOOR):
        if warmup != 30 or not isfinite(variance_floor) or variance_floor <= 0:
            raise ValueError("frozen thirty-return warmup and positive floor required")
        self.floor = variance_floor
        self.previous: MinuteBar | None = None
        self.squares: deque[float] = deque(maxlen=30)
        self.ewma: dict[str,float] = {}
        self.pending: Forecast | None = None
        self.counts: Counter[str] = Counter()

    def on_bar(self, bar: MinuteBar) -> dict | None:
        if self.previous is not None and bar.minute <= self.previous.minute:
            raise ValueError("bars must strictly increase for one instrument")
        if self.previous is not None and bar.security_id != self.previous.security_id:
            raise ValueError("one variance model handles one instrument")
        self.counts["bars"] += 1
        previous = self.previous
        self.previous = bar
        if (not bar.valid or previous is None or not previous.valid
                or bar.minute != previous.minute+1):
            self.squares.clear(); self.ewma.clear(); self.pending = None
            self.counts["invalid_gap_or_start_reset"] += 1
            return None
        squared = (log(bar.close)-log(previous.close))**2
        result = None
        if self.pending is not None:
            if self.pending.target_minute != bar.minute:
                raise ValueError("forecast target does not match next completed minute")
            result = {"security_id":bar.security_id,"forecast_us":self.pending.at_us,
                      "training_last_received_us":self.pending.training_last_received_us,
                      "outcome_minute":bar.minute,"outcome_available_us":bar.end_us,
                      "squared_log_return":squared,"forecasts":dict(self.pending.values)}
            self.counts["forecast_outcome_pairs"] += 1
            self.counts["zero_outcomes"] += squared == 0
        self.squares.append(squared)
        if len(self.squares) < 30:
            self.pending = None
            self.counts["warming_returns"] += 1
            return result
        if not self.ewma:
            seed = fmean(self.squares)
            self.ewma = {"ewma_094":seed,"ewma_097":seed}
        else:
            self.ewma["ewma_094"] = ewma_update(self.ewma["ewma_094"],squared,.94)
            self.ewma["ewma_097"] = ewma_update(self.ewma["ewma_097"],squared,.97)
        values = {**self.ewma,"rolling30":fmean(self.squares)}
        values = {name:max(value,self.floor) for name,value in values.items()}
        self.pending = Forecast(bar.security_id,bar.end_us,bar.last_us,bar.minute+1,values)
        self.counts["forecasts_created"] += 1
        return result


def completed_minutes(ticks: Iterable[Tick], *, receipt_proxy: bool = False,
                      maximum_gap_seconds: float = 15) -> tuple[list[MinuteBar],dict]:
    """Offline clock-boundary closes. Only receipts strictly before each boundary enter a bar."""
    if not isfinite(maximum_gap_seconds) or maximum_gap_seconds <= 0:
        raise ValueError("positive finite receipt-gap limit required")
    maximum_gap_us = int(maximum_gap_seconds*1_000_000)
    states: dict[int,dict] = {}
    output = []
    counts: Counter[str] = Counter()
    last_stream_us = 0

    def finish(state: dict) -> None:
        complete = state["valid"] and (state["minute"]+1)*MINUTE_US-state["last_us"] <= maximum_gap_us
        output.append(MinuteBar(state["minute"],state["security_id"],state["close"],
                                state["first_us"],state["last_us"],complete))
        counts["valid_minutes" if complete else "invalid_minutes"] += 1

    for tick in ticks:
        if tick.at_us < last_stream_us:
            raise ValueError("receipt stream must be ordered")
        last_stream_us = tick.at_us
        counts["observations"] += 1
        usable = tick.usable(5,receipt_proxy=receipt_proxy)
        counts["usable_observations"] += usable
        minute = tick.at_us//MINUTE_US
        state = states.get(tick.security_id)
        if state is not None and tick.at_us <= state["last_us"]:
            raise ValueError("instrument receipt timestamps must strictly increase")
        continuity = state is None or tick.at_us-state["last_us"] <= maximum_gap_us
        if state is None or state["minute"] != minute:
            if state is not None:
                finish(state)
            states[tick.security_id] = {"minute":minute,"security_id":tick.security_id,
                                       "first_us":tick.at_us,"last_us":tick.at_us,
                                       "close":tick.midpoint if tick.midpoint > 0 else tick.last,
                                       "valid":usable and continuity and tick.at_us-minute*MINUTE_US <= maximum_gap_us}
        else:
            state["valid"] = state["valid"] and usable and continuity
            state["last_us"] = tick.at_us
            if tick.midpoint > 0:
                state["close"] = tick.midpoint
    # A source ending before a bar boundary cannot establish that the minute closed.
    for state in states.values():
        if (state["minute"]+1)*MINUTE_US <= last_stream_us:
            finish(state)
        else:
            counts["unclosed_final_minutes"] += 1
    output.sort(key=lambda bar:(bar.minute,bar.security_id))
    return output,dict(counts)
