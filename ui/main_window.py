import os
import sys
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QIcon, QColor, QFont
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QScrollArea, QFrame, QProgressBar
)

from core.scanner import StorageItem, DriveInfo, scan_storage, get_drive_info, format_bytes
from core.cleaner import clean_selected_paths
from ui.widgets import CircularGauge, StorageItemCard, ToastNotification, ConfirmCleanDialog, CelebrationDialog
from ui.styles import DARK_THEME_QSS


class ScanWorker(QThread):
    progress_signal = Signal(str)
    finished_signal = Signal(object, list)
    error_signal = Signal(str)

    def run(self):
        try:
            drive_info, items = scan_storage(progress_callback=self.progress_signal.emit)
            self.finished_signal.emit(drive_info, items)
        except Exception as e:
            self.error_signal.emit(str(e))


class CleanWorker(QThread):
    progress_signal = Signal(str, int, int)
    finished_signal = Signal(list, list)
    error_signal = Signal(str)

    def __init__(self, paths: list[str]):
        super().__init__()
        self.paths = paths

    def run(self):
        try:
            deleted, errors = clean_selected_paths(
                self.paths,
                progress_callback=self.progress_signal.emit
            )
            self.finished_signal.emit(deleted, errors)
        except Exception as e:
            self.error_signal.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("StorageRelief - Windows Storage Optimizer")
        self.resize(1120, 780)
        self.setMinimumSize(960, 680)

        # Set App Icon if present
        icon_path = os.path.join(os.path.dirname(__file__), "..", "assets", "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.setStyleSheet(DARK_THEME_QSS)

        # State
        self.drive_info: DriveInfo = get_drive_info("C:\\")
        self.items: list[StorageItem] = []
        self.active_category: str = "all"
        self.search_query: str = ""
        self.is_scanning: bool = False
        self.is_cleaning: bool = False
        self.cards_map: dict[str, StorageItemCard] = {}

        self._build_ui()
        self._update_drive_ui(self.drive_info)

        # Boot initial scan smoothly after UI renders
        QTimer.singleShot(350, self.start_scan)

    def _build_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(28, 20, 28, 16)
        root_layout.setSpacing(16)

        # 1. Top Header Bar
        header_layout = QHBoxLayout()

        brand_layout = QHBoxLayout()
        brand_icon = QLabel("SR")
        brand_icon.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #06b6d4, stop:1 #10b981);
            color: #07090e;
            border-radius: 9px;
            font-size: 14px;
            font-weight: 800;
            padding: 4px;
        """)
        brand_icon.setFixedSize(36, 36)
        brand_icon.setAlignment(Qt.AlignCenter)
        brand_layout.addWidget(brand_icon)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        h_title = QLabel("StorageRelief")
        h_title.setObjectName("lblHeroTitle")
        title_col.addWidget(h_title)

        v_lbl = QLabel("v1.0 • Python Native Engine")
        v_lbl.setObjectName("lblSubHeader")
        title_col.addWidget(v_lbl)
        brand_layout.addLayout(title_col)
        header_layout.addLayout(brand_layout)

        header_layout.addStretch()

        # Status Pill
        self.status_pill = QFrame()
        self.status_pill.setStyleSheet("""
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            padding: 4px 12px;
        """)
        sp_layout = QHBoxLayout(self.status_pill)
        sp_layout.setContentsMargins(8, 4, 8, 4)
        sp_layout.setSpacing(6)

        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("lblStatusDot")
        sp_layout.addWidget(self.status_dot)

        self.status_lbl = QLabel("Ready")
        self.status_lbl.setObjectName("lblStatusText")
        sp_layout.addWidget(self.status_lbl)
        header_layout.addWidget(self.status_pill)

        # Scan Button
        self.btn_scan = QPushButton("Scan Drive")
        self.btn_scan.setObjectName("btnSecondary")
        self.btn_scan.clicked.connect(self.start_scan)
        header_layout.addWidget(self.btn_scan)

        root_layout.addLayout(header_layout)

        # 2. Hero Storage Dashboard Card
        hero_card = QFrame()
        hero_card.setProperty("class", "GlassCard")
        hero_layout = QHBoxLayout(hero_card)
        hero_layout.setContentsMargins(22, 18, 22, 18)
        hero_layout.setSpacing(24)

        # Left: Gauge
        self.gauge = CircularGauge()
        hero_layout.addWidget(self.gauge)

        # Center: Drive Metrics
        metrics_col = QVBoxLayout()
        metrics_col.setSpacing(10)

        # Top row: Stat items
        stats_row = QHBoxLayout()
        stats_row.setSpacing(28)

        def make_stat_box(title, val_attr):
            vbox = QVBoxLayout()
            vbox.setSpacing(2)
            k_lbl = QLabel(title)
            k_lbl.setObjectName("lblMetricKey")
            v_lbl = QLabel("0.0 GB")
            v_lbl.setObjectName("lblMetricVal")
            setattr(self, val_attr, v_lbl)
            vbox.addWidget(k_lbl)
            vbox.addWidget(v_lbl)
            return vbox

        stats_row.addLayout(make_stat_box("Free Space", "lbl_free_gb"))
        stats_row.addLayout(make_stat_box("Used Space", "lbl_used_gb"))
        stats_row.addLayout(make_stat_box("Total Drive (C:)", "lbl_total_gb"))
        stats_row.addStretch()
        metrics_col.addLayout(stats_row)

        # Linear bar
        self.drive_progress = QProgressBar()
        self.drive_progress.setFixedHeight(8)
        self.drive_progress.setTextVisible(False)
        self.drive_progress.setStyleSheet("""
            QProgressBar {
                background-color: rgba(30, 41, 59, 0.8);
                border-radius: 4px;
                border: none;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #06b6d4, stop:1 #10b981);
                border-radius: 4px;
            }
        """)
        metrics_col.addWidget(self.drive_progress)
        hero_layout.addLayout(metrics_col, stretch=1)

        # Right: Reclaimable Space Summary Box
        reclaim_box = QFrame()
        reclaim_box.setStyleSheet("""
            background: rgba(16, 185, 129, 0.08);
            border: 1px solid rgba(16, 185, 129, 0.2);
            border-radius: 12px;
            padding: 12px 18px;
        """)
        rb_layout = QVBoxLayout(reclaim_box)
        rb_layout.setSpacing(4)

        rb_title = QLabel("SELECTED TO RECLAIM")
        rb_title.setObjectName("lblReclaimTitle")
        rb_layout.addWidget(rb_title)

        self.lbl_hero_reclaim = QLabel("0.00 GB")
        self.lbl_hero_reclaim.setObjectName("lblHeroReclaim")
        rb_layout.addWidget(self.lbl_hero_reclaim)

        # Quick select buttons
        qb_row = QHBoxLayout()
        qb_row.setSpacing(8)

        self.btn_select_safe = QPushButton("Select Zero-Risk")
        self.btn_select_safe.setStyleSheet("""
            QPushButton {
                background: rgba(16, 185, 129, 0.2);
                border: 1px solid rgba(16, 185, 129, 0.4);
                color: #a7f3d0;
                font-size: 11px;
                padding: 4px 8px;
                border-radius: 6px;
            }
            QPushButton:hover { background: rgba(16, 185, 129, 0.35); }
        """)
        self.btn_select_safe.clicked.connect(self._select_all_safe)
        qb_row.addWidget(self.btn_select_safe)

        self.btn_deselect = QPushButton("Deselect All")
        self.btn_deselect.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                color: #94a3b8;
                font-size: 11px;
                padding: 4px 8px;
                border-radius: 6px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.1); color: #ffffff; }
        """)
        self.btn_deselect.clicked.connect(self._deselect_all)
        qb_row.addWidget(self.btn_deselect)

        rb_layout.addLayout(qb_row)
        hero_layout.addWidget(reclaim_box)

        root_layout.addWidget(hero_card)

        # 3. Filter Tabs & Search Bar Row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        self.tabs_group = []
        categories = [
            ("all", "All"),
            ("ghost_apps", "Ghost Apps"),
            ("caches", "Caches & Temp"),
            ("archives", "Installers & Repacks"),
            ("dev_junk", "Dev Builds"),
            ("virtual_disks", "VMs & Emulators"),
        ]

        for cat_id, label in categories:
            btn = QPushButton(label)
            btn.setProperty("class", "FilterTab")
            btn.setProperty("category_id", cat_id)
            btn.setProperty("active", "true" if cat_id == "all" else "false")
            btn.clicked.connect(lambda _, c=cat_id: self._set_active_category(c))
            filter_row.addWidget(btn)
            self.tabs_group.append(btn)

        filter_row.addStretch()

        # Search Bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter by path or name...")
        self.search_input.setFixedWidth(240)
        self.search_input.textChanged.connect(self._on_search_changed)
        filter_row.addWidget(self.search_input)

        root_layout.addLayout(filter_row)

        # 4. Storage Items List Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.items_layout = QVBoxLayout(self.scroll_content)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(8)

        # Empty State Widget
        self.empty_state = QFrame()
        self.empty_state.setStyleSheet("""
            background: rgba(17, 24, 39, 0.5);
            border: 1px dashed rgba(255, 255, 255, 0.12);
            border-radius: 12px;
            padding: 40px;
        """)
        es_layout = QVBoxLayout(self.empty_state)
        es_layout.setAlignment(Qt.AlignCenter)
        es_icon = QLabel("[OK]")
        es_icon.setObjectName("lblModalTotal")
        es_icon.setAlignment(Qt.AlignCenter)
        es_layout.addWidget(es_icon)

        self.es_title = QLabel("No storage waste in this category!")
        self.es_title.setObjectName("lblHeroTitle")
        self.es_title.setAlignment(Qt.AlignCenter)
        es_layout.addWidget(self.es_title)

        es_desc = QLabel("Your selected category is completely clean. Switch tabs or run a fresh scan anytime.")
        es_desc.setObjectName("lblSubHeader")
        es_desc.setAlignment(Qt.AlignCenter)
        es_layout.addWidget(es_desc)

        self.items_layout.addWidget(self.empty_state)
        self.empty_state.hide()

        self.items_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_content)
        root_layout.addWidget(self.scroll_area, stretch=1)

        # 5. Bottom Sticky Footer
        footer = QFrame()
        footer.setStyleSheet("""
            background: rgba(11, 15, 25, 0.95);
            border-top: 1px solid rgba(255, 255, 255, 0.08);
            padding: 12px 6px 4px 6px;
        """)
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(10, 8, 10, 4)

        f_left = QVBoxLayout()
        f_left.setSpacing(2)
        self.lbl_footer_summary = QLabel("Selected: 0 items (0.00 GB)")
        self.lbl_footer_summary.setObjectName("lblModalItemName")
        f_left.addWidget(self.lbl_footer_summary)

        badge_safe = QLabel("Safe Deletion Engine • Recursive Read-Only Unlock Guaranteed")
        badge_safe.setObjectName("lblModalItemSize")
        f_left.addWidget(badge_safe)
        f_layout.addLayout(f_left)

        f_layout.addStretch()

        self.btn_clean = QPushButton("Clean Selected (0.00 GB)")
        self.btn_clean.setObjectName("btnPrimary")
        self.btn_clean.setEnabled(False)
        self.btn_clean.clicked.connect(self._open_clean_dialog)
        f_layout.addWidget(self.btn_clean)

        root_layout.addWidget(footer)

    def _update_drive_ui(self, info: DriveInfo):
        self.drive_info = info
        self.lbl_free_gb.setText(f"{info.free_gb:.1f} GB")
        self.lbl_used_gb.setText(f"{info.used_gb:.1f} GB")
        self.lbl_total_gb.setText(f"{info.total_gb:.1f} GB")
        self.gauge.set_percent(info.percent_free)

        used_pct = int(100.0 - info.percent_free)
        self.drive_progress.setValue(used_pct)

    def start_scan(self):
        if self.is_scanning:
            return
        self.is_scanning = True
        self.btn_scan.setEnabled(False)
        self.btn_scan.setText("Scanning...")
        self.status_dot.setStyleSheet("color: #06b6d4; font-size: 10px;")
        self.status_lbl.setText("Scanning storage...")

        self.scan_worker = ScanWorker()
        self.scan_worker.progress_signal.connect(self._on_scan_progress)
        self.scan_worker.finished_signal.connect(self._on_scan_finished)
        self.scan_worker.error_signal.connect(self._on_scan_error)
        self.scan_worker.start()

    def _on_scan_progress(self, msg: str):
        self.status_lbl.setText(msg)

    def _on_scan_finished(self, drive_info: DriveInfo, items: list[StorageItem]):
        self.is_scanning = False
        self.btn_scan.setEnabled(True)
        self.btn_scan.setText("Scan Drive")
        self.status_dot.setStyleSheet("color: #10b981; font-size: 10px;")
        self.status_lbl.setText("Ready")

        self._update_drive_ui(drive_info)
        self.items = items
        self._rebuild_items_cards()
        self._update_selection_summary()
        self._show_toast(f"Scan complete! Discovered {len(items)} reclaimable items.", "success")

    def _on_scan_error(self, err_msg: str):
        self.is_scanning = False
        self.btn_scan.setEnabled(True)
        self.btn_scan.setText("Scan Drive")
        self.status_dot.setStyleSheet("color: #f43f5e; font-size: 10px;")
        self.status_lbl.setText("Scan failed")
        self._show_toast(f"Scan warning: {err_msg}", "error")

    def _rebuild_items_cards(self):
        # Clear existing cards from layout (except stretch and empty state)
        for i in reversed(range(self.items_layout.count())):
            widget = self.items_layout.itemAt(i).widget()
            if isinstance(widget, StorageItemCard):
                widget.setParent(None)
                widget.deleteLater()

        self.cards_map.clear()

        # Build cards
        for item in self.items:
            card = StorageItemCard(item)
            card.selection_toggled.connect(self._on_card_selection_changed)
            self.cards_map[item.id] = card
            # Insert before empty_state and stretch
            self.items_layout.insertWidget(self.items_layout.count() - 2, card)

        self._filter_cards()

    def _filter_cards(self):
        visible_count = 0
        q = self.search_query.lower()

        for item in self.items:
            card = self.cards_map.get(item.id)
            if not card:
                continue

            matches_cat = (self.active_category == "all" or item.category == self.active_category)
            matches_query = (not q or q in item.name.lower() or q in item.path.lower())

            should_show = matches_cat and matches_query
            card.setVisible(should_show)
            if should_show:
                visible_count += 1

        if visible_count == 0:
            self.empty_state.show()
        else:
            self.empty_state.hide()

    def _set_active_category(self, cat_id: str):
        self.active_category = cat_id
        for btn in self.tabs_group:
            is_active = (btn.property("category_id") == cat_id)
            btn.setProperty("active", "true" if is_active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._filter_cards()

    def _on_search_changed(self, text: str):
        self.search_query = text.strip()
        self._filter_cards()

    def _on_card_selection_changed(self, item_id: str, is_checked: bool):
        self._update_selection_summary()

    def _select_all_safe(self):
        for item in self.items:
            if item.risk_level == "safe":
                item.selected = True
                card = self.cards_map.get(item.id)
                if card:
                    card.cb.setChecked(True)
        self._update_selection_summary()

    def _deselect_all(self):
        for item in self.items:
            item.selected = False
            card = self.cards_map.get(item.id)
            if card:
                card.cb.setChecked(False)
        self._update_selection_summary()

    def _update_selection_summary(self):
        selected_items = [i for i in self.items if i.selected]
        selected_bytes = sum(i.size_bytes for i in selected_items)
        size_formatted = format_bytes(selected_bytes)

        self.lbl_hero_reclaim.setText(size_formatted)
        self.lbl_footer_summary.setText(f"Selected: {len(selected_items)} items ({size_formatted})")

        if selected_items:
            self.btn_clean.setEnabled(True)
            self.btn_clean.setText(f"Clean Selected ({size_formatted})")
        else:
            self.btn_clean.setEnabled(False)
            self.btn_clean.setText("Clean Selected (0.00 GB)")

    def _open_clean_dialog(self):
        selected_items = [i for i in self.items if i.selected]
        if not selected_items:
            return

        dlg = ConfirmCleanDialog(selected_items, self)
        if dlg.exec() == ConfirmCleanDialog.Accepted:
            self._execute_clean(selected_items)

    def _execute_clean(self, selected_items: list[StorageItem]):
        if self.is_cleaning:
            return
        self.is_cleaning = True
        self.btn_clean.setEnabled(False)
        self.btn_clean.setText("Cleaning in progress...")
        self.status_dot.setStyleSheet("color: #f59e0b; font-size: 10px;")
        self.status_lbl.setText("Deleting selected files...")

        paths = [i.path for i in selected_items]
        total_reclaimed = sum(i.size_bytes for i in selected_items)

        self.clean_worker = CleanWorker(paths)
        self.clean_worker.progress_signal.connect(
            lambda name, cur, tot: self.status_lbl.setText(f"Cleaning ({cur}/{tot}): {name}")
        )
        self.clean_worker.finished_signal.connect(
            lambda deleted, errors: self._on_clean_finished(deleted, errors, total_reclaimed)
        )
        self.clean_worker.error_signal.connect(self._on_clean_error)
        self.clean_worker.start()

    def _on_clean_finished(self, deleted: list[str], errors: list[str], total_reclaimed: int):
        self.is_cleaning = False
        self.status_dot.setStyleSheet("color: #10b981; font-size: 10px;")
        self.status_lbl.setText("Clean complete")

        deleted_set = set(deleted)
        actual_reclaimed = sum(i.size_bytes for i in self.scanned_items if i.path in deleted_set)

        if deleted and actual_reclaimed > 0:
            cdlg = CelebrationDialog(format_bytes(actual_reclaimed), self)
            cdlg.exec()
            if errors:
                self._show_toast(f"Reclaimed {format_bytes(actual_reclaimed)}. {len(errors)} locked item(s) skipped.", "info")
        elif errors:
            self._show_toast(f"Clean failed: {errors[0]}", "error")
        else:
            self._show_toast("No items were removed.", "info")

        # Run fresh scan
        self.start_scan()

    def _on_clean_error(self, err_msg: str):
        self.is_cleaning = False
        self.btn_clean.setEnabled(True)
        self.status_dot.setStyleSheet("color: #f43f5e; font-size: 10px;")
        self.status_lbl.setText("Clean error")
        self._show_toast(f"Error during clean: {err_msg}", "error")

    def _show_toast(self, text: str, toast_type: str = "info"):
        toast = ToastNotification(text, toast_type, self)
        # Position at bottom-right
        x = self.width() - toast.width() - 32
        y = self.height() - toast.height() - 74
        toast.move(x, y)
        toast.show()
