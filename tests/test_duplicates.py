import os
import tempfile
import unittest

from core.duplicates import (
    get_quick_partial_hash,
    get_full_hash,
    score_originality,
    verify_duplicate_integrity_before_delete,
)


class TestDuplicatesEngine(unittest.TestCase):
    def test_hashing_consistency(self):
        """Verifies hash generation on known byte samples."""
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"ABC" * 5000)
            tf_path = tf.name

        try:
            partial_h = get_quick_partial_hash(tf_path)
            full_h = get_full_hash(tf_path)

            self.assertIsNotNone(partial_h)
            self.assertIsNotNone(full_h)
            self.assertEqual(len(full_h), 64)  # SHA-256 hex length
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    def test_smart_original_scoring_copy_names(self):
        """Clean canonical filenames must score higher than copy markers."""
        score_orig = score_originality(r"C:\Users\User\Documents\Financial_Report.xlsx", mtime=1000)
        score_copy1 = score_originality(r"C:\Users\User\Documents\Financial_Report (1).xlsx", mtime=1000)
        score_copy2 = score_originality(r"C:\Users\User\Documents\Financial_Report - Copy.xlsx", mtime=1000)
        score_copy3 = score_originality(r"C:\Users\User\Documents\Copy of Financial_Report.xlsx", mtime=1000)

        self.assertGreater(score_orig, score_copy1)
        self.assertGreater(score_orig, score_copy2)
        self.assertGreater(score_orig, score_copy3)

    def test_smart_original_scoring_curated_folder_priority(self):
        """Curated library folders (Documents/Pictures) must score higher than Downloads/Temp."""
        score_doc = score_originality(r"C:\Users\User\Documents\contract.pdf", mtime=2000)
        score_down = score_originality(r"C:\Users\User\Downloads\contract.pdf", mtime=1000)  # Even if older!
        score_temp = score_originality(r"C:\Users\User\AppData\Local\Temp\contract.pdf", mtime=1000)

        self.assertGreater(score_doc, score_down, "Documents folder must take precedence over Downloads")
        self.assertGreater(score_doc, score_temp, "Documents folder must take precedence over Temp")

    def test_verify_duplicate_integrity_aborts_if_no_survivor(self):
        """TOCTOU safety: if original was deleted, duplicate deletion must be aborted."""
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"duplicate test file content")
            dup_path = tf.name

        try:
            fake_sibling = r"C:\NonExistent_Original_File_9999.xyz"
            file_sz = os.path.getsize(dup_path)

            safe, reason = verify_duplicate_integrity_before_delete(dup_path, [fake_sibling], file_sz)
            self.assertFalse(safe)
            self.assertIn("ABORTED", reason)
        finally:
            if os.path.exists(dup_path):
                os.remove(dup_path)

    def test_verify_duplicate_integrity_allows_when_survivor_intact(self):
        """If sibling exists on disk with matching size, integrity check succeeds."""
        with tempfile.NamedTemporaryFile(delete=False) as f1, tempfile.NamedTemporaryFile(delete=False) as f2:
            f1.write(b"identical content bytes")
            f2.write(b"identical content bytes")
            p1, p2 = f1.name, f2.name

        try:
            file_sz = os.path.getsize(p1)
            safe, reason = verify_duplicate_integrity_before_delete(p1, [p2], file_sz)
            self.assertTrue(safe, f"Should be safe when sibling intact: {reason}")
        finally:
            for p in (p1, p2):
                if os.path.exists(p):
                    os.remove(p)


    def test_scan_duplicates_argument_compatibility(self):
        """Verifies scan_duplicates accepts both min_size_bytes and min_size_mb without raising TypeError."""
        from core.duplicates import scan_duplicates
        with tempfile.TemporaryDirectory() as td:
            # Test with min_size_bytes keyword
            res1 = scan_duplicates([td], min_size_bytes=1024)
            self.assertEqual(res1.duplicate_groups_count, 0)

            # Test with min_size_mb keyword
            res2 = scan_duplicates([td], min_size_mb=2.0)
            self.assertEqual(res2.duplicate_groups_count, 0)


if __name__ == "__main__":
    unittest.main()
