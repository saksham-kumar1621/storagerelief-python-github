import unittest

from core.scanner import (
    get_drive_info,
    format_bytes,
    StorageItem,
    DriveInfo,
)


class TestScannerModule(unittest.TestCase):
    def test_get_drive_info(self):
        """Verifies querying C:\\ drive metrics via Win32 API."""
        info = get_drive_info("C:\\")
        self.assertIsInstance(info, DriveInfo)
        self.assertGreater(info.total_bytes, 0)
        self.assertGreater(info.free_bytes, 0)
        self.assertGreaterEqual(info.percent_free, 0.0)
        self.assertLessEqual(info.percent_free, 100.0)

    def test_format_bytes(self):
        """Verifies byte string formatting."""
        self.assertEqual(format_bytes(0), "0 B")
        self.assertEqual(format_bytes(1024), "1.0 KB")
        self.assertEqual(format_bytes(1024 * 1024), "1.0 MB")
        self.assertEqual(format_bytes(1024 * 1024 * 1024), "1.00 GB")

    def test_storage_item_dataclass(self):
        """Verifies StorageItem creation and field consistency."""
        item = StorageItem(
            id="item_1",
            name="Shader Cache",
            path=r"C:\AppData\Local\D3DSCache",
            size_bytes=1048576,
            size_formatted="1.00 MB",
            category="caches",
            category_label="Application Caches",
            risk_level="safe",
            description="DirectX precompiled shaders",
            selected=True,
        )
        self.assertEqual(item.id, "item_1")
        self.assertTrue(item.selected)
        self.assertEqual(item.risk_level, "safe")


if __name__ == "__main__":
    unittest.main()
