import os
from PySide6.QtCore import Qt, Signal, QRectF, QTimer, QPropertyAnimation, Property
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QBrush, QLinearGradient
from PySide6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLabel,
    QCheckBox, QPushButton, QDialog, QScrollArea
)
from core.scanner import StorageItem, format_bytes
from core.cleaner import open_in_file_explorer


class CircularGauge(QWidget):
    """Custom QPainter Circular Drive Space Gauge."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._percent = 0.0
        self.setFixedSize(130, 130)

    def get_percent(self) -> float:
        return self._percent

    def set_percent(self, val: float):
        self._percent = max(0.0, min(100.0, val))
        self.update()

    percent = Property(float, get_percent, set_percent)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(10, 10, self.width() - 20, self.height() - 20)
        track_pen = QPen(QColor(30, 41, 59, 180), 9)
        track_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(rect, 0, 360 * 16)

        # Dynamic color based on percent free
        if self._percent < 10:
            arc_color = QColor(244, 63, 94)  # Rose
            status_text = "LOW"
        elif self._percent < 20:
            arc_color = QColor(245, 158, 11)  # Amber
            status_text = "WARNING"
        else:
            arc_color = QColor(6, 182, 212)   # Cyan
            status_text = "FREE"

        # Foreground Arc (counter-clockwise from 90 deg)
        arc_pen = QPen(arc_color, 9)
        arc_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(arc_pen)

        span_angle = int(- (self._percent / 100.0) * 360 * 16)
        painter.drawArc(rect, 90 * 16, span_angle)

        # Text in center
        painter.setPen(QColor(255, 255, 255))
        font_pct = QFont("Segoe UI", 18, QFont.Bold)
        painter.setFont(font_pct)
        pct_str = f"{self._percent:.0f}%"
        painter.drawText(QRectF(0, 36, self.width(), 32), Qt.AlignCenter, pct_str)

        font_sub = QFont("Segoe UI", 9, QFont.DemiBold)
        painter.setFont(font_sub)
        painter.setPen(QColor(148, 163, 184))
        painter.drawText(QRectF(0, 68, self.width(), 20), Qt.AlignCenter, status_text)


class StorageItemCard(QFrame):
    """Interactive card representing a detected storage item."""
    selection_toggled = Signal(str, bool)

    CATEGORY_LABELS = {
        "ghost_apps": "Ghost Apps",
        "caches": "Caches & Temp",
        "archives": "Installers & Repacks",
        "dev_junk": "Dev Builds",
        "virtual_disks": "VMs & Emulators",
    }

    def __init__(self, item: StorageItem, parent=None):
        super().__init__(parent)
        self.item = item
        self.setObjectName("storageCard")
        self.setProperty("class", "GlassCard GlassCardHover")
        self.setFixedHeight(76)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(14)

        # Checkbox
        self.cb = QCheckBox()
        self.cb.setChecked(item.selected)
        self.cb.stateChanged.connect(self._on_check_changed)
        layout.addWidget(self.cb)

        # Category Icon Pill
        cat_name = self.CATEGORY_LABELS.get(item.category, "Item")
        icon_lbl = QLabel(cat_name[:2].upper())
        icon_lbl.setStyleSheet("""
            background: rgba(255, 255, 255, 0.08);
            border-radius: 8px;
            font-size: 11px;
            font-weight: 800;
            color: #38bdf8;
            padding: 4px;
        """)
        icon_lbl.setFixedSize(38, 38)
        icon_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_lbl)

        # Details Column
        details_layout = QVBoxLayout()
        details_layout.setSpacing(2)
        details_layout.setContentsMargins(0, 0, 0, 0)

        # Row 1: Title + Risk Badge
        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        self.title_lbl = QLabel(item.name)
        self.title_lbl.setStyleSheet("font-weight: 700; font-size: 13px; color: #f8fafc;")
        title_row.addWidget(self.title_lbl)

        badge_class = f"RiskBadge{item.risk_level.capitalize()}"
        self.badge_lbl = QLabel(item.risk_level.upper())
        self.badge_lbl.setProperty("class", badge_class)
        title_row.addWidget(self.badge_lbl)
        title_row.addStretch()

        details_layout.addLayout(title_row)

        # Row 2: Description & Path
        self.desc_lbl = QLabel(f"{item.description} • {item.path}")
        self.desc_lbl.setStyleSheet("font-size: 11px; color: #64748b;")
        self.desc_lbl.setToolTip(item.path)
        details_layout.addWidget(self.desc_lbl)

        layout.addLayout(details_layout, stretch=1)

        # Size Label
        self.size_lbl = QLabel(item.size_formatted)
        self.size_lbl.setStyleSheet("""
            font-size: 14px;
            font-weight: 700;
            font-family: 'JetBrains Mono', 'Consolas', monospace;
            color: #38bdf8;
        """)
        layout.addWidget(self.size_lbl)

        # Explorer Launch Button
        self.btn_explore = QPushButton("Explore")
        self.btn_explore.setToolTip("Open folder in Windows File Explorer")
        self.btn_explore.setFixedSize(34, 34)
        self.btn_explore.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                font-size: 14px;
                padding: 0;
            }
            QPushButton:hover {
                background: rgba(6, 182, 212, 0.2);
                border-color: #06b6d4;
            }
        """)
        self.btn_explore.clicked.connect(lambda: open_in_file_explorer(item.path))
        layout.addWidget(self.btn_explore)

    def _on_check_changed(self, state):
        is_checked = (state == Qt.Checked.value or state == 2)
        self.item.selected = is_checked
        self.selection_toggled.emit(self.item.id, is_checked)


