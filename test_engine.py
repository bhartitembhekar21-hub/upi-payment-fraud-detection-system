import os
import unittest
import engine

class TestUPIShieldEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.environ["UPI_SHIELD_DB"] = "test_upi_shield.db"
        engine.DB_PATH = "test_upi_shield.db"
        engine.init_db(force_reset=True)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists("test_upi_shield.db"):
            os.remove("test_upi_shield.db")

    def test_01_normal_payment_settlement(self):
        """1. A normal payment to a merchant settles and balances change."""
        sender = "student@upi"
        payee = "chai_point@upi"
        amt = 100.0

        conn = engine.get_db_connection()
        s_init = conn.execute("SELECT balance FROM accounts WHERE vpa = ?", (sender,)).fetchone()["balance"]
        conn.close()

        inv = engine.investigate(
            amount=amt, sender_vpa=sender, receiver_vpa=payee,
            city="Nagpur", device_id="TEST_DEV_1"
        )
        self.assertEqual(inv["tier"], "CLEARED")

        utr, status = engine.record_transaction(sender, payee, amt, "Nagpur", "TEST_DEV_1", inv)
        self.assertEqual(status, "SUCCESS")

        conn = engine.get_db_connection()
        s_after = conn.execute("SELECT balance FROM accounts WHERE vpa = ?", (sender,)).fetchone()["balance"]
        conn.close()

        self.assertAlmostEqual(s_init - s_after, amt)

    def test_02_repeat_payment_avoids_new_payee(self):
        """2. A repeat payment to the same merchant does not raise NEW_PAYEE."""
        sender = "student@upi"
        payee = "chai_point@upi"
        inv = engine.investigate(
            amount=50.0, sender_vpa=sender, receiver_vpa=payee,
            city="Nagpur", device_id="TEST_DEV_1"
        )
        self.assertNotIn("NEW_PAYEE", inv["flags"])

    def test_03_new_device_otp_workflow(self):
        """3. Payment from a new device triggers OTP hold; wrong OTP fails; 3 wrong attempts cancels it."""
        sender = "student@upi"
        payee = "bigbasket@upi"
        amt = 200.0

        inv = engine.investigate(
            amount=amt, sender_vpa=sender, receiver_vpa=payee,
            city="Nagpur", device_id="UNRECOGNIZED_DEV_99"
        )
        self.assertEqual(inv["tier"], "PENDING_OTP")
        self.assertIn("NEW_DEVICE", inv["flags"])

        utr, status = engine.record_transaction(sender, payee, amt, "Nagpur", "UNRECOGNIZED_DEV_99", inv)
        self.assertEqual(status, "PENDING_OTP")

        otp = engine.create_otp_challenge(utr, "UNRECOGNIZED_DEV_99", sender)
        self.assertEqual(len(otp), 4)

        # 1st wrong attempt
        ok, _ = engine.verify_otp_challenge(utr, "0000")
        self.assertFalse(ok)

        # 2nd wrong attempt
        ok, _ = engine.verify_otp_challenge(utr, "0000")
        self.assertFalse(ok)

        # 3rd wrong attempt -> Blocks
        ok, msg = engine.verify_otp_challenge(utr, "0000")
        self.assertFalse(ok)

        conn = engine.get_db_connection()
        tx = conn.execute("SELECT status FROM transactions WHERE utr = ?", (utr,)).fetchone()
        conn.close()
        self.assertEqual(tx["status"], "BLOCKED")

    def test_04_scam_vpa_blocked(self):
        """4. claim-refund@fakebank is blocked and nothing is debited."""
        sender = "student@upi"
        payee = "claim-refund@fakebank"
        amt = 500.0

        conn = engine.get_db_connection()
        s_init = conn.execute("SELECT balance FROM accounts WHERE vpa = ?", (sender,)).fetchone()["balance"]
        conn.close()

        inv = engine.investigate(
            amount=amt, sender_vpa=sender, receiver_vpa=payee,
            city="Nagpur", device_id="TEST_DEV_1"
        )
        self.assertEqual(inv["tier"], "BLOCKED")
        self.assertIn("SUSPICIOUS_VPA", inv["flags"])

        utr, status = engine.record_transaction(sender, payee, amt, "Nagpur", "TEST_DEV_1", inv)
        self.assertEqual(status, "BLOCKED")

        conn = engine.get_db_connection()
        s_after = conn.execute("SELECT balance FROM accounts WHERE vpa = ?", (sender,)).fetchone()["balance"]
        conn.close()

        self.assertEqual(s_init, s_after)

    def test_05_beneficiary_lien_enforcement(self):
        """5. After a lien is placed, a later payment to that VPA is blocked."""
        payee = "untrusted.merchant@upi"
        engine.place_beneficiary_lien(payee, "Confirmed fraudulent scheme")

        inv = engine.investigate(
            amount=100.0, sender_vpa="salaried@upi", receiver_vpa=payee,
            city="Nagpur", device_id="TEST_DEV_1"
        )
        self.assertEqual(inv["tier"], "BLOCKED")
        self.assertIn("LIENED_BENEFICIARY", inv["flags"])

    def test_06_impossible_speed_kinematics(self):
        """6. A far-away city soon after a payment triggers IMPOSSIBLE_SPEED."""
        sender = "kirana@upi"
        
        # Settle first transaction in Nagpur
        inv1 = engine.investigate(100.0, sender, "chai_point@upi", "Nagpur", "TEST_DEV_KIRANA")
        engine.record_transaction(sender, "chai_point@upi", 100.0, "Nagpur", "TEST_DEV_KIRANA", inv1)

        # Settle immediate second transaction in Delhi (Displacement ~850 km, gap ~0 sec)
        inv2 = engine.investigate(100.0, sender, "chai_point@upi", "Delhi", "TEST_DEV_KIRANA")
        self.assertIn("IMPOSSIBLE_SPEED", inv2["flags"])
        self.assertEqual(inv2["tier"], "BLOCKED")

    def test_07_qr_generation_and_decoding(self):
        """7. A generated QR decodes back to the identical UPI link; garbage gives errors."""
        img, link = engine.generate_upi_qr("city.mart@upi", "City Mart", 450.0)
        
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        raw_bytes = buf.getvalue()

        decoded_text, err = engine.decode_qr_image(raw_bytes)
        self.assertIsNone(err)
        self.assertEqual(decoded_text, link)

        valid, parsed, _ = engine.parse_upi_uri(decoded_text)
        self.assertTrue(valid)
        self.assertEqual(parsed["receiver_vpa"], "city.mart@upi")
        self.assertEqual(parsed["amount"], 450.0)

        # Non-UPI link test
        valid_bad, _, _ = engine.parse_upi_uri("https://google.com")
        self.assertFalse(valid_bad)

if __name__ == "__main__":
    unittest.main()
