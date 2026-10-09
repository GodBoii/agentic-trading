"""Explicit no-trade control for execution-assumption sensitivity research."""

from research.intraday_lab.domain import Signal, Tick


class NoTradePolicy:
    def on_tick(self, tick: Tick) -> tuple[Signal | None, str]:
        return None, "no_trade_control"