class ToastNotification(QFrame):
    """Floating glassmorphic toast notification."""
    def __init__(self, text: str, toast_type: str = "info", parent=None):
        super().__init__(parent)
        self.setFixedWidth(340)

        if toast_type == "error":
            bg = "rgba(40, 16, 24, 0.95)"
            border = "rgba(244, 63, 94, 0.4)"
            icon = "[!]"
            color = "#fecdd3"
        elif toast_type == "success":
            bg = "rgba(16, 36, 28, 0.95)"
            border = "rgba(16, 185, 129, 0.4)"
            icon = "[OK]"
            color = "#d1fae5"
        else:
            bg = "rgba(15, 28, 44, 0.95)"
            border = "rgba(6, 182, 212, 0.4)"
            icon = "[i]"
            color = "#cffafe"

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 10px;
                color: {color};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 14px; background: transparent;")
        layout.addWidget(icon_lbl)

        msg_lbl = QLabel(text)
        msg_lbl.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {color}; background: transparent;")
        msg_lbl.setWordWrap(True)
        layout.addWidget(msg_lbl, stretch=1)

        QTimer.singleShot(4000, self.deleteLater)


class ConfirmCleanDialog(QDialog):
    """Confirmation modal displaying itemized list of items to be deleted."""
    def __init__(self, selected_items: list[StorageItem], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirm Storage Clean")
        self.setFixedSize(540, 480)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header Title
        title_lbl = QLabel("Confirm Storage Deletion")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: 800; color: #f43f5e;")
        layout.addWidget(title_lbl)

        desc_lbl = QLabel("You are about to permanently delete the following selected items:")
        desc_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(desc_lbl)

        # Scrollable items list preview
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        c_layout = QVBoxLayout(container)
        c_layout.setSpacing(6)

        total_bytes = 0
        for item in selected_items:
            total_bytes += item.size_bytes
            row = QFrame()
            row.setStyleSheet("""
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 6px;
                padding: 6px 10px;
            """)
            r_layout = QHBoxLayout(row)
            r_layout.setContentsMargins(8, 6, 8, 6)

            n_lbl = QLabel(item.name)
            n_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #f1f5f9;")
            n_lbl.setToolTip(item.path)
            r_layout.addWidget(n_lbl, stretch=1)

            s_lbl = QLabel(item.size_formatted)
            s_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #38bdf8;")
            r_layout.addWidget(s_lbl)

            c_layout.addWidget(row)

        c_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

        # Total Reclaim Badge
        summary_frame = QFrame()
        summary_frame.setStyleSheet("""
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.25);
            border-radius: 8px;
            padding: 10px 16px;
        """)
        sum_layout = QHBoxLayout(summary_frame)
        sum_lbl = QLabel("Total Space to Reclaim:")
        sum_lbl.setStyleSheet("font-weight: 600; color: #94a3b8;")
        sum_layout.addWidget(sum_lbl)

        total_lbl = QLabel(format_bytes(total_bytes))
        total_lbl.setStyleSheet("font-size: 16px; font-weight: 800; color: #10b981;")
        sum_layout.addWidget(total_lbl, alignment=Qt.AlignRight)
        layout.addWidget(summary_frame)

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_confirm = QPushButton("Proceed with Clean")
        btn_confirm.setObjectName("btnDanger")
        btn_confirm.clicked.connect(self.accept)
        btn_row.addWidget(btn_confirm)

        layout.addLayout(btn_row)


class CelebrationDialog(QDialog):
    """Celebration modal displaying reclaimed space."""
    def __init__(self, reclaimed_formatted: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Storage Relieved!")
        self.setFixedSize(400, 320)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignCenter)

        icon_lbl = QLabel("[CLEAN]")
        icon_lbl.setStyleSheet("font-size: 24px; font-weight: 800; color: #10b981;")
        icon_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_lbl)

        title_lbl = QLabel("Storage Relief Achieved!")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: #ffffff;")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        sub_lbl = QLabel("Your Windows system drive is now lighter and faster.")
        sub_lbl.setStyleSheet("font-size: 12px; color: #94a3b8;")
        sub_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub_lbl)

        trophy_frame = QFrame()
        trophy_frame.setStyleSheet("""
            background: rgba(16, 185, 129, 0.12);
            border: 1px solid rgba(16, 185, 129, 0.35);
            border-radius: 10px;
            padding: 12px;
        """)
        t_layout = QVBoxLayout(trophy_frame)
        t_layout.setSpacing(2)

        t_sub = QLabel("FREED UP")
        t_sub.setStyleSheet("font-size: 10px; font-weight: 700; color: #34d399; letter-spacing: 1px;")
        t_sub.setAlignment(Qt.AlignCenter)
        t_layout.addWidget(t_sub)

        t_val = QLabel(f"+{reclaimed_formatted}")
        t_val.setStyleSheet("font-size: 26px; font-weight: 900; color: #10b981; font-family: monospace;")
        t_val.setAlignment(Qt.AlignCenter)
        t_layout.addWidget(t_val)

        layout.addWidget(trophy_frame)

        btn_done = QPushButton("Done")
        btn_done.setObjectName("btnPrimary")
        btn_done.setFixedHeight(38)
        btn_done.clicked.connect(self.accept)
        layout.addWidget(btn_done)
