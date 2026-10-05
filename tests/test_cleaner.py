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


    def test_firewall_allows_legitimate_build_and_package_caches(self):
        """Asserts that build caches (Gradle executionHistory.lock, npm, pip) are not blocked."""
        test_allowed_paths = [
            r"C:\Users\Default\.gradle\caches\8.2.1\executionHistory\executionHistory.lock",
            r"C:\Users\Default\.gradle\caches\8.4\kotlin-dsl\executionHistory.bin",
            r"C:\Users\Default\AppData\Local\npm-cache\corsredirectcontainscredentials.md",
            r"C:\Users\Default\AppData\Local\npm-cache\emailverificationrequestaccountsemptylist.md",
            r"C:\Users\Default\AppData\Local\Temp\history_report.txt",
            r"C:\Users\Default\AppData\Local\Temp\user_preferences.ini",
            r"C:\Users\Default\AppData\Local\pip\cache\wheels\test.whl",
        ]
        for p in test_allowed_paths:
            blocked, reason = is_path_protected_by_firewall(p)
            self.assertFalse(blocked, f"Path should NOT be blocked by firewall: {p} (reason: {reason})")

    def test_safe_delete_directory_with_gradle_history_locks(self):
        """Asserts that directories containing Gradle executionHistory.lock delete cleanly."""
        temp_dir = tempfile.mkdtemp(prefix="sr_gradle_cache_test_")
        try:
            exec_history_dir = os.path.join(temp_dir, "8.2.1", "executionHistory")
            os.makedirs(exec_history_dir, exist_ok=True)
            lock_file = os.path.join(exec_history_dir, "executionHistory.lock")
            with open(lock_file, "w") as f:
                f.write("gradle lock data")

            bin_dir = os.path.join(temp_dir, "8.4", "kotlin-dsl")
            os.makedirs(bin_dir, exist_ok=True)
            bin_file = os.path.join(bin_dir, "executionHistory.bin")
            with open(bin_file, "w") as f:
                f.write("gradle bin data")

            self.assertTrue(os.path.exists(lock_file))
            success, err_msg = safe_delete_path(temp_dir)
            self.assertTrue(success, f"Deletion failed for gradle cache structure: {err_msg}")
            self.assertFalse(os.path.exists(temp_dir))
        finally:
            if os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)

    def test_safe_delete_aborts_on_directory_containing_sensitive_browser_credential(self):
        """Asserts that safe_delete_path strictly refuses to delete directories containing browser credentials."""
        temp_dir = tempfile.mkdtemp(prefix="sr_profile_test_")
        try:
            login_data = os.path.join(temp_dir, "Login Data")
            with open(login_data, "w") as f:
                f.write("sensitive password db")

            success, err_msg = safe_delete_path(temp_dir)
            self.assertFalse(success, "Directory containing Login Data must be blocked from deletion")
            self.assertIn("protected session or credential store", err_msg.lower())
            self.assertTrue(os.path.exists(temp_dir))
        finally:
            if os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)


    def test_firewall_blocks_real_browser_local_state_but_allows_temp_webview_local_state(self):
        """Asserts that Local State in Chrome/Edge profile is blocked, but temp WebView2 Local State is allowed."""
        chrome_local_state = r"C:\Users\Default\AppData\Local\Google\Chrome\User Data\Local State"
        blocked, reason = is_path_protected_by_firewall(chrome_local_state)
        self.assertTrue(blocked, "Chrome User Data Local State must be protected")
        self.assertIn("local state", reason.lower())

        edge_local_state = r"C:\Users\Default\AppData\Local\Microsoft\Edge\User Data\Local State"
        blocked, reason = is_path_protected_by_firewall(edge_local_state)
        self.assertTrue(blocked, "Edge User Data Local State must be protected")

        temp_webview_local_state = r"C:\Users\Default\AppData\Local\Temp\tmp12345\EBWebView\Local State"
        blocked, reason = is_path_protected_by_firewall(temp_webview_local_state)
        self.assertFalse(blocked, f"Temp WebView Local State should NOT be blocked: {reason}")

    def test_safe_delete_container_directory_temp(self):
        """Asserts that calling safe_delete_path on %TEMP% purges inner contents and returns success."""
        temp_dir = os.environ.get("TEMP")
        if temp_dir and os.path.exists(temp_dir):
            success, err_msg = safe_delete_path(temp_dir)
            self.assertTrue(success, f"safe_delete_path on TEMP directory must succeed: {err_msg}")
            # Ensure the TEMP directory itself was NOT deleted
            self.assertTrue(os.path.exists(temp_dir), "TEMP directory container itself must remain intact")


if __name__ == "__main__":
    unittest.main()


