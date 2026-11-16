import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from task1_username_hash import make_hash
from task2_salt_pepper import (
    hash_password,
    hash_password_pbkdf2,
    load_db,
    register_user,
    save_db,
    verify_user,
)


class TestLab09Hashing(unittest.TestCase):
    def setUp(self):
        self.old_pepper = os.environ.get("PASSWORD_PEPPER")
        self.test_pepper = "unit-test-secret-pepper-98765"
        os.environ["PASSWORD_PEPPER"] = self.test_pepper

        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "users.json"

    def tearDown(self):
        self.temp_dir.cleanup()
        if self.old_pepper is None:
            os.environ.pop("PASSWORD_PEPPER", None)
        else:
            os.environ["PASSWORD_PEPPER"] = self.old_pepper

    def test_1_task1_username_and_password_hash(self):
        """Task-1: alice and bob get different 128-hex-char SHA-512 hashes for the same password."""
        h_alice_1 = make_hash("alice", "Test@1234")
        h_alice_2 = make_hash("alice", "Test@1234")
        h_bob = make_hash("bob", "Test@1234")

        self.assertEqual(h_alice_1, h_alice_2)
        self.assertNotEqual(h_alice_1, h_bob)
        self.assertEqual(len(h_alice_1), 128)
        int(h_alice_1, 16)  # confirms valid hexadecimal characters

    def test_2_task2_same_password_different_salts_and_hashes(self):
        """Task-2: two users with the same password get different random salts and hashes."""
        rec_alice = register_user("alice", "Test@1234", db_path=self.db_path)
        rec_bob = register_user("bob", "Test@1234", db_path=self.db_path)

        self.assertNotEqual(rec_alice["salt"], rec_bob["salt"])
        self.assertNotEqual(rec_alice["hash"], rec_bob["hash"])

    def test_3_correct_password_verifies_true(self):
        """Task-2: logging in with the right password returns True."""
        register_user("alice", "Test@1234", db_path=self.db_path)
        self.assertTrue(verify_user("alice", "Test@1234", db_path=self.db_path))

    def test_4_wrong_password_verifies_false(self):
        """Task-2: logging in with a wrong password or unknown user returns False."""
        register_user("alice", "Test@1234", db_path=self.db_path)
        self.assertFalse(verify_user("alice", "WrongPass99", db_path=self.db_path))
        self.assertFalse(verify_user("charlie", "Test@1234", db_path=self.db_path))

    def test_5_one_char_change_alters_hash(self):
        """Task-2: changing a single character of the password produces a completely different hash."""
        salt = bytes.fromhex("00112233445566778899aabbccddeeff")
        h1 = hash_password("Test@1234", salt)
        h2 = hash_password("Test@1235", salt)
        self.assertNotEqual(h1, h2)

    def test_6_tampered_hash_or_salt_fails_login(self):
        """Task-2: modifying the stored hash or salt in users.json causes verification to fail."""
        register_user("alice", "Test@1234", db_path=self.db_path)

        # Flip one hex character in the stored hash
        db = load_db(self.db_path)
        orig_hash = db["alice"]["hash"]
        flipped = ("0" if orig_hash[0] != "0" else "1") + orig_hash[1:]
        db["alice"]["hash"] = flipped
        save_db(db, self.db_path)
        self.assertFalse(verify_user("alice", "Test@1234", db_path=self.db_path))

        # Restore hash, then tamper with the stored salt
        db["alice"]["hash"] = orig_hash
        orig_salt = db["alice"]["salt"]
        db["alice"]["salt"] = ("0" if orig_salt[0] != "0" else "1") + orig_salt[1:]
        save_db(db, self.db_path)
        self.assertFalse(verify_user("alice", "Test@1234", db_path=self.db_path))

    def test_7_wrong_pepper_fails_login(self):
        """Task-2: changing PASSWORD_PEPPER makes verification fail even with the right password."""
        register_user("alice", "Test@1234", db_path=self.db_path)
        os.environ["PASSWORD_PEPPER"] = "different-wrong-pepper-000"
        self.assertFalse(verify_user("alice", "Test@1234", db_path=self.db_path))

    def test_8_json_schema_and_no_leaked_secrets(self):
        """Task-2: users.json contains only the 4 expected keys and never stores password or pepper."""
        password = "MySecretPassword!2026"
        register_user("alice", password, db_path=self.db_path)

        raw_text = self.db_path.read_text(encoding="utf-8")
        self.assertNotIn(password, raw_text)
        self.assertNotIn(self.test_pepper, raw_text)

        db = load_db(self.db_path)
        expected_keys = {"algorithm", "salt", "hash", "created_at"}
        self.assertEqual(set(db["alice"].keys()), expected_keys)
        self.assertEqual(db["alice"]["algorithm"], "SHA-512")
        self.assertEqual(len(db["alice"]["salt"]), 32)
        self.assertEqual(len(db["alice"]["hash"]), 128)

    def test_9_bonus_pbkdf2_helper(self):
        """Bonus: hash_password_pbkdf2 produces a deterministic 128-hex-char derived key."""
        salt = bytes.fromhex("00112233445566778899aabbccddeeff")
        d1 = hash_password_pbkdf2("Test@1234", salt, iterations=1000)
        d2 = hash_password_pbkdf2("Test@1234", salt, iterations=1000)
        d3 = hash_password_pbkdf2("Test@1235", salt, iterations=1000)
        self.assertEqual(d1, d2)
        self.assertNotEqual(d1, d3)
        self.assertEqual(len(d1), 128)


if __name__ == "__main__":
    unittest.main()
