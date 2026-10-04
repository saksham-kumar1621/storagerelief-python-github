import os
import stat
import tempfile
import unittest

from core.cleaner import (
    safe_delete_path,
    clean_selected_paths,
    is_path_protected_by_firewall,
    FORBIDDEN_DELETION_PATTERNS
)


class TestCleanerFirewall(unittest.TestCase):
    def test_firewall_blocks_forbidden_patterns(self):
        """Asserts that all browser session, credentials, and system targets are blocked."""
        test_forbidden_paths = [
            r"C:\Users\Default\AppData\Local\Google\Chrome\User Data\Default\Login Data",
            r"C:\Users\Default\AppData\Local\Google\Chrome\User Data\Default\Cookies",
            r"C:\Users\Default\AppData\Local\Google\Chrome\User Data\Default\Web Data",
            r"C:\Users\Default\AppData\Local\Google\Chrome\User Data\Default\History",
            r"C:\Users\Default\AppData\Local\Google\Chrome\User Data\Default\Sessions",
            r"C:\Users\Default\AppData\Roaming\Mozilla\Firefox\Profiles\xyz\key4.db",
            r"C:\Users\Default\AppData\Roaming\Mozilla\Firefox\Profiles\xyz\logins.json",
            r"C:\Users\Default\AppData\Roaming\Mozilla\Firefox\Profiles\xyz\sessionstore.jsonlz4",
            r"C:\Windows\System32\cmd.exe",
            r"C:\bootmgr",
        ]
        for p in test_forbidden_paths:
            blocked, reason = is_path_protected_by_firewall(p)
            self.assertTrue(blocked, f"Path should be blocked by firewall: {p}")
            self.assertTrue(len(reason) > 0)

    def test_firewall_blocks_drive_and_user_roots(self):
        """Asserts that drive roots, system directories, and primary user folders cannot be deleted."""
        user_prof = os.environ.get("USERPROFILE", r"C:\Users\Default")
        test_roots = [
            "C:\\",
            "D:\\",
            r"C:\Windows",
            r"C:\Program Files",
            r"C:\Program Files (x86)",
            user_prof,
            os.path.join(user_prof, "Desktop"),
            os.path.join(user_prof, "Documents"),
            os.path.join(user_prof, "Downloads"),
        ]
        for r in test_roots:
            blocked, reason = is_path_protected_by_firewall(r)
            self.assertTrue(blocked, f"Root should be blocked: {r}")

    def test_safe_delete_real_file_with_readonly_attribute(self):
        """Creates a temporary read-only file and asserts safe_delete_path unlocks and deletes it."""
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"temporary test data for safe deletion")
            temp_path = tf.name

        try:
            # Set to read-only
            os.chmod(temp_path, stat.S_IREAD)
            self.assertTrue(os.path.exists(temp_path))

            success, err_msg = safe_delete_path(temp_path)
            self.assertTrue(success, f"Deletion failed: {err_msg}")
            self.assertFalse(os.path.exists(temp_path))
        finally:
            if os.path.exists(temp_path):
                os.chmod(temp_path, stat.S_IWRITE)
                os.remove(temp_path)

    def test_safe_delete_non_existent_reporting(self):
        """Calling safe_delete_path on a non-existent path must accurately report failure."""
        fake_path = r"C:\StorageRelief_NonExistent_Test_File_12345.tmp"
        success, err_msg = safe_delete_path(fake_path)
        self.assertFalse(success)
        self.assertIn("does not exist", err_msg.lower())

    def test_clean_selected_paths_reporting(self):
        """Tests that clean_selected_paths accurately partitions deleted vs failed items."""
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"valid item")
            valid_path = tf.name

        fake_path = r"C:\StorageRelief_NonExistent_Test_File_999.tmp"
        deleted, errors = clean_selected_paths([valid_path, fake_path])

        self.assertIn(valid_path, deleted)
        self.assertEqual(len(errors), 1)
        self.assertIn(fake_path, errors[0])


if __name__ == "__main__":
    unittest.main()
