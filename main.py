#!/usr/bin/env python3
"""
StorageRelief - Native Windows Storage Optimizer
Python Edition built with Edge WebView2 (pywebview) + Modern Glassmorphic Frontend
Pure Python Backend (Win32 API, NTFS Scanner, Safe Cleaner)
"""

import os
import sys
import ctypes
from dataclasses import asdict
from typing import List, Dict, Any, Union

import webview

from core.scanner import get_available_drives, get_drive_info, scan_storage
from core.cleaner import clean_selected_paths, open_in_file_explorer
from core.duplicates import scan_duplicates, get_default_scan_targets


def get_resource_path(relative_path: str) -> str:
    """Resolves resource path for both standard Python and PyInstaller bundles."""
    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(base_path, relative_path))


class StorageReliefAPI:
    """
    Exposed JavaScript-to-Python IPC Bridge.
    All methods are directly callable from JavaScript via `window.pywebview.api.<method>()`.
    """

    def get_available_drives(self) -> List[Dict[str, Any]]:
        """Enumerates all active fixed and removable drives with real-time capacity and labels."""
        try:
            drives = get_available_drives()
            return [asdict(d) for d in drives]
        except Exception as e:
            print(f"[StorageRelief Backend Error] get_available_drives: {e}", file=sys.stderr)
            raise e

    def get_drive_info(self, drive_letter: Union[str, Dict[str, Any]] = "C:\\") -> Dict[str, Any]:
        """Queries real-time drive space metrics via Win32 GetDiskFreeSpaceExW."""
        target_letter = "C:\\"
        if isinstance(drive_letter, str) and drive_letter:
            target_letter = drive_letter
        elif isinstance(drive_letter, dict):
            target_letter = drive_letter.get("drive_letter", "C:\\")

        try:
            drive_info = get_drive_info(target_letter)
            return asdict(drive_info)
        except Exception as e:
            print(f"[StorageRelief Backend Notice] get_drive_info on {target_letter} ({e}), falling back to C:\\", file=sys.stderr)
            try:
                fallback = get_drive_info("C:\\")
                return asdict(fallback)
            except Exception:
                raise e

    def scan_storage(self, drive_letter: Union[str, Dict[str, Any]] = "C:\\") -> Dict[str, Any]:
        """Runs the complete multi-category deep storage scanner on the chosen drive."""
        target_letter = "C:\\"
        if isinstance(drive_letter, str) and drive_letter:
            target_letter = drive_letter
        elif isinstance(drive_letter, dict):
            target_letter = drive_letter.get("drive_letter", "C:\\")

        try:
            try:
                drive_info, items = scan_storage(target_letter)
            except Exception as e:
                print(f"[StorageRelief Backend Notice] scan_storage on {target_letter} ({e}), falling back to C:\\", file=sys.stderr)
                drive_info, items = scan_storage("C:\\")

            items_dict = [asdict(item) for item in items]
            total_reclaimable = sum(item.size_bytes for item in items)
            return {
                "drive_info": asdict(drive_info),
                "items": items_dict,
                "total_reclaimable": total_reclaimable,
            }
        except Exception as e:
            print(f"[StorageRelief Backend Error] scan_storage: {e}", file=sys.stderr)
            raise e

    def clean_selected_items(self, paths: Union[List[str], Dict[str, Any]] = None) -> Dict[str, Any]:
        """Safely cleans selected paths with Windows recursive read-only attribute stripping."""
        try:
            target_paths: List[str] = []
            if isinstance(paths, list):
                target_paths = paths
            elif isinstance(paths, dict):
                target_paths = paths.get("paths", [])

            deleted, errors = clean_selected_paths(target_paths)
            return {
                "deleted": deleted,
                "errors": errors,
            }
        except Exception as e:
            print(f"[StorageRelief Backend Error] clean_selected_items: {e}", file=sys.stderr)
            raise e

    def open_item_path(self, path: Union[str, Dict[str, Any]] = "") -> bool:
        """Spawns Windows File Explorer highlighting or opening the specified target."""
        try:
            target_path = path if isinstance(path, str) else path.get("path", "")
            return open_in_file_explorer(target_path)
        except Exception as e:
            print(f"[StorageRelief Backend Error] open_item_path: {e}", file=sys.stderr)
            return False

    def get_duplicate_scan_targets(self, drive_letter: Union[str, Dict[str, Any]] = "C:\\") -> List[Dict[str, Any]]:
        """Returns standard library folders available for duplicate scanning on the given drive."""
        try:
            target_letter = "C:\\"
            if isinstance(drive_letter, str) and drive_letter:
                target_letter = drive_letter
            elif isinstance(drive_letter, dict):
                target_letter = drive_letter.get("drive_letter", "C:\\")

            return get_default_scan_targets(target_letter)
        except Exception as e:
            print(f"[StorageRelief Backend Error] get_duplicate_scan_targets: {e}", file=sys.stderr)
            return []

    def scan_duplicates(self, options: Union[Dict[str, Any], List[str]] = None) -> Dict[str, Any]:
        """Runs the 3-phase hash deduplication engine across selected target directories."""
        try:
            target_dirs = []
            min_size_mb = 1.0

            if isinstance(options, dict):
                target_dirs = options.get("target_dirs", [])
                min_size_mb = float(options.get("min_size_mb", 1.0))
            elif isinstance(options, list):
                target_dirs = options

            min_bytes = int(min_size_mb * 1024 * 1024)
            result = scan_duplicates(target_dirs, min_size_mb=min_size_mb, min_size_bytes=min_bytes)

            groups_dict = []
            for g in result.groups:
                groups_dict.append(asdict(g))

            return {
                "total_scanned_files": result.total_scanned_files,
                "total_scanned_bytes": result.total_scanned_bytes,
                "duplicate_groups_count": result.duplicate_groups_count,
                "total_wasted_bytes": result.total_wasted_bytes,
                "total_wasted_formatted": result.total_wasted_formatted,
                "groups": groups_dict,
            }
        except Exception as e:
            print(f"[StorageRelief Backend Error] scan_duplicates: {e}", file=sys.stderr)
            raise e

    def pick_custom_folder(self) -> str:
        """Opens native Windows folder picker dialog."""
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            folder_selected = filedialog.askdirectory(title="Select Folder to Scan for Duplicates")
            root.destroy()
            return folder_selected or ""
        except Exception as e:
            print(f"[StorageRelief Backend Error] pick_custom_folder: {e}", file=sys.stderr)
            return ""


def main():
    # 1. Windows Taskbar AppUserModelID (ensures window groups and icons display properly)
    try:
        app_id = "com.storagerelief.python.webview.optimizer"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass

    # 2. Locate frontend assets and icon
    html_entry = get_resource_path(os.path.join("ui", "web", "index.html"))
    icon_path = get_resource_path(os.path.join("assets", "icon.ico"))

    if not os.path.isfile(html_entry):
        print(f"Error: UI file not found at {html_entry}", file=sys.stderr)
        sys.exit(1)

    # 3. Instantiate Bridge API
    api = StorageReliefAPI()

    # 4. Create Webview Window using Microsoft Edge WebView2
    window = webview.create_window(
        title="StorageRelief — Smart Windows Storage Optimizer",
        url=html_entry,
        js_api=api,
        width=1200,
        height=742,
        min_size=(960, 593),
        background_color="#07090e",  # Matches --bg-dark
        text_select=True,
    )

    # 5. Start WebView Engine
    start_kwargs: Dict[str, Any] = {
        "gui": "edgechromium",
        "debug": False,
    }
    if os.path.isfile(icon_path):
        start_kwargs["icon"] = icon_path

    webview.start(**start_kwargs)


if __name__ == "__main__":
    main()
