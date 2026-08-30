from __future__ import annotations

import unittest
import sys
import types
from datetime import datetime, timedelta

if "dhanhq" not in sys.modules:
    fake_dhan = types.ModuleType("dhanhq")
    fake_dhan.MarketFeed = type("MarketFeed", (), {"NSE": "NSE", "BSE": "BSE", "Full": "Full"})
    fake_dhan.DhanContext = type("DhanContext", (), {})
    fake_dhan.HistoricalData = type("HistoricalData", (), {})
    fake_dhan.OptionChain = type("OptionChain", (), {})
    fake_dhan.FullDepth = type("FullDepth", (), {})
    fake_dhan.dhanhq = type("dhanhq", (), {})
    sys.modules["dhanhq"] = fake_dhan

from pipeline.config import PipelineConfig
from pipeline.research.opportunity_replay import replay_opportunities


class OpportunityReplayTests(unittest.TestCase):
    def test_replay_uses_production_ranker_and_opening_setup(self) -> None:
        start = datetime.fromisoformat("2026-08-28T09:15:00+05:30")
        stock = {
            "isin": "INE1",
            "exchange_segment": "NSE_EQ",
            "security_id": 1,
            "symbol": "TEST",
            "historical": {"previous_close": 100.0, "atr_percent": 2.0, "adv_20_cr": 10.0},
        }
        rows = []
        for second in range(45):
            price = 100.0 + second * 0.02
            rows.append(
                {
                    "received_at": (start + timedelta(seconds=second)).isoformat(),
                    "packet": {
                        "exchange_segment": 1,
                        "security_id": 1,
                        "LTP": price,
                        "LTT": (start + timedelta(seconds=second)).strftime("%H:%M:%S"),
                        "volume": 1000 + second * 100,
                        "avg_price": 100.2,
                        "close": 100.0,
                        "depth": [
                            {
                                "bid_price": price - 0.01,
                                "ask_price": price + 0.01,
                                "bid_quantity": 1000,
                                "ask_quantity": 1000,
                                "bid_orders": 10,
                                "ask_orders": 10,
                            }
                            for _ in range(5)
                        ],
                    },
                }
            )

        result = replay_opportunities(
            stocks=[stock],
            rows=rows,
            config=PipelineConfig(
                intra_finder_hot_set_size=1,
                intra_finder_hot_reserve_size=1,
            ),
        )

        self.assertGreater(result["rank_evaluations"], 1)
        self.assertTrue(any(event["setup_type"] == "OPENING_DRIVE" for event in result["events"]))


if __name__ == "__main__":
    unittest.main()
