from __future__ import annotations

import unittest

from pipeline.services.corporate_action_service import (
    CorporateActionService,
    action_for_stock,
    action_index,
)


class CorporateActionServiceTests(unittest.TestCase):
    def test_split_disables_gap_reference_without_ai(self) -> None:
        action = CorporateActionService._normalize(
            {
                "symbol": "ABC",
                "subject": "Stock Split From Rs.10 to Rs.2",
                "exDate": "28-Aug-2026",
                "recDate": "29-Aug-2026",
            },
            "NSE",
        )

        self.assertIsNotNone(action)
        self.assertTrue(action["price_reference_unsafe"])
        self.assertTrue(action["gap_setup_disabled"])

    def test_action_matches_verified_exchange_symbol(self) -> None:
        payload = {
            "actions": [
                {
                    "exchange": "NSE",
                    "symbol": "ABC",
                    "isin": "",
                    "ex_date": "2026-08-28",
                    "purpose": "Dividend - Rs 2",
                }
            ]
        }

        matched = action_for_stock(
            action_index(payload),
            {"exchange": "NSE", "symbol": "ABC", "isin": "INE1"},
        )

        self.assertEqual(matched["purpose"], "Dividend - Rs 2")

    def test_bse_action_matches_security_id(self) -> None:
        payload = {
            "actions": [
                {
                    "exchange": "BSE",
                    "symbol": "500001",
                    "security_id": "500001",
                    "isin": "",
                    "ex_date": "2026-08-28",
                    "purpose": "Bonus 1:1",
                }
            ]
        }

        matched = action_for_stock(
            action_index(payload),
            {"exchange": "BSE", "security_id": 500001, "symbol": "ABC"},
        )

        self.assertEqual(matched["purpose"], "Bonus 1:1")


if __name__ == "__main__":
    unittest.main()
