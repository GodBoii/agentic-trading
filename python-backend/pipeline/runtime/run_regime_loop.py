import time
from datetime import datetime, time as dt_time, timedelta
from typing import Optional

from pipeline.config import PipelineConfig
from pipeline.regime.regime_analyzer import MarketRegimeAnalyzer
from pipeline.services.market_time_service import MarketTimeService


def _parse_schedule_time(value: str) -> dt_time:
    hour, minute = value.split(":", 1)
    return dt_time(int(hour), int(minute))


def _next_run_time(market_time: MarketTimeService, last_run_date: Optional[str], last_run_slot: Optional[str]) -> datetime:
    now = market_time.now()
    today = now.date()
    slots = [(slot, _parse_schedule_time(slot)) for slot in market_time.config.regime_schedule_times]
    missed_slots = [slot for slot in slots if now.time() >= slot[1]]

    if missed_slots and last_run_date != today.isoformat():
        return now

    for slot, slot_time in slots:
        if now.time() < slot_time:
            return datetime.combine(today, slot_time, tzinfo=market_time.tz)
        if last_run_date == today.isoformat() and last_run_slot == slot:
            continue

    tomorrow = today + timedelta(days=1)
    return datetime.combine(tomorrow, slots[0][1], tzinfo=market_time.tz)


def _slot_for_now(config: PipelineConfig, market_time: MarketTimeService) -> str:
    now_time = market_time.now().time()
    elapsed = [slot for slot in config.regime_schedule_times if now_time >= _parse_schedule_time(slot)]
    return elapsed[-1] if elapsed else config.regime_schedule_times[0]


def _sleep_until(market_time: MarketTimeService, wake_at: datetime) -> None:
    while True:
        remaining_seconds = (wake_at - market_time.now()).total_seconds()
        if remaining_seconds <= 0:
            return
        time.sleep(remaining_seconds)


def main() -> None:
    config = PipelineConfig()
    analyzer = MarketRegimeAnalyzer(config)
    market_time = MarketTimeService(config)
    last_run_date: Optional[str] = None
    last_run_slot: Optional[str] = None

    print("=" * 60)
    print("REGIME ORCHESTRATOR")
    print("=" * 60)
    print(f"Regime schedule: {', '.join(config.regime_schedule_times)} {config.market_timezone}")

    while True:
        next_run_at = _next_run_time(market_time, last_run_date, last_run_slot)
        sleep_seconds = max(0.0, (next_run_at - market_time.now()).total_seconds())
        if sleep_seconds > 0:
            print(f"Next regime cycle at {next_run_at.strftime('%Y-%m-%d %H:%M:%S %Z')}.")
            _sleep_until(market_time, next_run_at)
            continue

        try:
            print("\nStarting regime cycle...")
            analyzer.run()
            last_run_date = market_time.now().date().isoformat()
            last_run_slot = _slot_for_now(config, market_time)
        except Exception as exc:  # pragma: no cover - runtime safety
            print(f"Regime loop error: {exc}")
            time.sleep(60)


if __name__ == "__main__":
    main()
