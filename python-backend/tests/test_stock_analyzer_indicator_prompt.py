from __future__ import annotations

import unittest

from pipeline.analyzer.stock_analyzer_agent import StockAnalyzerAgent


class StockAnalyzerIndicatorPromptTests(unittest.TestCase):
    def test_prompt_treats_indicator_event_as_attention_not_trade_instruction(self) -> None:
        agent = StockAnalyzerAgent.__new__(StockAnalyzerAgent)
        prompt = agent._build_prompt(
            {
                "symbol": "TEST",
                "security_id": 1,
                "setup_type": "INDICATOR_EVENT",
                "direction": "MIXED",
                "setup_score": 72,
                "event_trigger_rule": "one_or_more_new_indicator_events",
                "indicator_events": [
                    {"event_type": "BULLISH_ENGULFING", "direction": "LONG"},
                    {"event_type": "SHOOTING_STAR", "direction": "SHORT"},
                ],
                "indicator_snapshot": {"rsi": 50.0},
                "recent_closed_bars": [{"close": 100.0}],
            }
        )
        self.assertIn("supplies no trade recommendation", prompt)
        self.assertNotIn("MIXED", prompt)
        self.assertNotIn("BULLISH_ENGULFING", prompt)
        self.assertNotIn("setup_score", prompt)
        self.assertIn("Recent Objective Evidence", prompt)


if __name__ == "__main__":
    unittest.main()
