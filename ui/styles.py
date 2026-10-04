"""
StorageRelief - Glassmorphic Dark UI Theme
Bespoke styling inspired by modern Windows 11 Fluent and dark glassmorphic design.
"""

DARK_THEME_QSS = """
/* Global Window & Base Settings */
QMainWindow, QDialog {
    background-color: #0b0f19;
    color: #f1f5f9;
    font-family: "Segoe UI", "Plus Jakarta Sans", -apple-system, sans-serif;
}

QWidget {
    font-family: "Segoe UI", "Plus Jakarta Sans", sans-serif;
    color: #e2e8f0;
}

/* Glass Card Frames */
.GlassCard {
    background-color: rgba(17, 24, 39, 0.75);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
}

.GlassCardHover:hover {
    background-color: rgba(26, 35, 54, 0.85);
    border: 1px solid rgba(6, 182, 212, 0.3);
}

/* Push Buttons */
QPushButton {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 9px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #334155;
    border-color: rgba(255, 255, 255, 0.2);
}

QPushButton:pressed {
    background-color: #0f172a;
}

QPushButton:disabled {
    background-color: rgba(30, 41, 59, 0.4);
    color: #64748b;
    border-color: rgba(255, 255, 255, 0.04);
}

/* Primary Action Button (Cyan / Emerald Gradient) */
QPushButton#btnPrimary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #06b6d4, stop:1 #0891b2);
    color: #ffffff;
    border: none;
    border-radius: 10px;
    font-weight: 700;
    font-size: 14px;
    padding: 10px 22px;
}

QPushButton#btnPrimary:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #22d3ee, stop:1 #06b6d4);
}

QPushButton#btnPrimary:pressed {
    background: #0e7490;
}

QPushButton#btnPrimary:disabled {
    background: #1e293b;
    color: #475569;
}

/* Danger Button */
QPushButton#btnDanger {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f43f5e, stop:1 #e11d48);
    color: #ffffff;
    border: none;
    border-radius: 10px;
    font-weight: 700;
    font-size: 13px;
    padding: 9px 20px;
}

QPushButton#btnDanger:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #fb7185, stop:1 #f43f5e);
}

/* Secondary Button */
QPushButton#btnSecondary {
    background-color: rgba(255, 255, 255, 0.05);
    color: #cbd5e1;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 9px;
    font-size: 13px;
    font-weight: 600;
    padding: 8px 16px;
}

QPushButton#btnSecondary:hover {
    background-color: rgba(255, 255, 255, 0.1);
    color: #ffffff;
}

/* Filter Tab Buttons */
QPushButton.FilterTab {
    background-color: rgba(255, 255, 255, 0.04);
    color: #94a3b8;
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 20px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 600;
}

QPushButton.FilterTab:hover {
    background-color: rgba(255, 255, 255, 0.08);
    color: #f1f5f9;
}

QPushButton.FilterTab[active="true"] {
    background-color: #06b6d4;
    color: #07090e;
    font-weight: 700;
    border: 1px solid #22d3ee;
}

/* Search Bar */
QLineEdit {
    background-color: rgba(17, 24, 39, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 10px;
    color: #f8fafc;
    padding: 8px 14px;
    font-size: 13px;
    selection-background-color: #06b6d4;
}

QLineEdit:focus {
    border: 1px solid #06b6d4;
    background-color: rgba(17, 24, 39, 0.95);
}

/* Checkboxes */
QCheckBox {
    spacing: 8px;
}

QCheckBox::indicator {
    width: 19px;
    height: 19px;
    border: 1.5px solid rgba(255, 255, 255, 0.25);
    border-radius: 5px;
    background-color: rgba(17, 24, 39, 0.6);
}

QCheckBox::indicator:hover {
    border-color: #06b6d4;
}

QCheckBox::indicator:checked {
    background-color: #06b6d4;
    border-color: #06b6d4;
    image: none;
}

/* Scroll Area & Scroll Bars */
QScrollArea {
    border: none;
    background: transparent;
}

QScrollBar:vertical {
    border: none;
    background: rgba(15, 23, 42, 0.4);
    width: 8px;
    margin: 0px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 0.15);
    min-height: 25px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: rgba(6, 182, 212, 0.4);
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
    border: none;
}

/* Labels */
QLabel {
    background: transparent;
}

QLabel#lblHeroTitle {
    font-size: 26px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -0.5px;
}

QLabel#lblSubTitle {
    font-size: 13px;
    color: #94a3b8;
}

QLabel#lblMetricValue {
    font-size: 18px;
    font-weight: 700;
    font-family: "JetBrains Mono", "Consolas", monospace;
    color: #f8fafc;
}

QLabel#lblMetricKey {
    font-size: 11px;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
}

/* Badges */
.RiskBadgeSafe {
    background-color: rgba(16, 185, 129, 0.15);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.3);
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 700;
}

.RiskBadgeReview {
    background-color: rgba(245, 158, 11, 0.15);
    color: #fbbf24;
    border: 1px solid rgba(245, 158, 11, 0.3);
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 700;
}

.RiskBadgeCaution {
    background-color: rgba(244, 63, 94, 0.15);
    color: #fda4af;
    border: 1px solid rgba(244, 63, 94, 0.3);
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 700;
}

QLabel#lblHeroTitle { font-size: 20px; font-weight: 800; color: #ffffff; }
QLabel#lblSubHeader { font-size: 11px; font-weight: 600; color: #38bdf8; }
QLabel#lblStatusDot { color: #10b981; font-size: 10px; }
QLabel#lblStatusText { font-size: 12px; font-weight: 600; color: #cbd5e1; }
QLabel#lblMetricKey { font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; }
QLabel#lblMetricVal { font-size: 18px; font-weight: 800; font-family: 'JetBrains Mono', Consolas, monospace; color: #f8fafc; }
QLabel#lblReclaimTitle { font-size: 10px; font-weight: 800; color: #34d399; letter-spacing: 0.5px; }
QLabel#lblHeroReclaim { font-size: 24px; font-weight: 900; color: #10b981; font-family: monospace; }
QLabel#lblModalTotal { font-size: 20px; font-weight: 800; color: #10b981; }
QLabel#lblModalItemName { font-size: 13px; font-weight: 700; color: #f8fafc; }
QLabel#lblModalItemSize { font-size: 11px; color: #10b981; font-weight: 600; }
"""
