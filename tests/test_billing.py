"""Stripe checkout shape: monthly plans carry the advertised 14-day trial,
while the one-time Lifetime plan must not be sold as a subscription."""

import pathlib
import tempfile
import unittest

from memory_box import web


class BillingCheckoutTests(unittest.TestCase):
    def _billing(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        gate = web.Gate(pathlib.Path(tmp.name))
        env = {
            "STRIPE_SECRET_KEY": "sk_test_x",
            "STRIPE_WEBHOOK_SECRET": "whsec_test",
            "STRIPE_PRICES": "personal=price_p,lifetime=price_l",
            "PUBLIC_URL": "https://example.test",
        }
        billing = web.Billing(pathlib.Path(tmp.name), gate, env)
        sent = {}
        billing._stripe = lambda path, form: sent.update(form) or {"url": "https://checkout.test/s"}
        return billing, sent

    def test_monthly_checkout_has_14_day_trial(self):
        billing, sent = self._billing()
        self.assertEqual(billing.checkout("personal"), "https://checkout.test/s")
        self.assertEqual(sent["mode"], "subscription")
        self.assertEqual(sent["subscription_data[trial_period_days]"], "14")

    def test_lifetime_checkout_is_a_one_time_payment(self):
        billing, sent = self._billing()
        billing.checkout("lifetime")
        self.assertEqual(sent["mode"], "payment")
        self.assertNotIn("subscription_data[trial_period_days]", sent)


if __name__ == "__main__":
    unittest.main()
