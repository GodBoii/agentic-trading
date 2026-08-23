from __future__ import annotations

import os
import signal
from threading import Event


def _enabled() -> bool:
    return os.getenv("NIFTY_DEPTH_MONITOR_ENABLED", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


def _park_while_disabled() -> None:
    stop_event = Event()

    def _stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    print(
        "NIFTY 50 market-depth collector is disabled by "
        "NIFTY_DEPTH_MONITOR_ENABLED=0. The container is parked.",
        flush=True,
    )
    while not stop_event.wait(300):
        pass


def main() -> None:
    if not _enabled():
        _park_while_disabled()
        return

    # Keep pandas, matplotlib, PyArrow and the Dhan feed SDK out of the parked
    # process. They are imported only when the collector gate is enabled.
    from pipeline.config import PipelineConfig
    from pipeline.services.nifty_depth_monitor import NiftyDepthMonitor

    print("NIFTY 50 MARKET DEPTH")
    NiftyDepthMonitor(PipelineConfig()).run()


if __name__ == "__main__":
    main()
