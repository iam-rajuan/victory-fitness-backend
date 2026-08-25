import unittest

from app.revenue_service import (
    build_referral_code,
    compute_marketplace_platform_fee,
    referral_legend_unlocked,
    referral_share_pct_for_count,
)


class RevenueServiceTests(unittest.TestCase):
    def test_marketplace_platform_fee_is_twenty_percent(self) -> None:
        self.assertEqual(compute_marketplace_platform_fee(100.0), 20.0)
        self.assertEqual(compute_marketplace_platform_fee(29.99), 6.0)

    def test_referral_legend_threshold_unlocks_at_eleven(self) -> None:
        self.assertFalse(referral_legend_unlocked(10))
        self.assertTrue(referral_legend_unlocked(11))
        self.assertEqual(referral_share_pct_for_count(10), 0)
        self.assertEqual(referral_share_pct_for_count(11), 20)

    def test_referral_code_uses_name_and_identifier(self) -> None:
        code = build_referral_code({"_id": "66cafe123456", "name": "Victor Akko"})
        self.assertEqual(code, "VICTOR-123456")


if __name__ == "__main__":
    unittest.main()
