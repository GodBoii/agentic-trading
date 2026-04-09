import time

from pipeline.config import PipelineConfig
from pipeline.regime.regime_analyzer import MarketRegimeAnalyzer


def main() -> None:
    config = PipelineConfig()
    analyzer = MarketRegimeAnalyzer(config)

    print("=" * 60)
    print("REGIME ORCHESTRATOR")
    print("=" * 60)
    print(f"Regime loop interval: {config.regime_loop_interval_seconds} seconds")

    while True:
        try:
            print("\nStarting regime cycle...")
            analyzer.run()
        except Exception as exc:  # pragma: no cover - runtime safety
            print(f"Regime loop error: {exc}")
        print(
            f"Sleeping for {config.regime_loop_interval_seconds} seconds before next regime cycle..."
        )
        time.sleep(config.regime_loop_interval_seconds)


if __name__ == "__main__":
    main()
