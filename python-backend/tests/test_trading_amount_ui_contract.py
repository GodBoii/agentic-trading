from pathlib import Path
import unittest


class TradingAmountUIContractTests(unittest.TestCase):
    def test_amount_only_ui_has_save_and_no_manual_start_controls(self):
        source = (Path(__file__).parents[2] / "components" / "trading-status.tsx").read_text(encoding="utf-8")
        self.assertIn('aria-label="Trading amount in rupees"', source)
        self.assertIn("Auto: available balance", source)
        self.assertIn("Auto splits your available margin", source)
        self.assertIn("Margin per trade", source)
        self.assertIn("saving does not start a scan", source)
        self.assertNotIn("Start trading", source)
        self.assertNotIn("startAITrading", source)
        self.assertNotIn("tradeMode", source)
        self.assertNotIn("Regime Analysis", source)

    def test_frontend_uses_config_api_not_manual_toggle_post(self):
        source = (Path(__file__).parents[2] / "components" / "trading-status.tsx").read_text(encoding="utf-8")
        self.assertIn("/api/ai-trading/config", source)
        self.assertNotIn("/api/ai-trading/toggle", source)

    def test_config_api_rejects_non_finite_and_non_positive_amounts(self):
        source = (Path(__file__).parents[2] / "app" / "api" / "ai-trading" / "config" / "route.ts").read_text(encoding="utf-8")
        self.assertIn("Number.isFinite(amount) && amount > 0", source)
        self.assertIn("status: 400", source)
        self.assertIn("const automatic =", source)
        self.assertIn("automatic ? 'auto' : 'manual'", source)
        self.assertIn("amount_updated_at_utc", source)


if __name__ == "__main__":
    unittest.main()
