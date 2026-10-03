#!/usr/bin/env python3
"""
StorageRelief - Native Windows Storage Optimizer
Python Edition built with PySide6 (Qt6)
Alternative Native GUI
"""

import os
import sys
import ctypes

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main():
    # 1. Windows Taskbar AppUserModelID (ensures icon shows on taskbar instead of python.exe icon)
    try:
        app_id = "com.storagerelief.python.optimizer"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass

    # 2. Configure High-DPI awareness
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("StorageRelief")
    app.setApplicationDisplayName("StorageRelief — Smart Windows Storage Optimizer (Qt)")
    app.setOrganizationName("StorageRelief")

    # 3. Application-wide Window Icon
    icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
