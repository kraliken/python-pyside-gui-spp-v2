from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QLabel,
    QListWidget,
    QTableView,
    QHeaderView,
    QMessageBox,
    QApplication,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor
import pandas as pd
from models.pandas_model import PandasModel
from ui.dialogs.db_operation_progress import DbOperationProgressDialog
from database.database import DatabaseManager
from ui.icons import (
    ICON_UPLOAD, ICON_SAVE, ICON_TRASH, set_button_icon,
    CLR_PRIMARY, CLR_PRIMARY_DIS, CLR_DANGER, CLR_DANGER_DIS,
)


class _PlaceholderTableView(QTableView):
    """QTableView that renders 'Nincs adat' in the viewport when the model has no rows."""

    _PLACEHOLDER = "Nincs adat"

    def paintEvent(self, event):
        super().paintEvent(event)
        model = self.model()
        if model is None or model.rowCount() == 0:
            painter = QPainter(self.viewport())
            painter.setPen(QColor("#868e96"))
            painter.drawText(self.viewport().rect(), Qt.AlignCenter, self._PLACEHOLDER)


class BaseImportView(QWidget):
    """Közös alaposztály az összes import nézethez.

    Az osztály kiszervezi a kétpaneles elrendezést, a megerősítő/progress
    dialógusok kezelését és a táblázat frissítését. A leszármazottaknak a
    következő metódusokat kell implementálniuk:
      - load_files()           — fájl(ok) betöltése és df feltöltése
      - get_data_for_save()    — a mentendő DataFrame visszaadása
      - validate_for_insert()  — validációs logika
      - run_database_save()    — tényleges DB mentés (hide_progress() hívással)
    """

    def __init__(self):
        super().__init__()
        self.progress_dialog = None
        self.db = DatabaseManager()

    def setup_ui(self, title: str, import_button_label: str = "Importálás"):
        """Felépíti a kétpaneles elrendezést.

        Felül: oldalnézet-cím (view_title stílussal).
        Bal oldal: fehér panel (left_panel) — alcím, fájl-kiválasztó gomb,
                   no_file_label / fájllista, Törlés gomb.
        Jobb oldal: Mentés gomb + header_row (subclass bővítheti),
                    empty_label / táblázat.

        A subclass az __init__-ben a self.header_row-ba szúrhat be extra
        widgeteket a save_button UTÁN (insert pozíció: 1).
        """
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Oldalnézet-cím ---
        self.title_label = QLabel(title)
        self.title_label.setObjectName("view_title")
        title_bar = QWidget()
        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(24, 16, 24, 8)
        title_bar_layout.addWidget(self.title_label)
        main_layout.addWidget(title_bar)

        # --- Kétpaneles tartalom ---
        content_layout = QHBoxLayout()
        content_layout.setSpacing(0)
        content_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addLayout(content_layout, 1)

        # ===== BAL PANEL =====
        left_panel = QWidget()
        left_panel.setObjectName("left_panel")
        left_panel_layout = QVBoxLayout(left_panel)
        left_panel_layout.setContentsMargins(16, 12, 16, 16)
        left_panel_layout.setSpacing(10)

        # left_subtitle = QLabel(title)
        # left_subtitle.setStyleSheet(
        #     "font-size: 13px; font-weight: 600; color: #212529; background: transparent;"
        # )
        # left_panel_layout.addWidget(left_subtitle)

        self.select_button = QPushButton(import_button_label)
        set_button_icon(self.select_button, ICON_UPLOAD, CLR_PRIMARY, CLR_PRIMARY_DIS)
        self.select_button.clicked.connect(self.load_files)
        left_panel_layout.addWidget(self.select_button)

        # Fájlterület: mindig látható bordered doboz; no_file_label ↔ file_list_widget váltják
        file_area = QWidget()
        file_area.setObjectName("file_area_box")
        file_area.setStyleSheet(
            "QWidget#file_area_box { background: white; border: 1px solid #dee2e6; border-radius: 4px; }"
        )
        file_area_layout = QVBoxLayout(file_area)
        file_area_layout.setContentsMargins(4, 4, 4, 4)
        file_area_layout.setSpacing(0)

        self.no_file_label = QLabel("Nincs betöltött fájl")
        self.no_file_label.setObjectName("no_file_label")
        self.no_file_label.setAlignment(Qt.AlignCenter)
        file_area_layout.addWidget(self.no_file_label)

        self.file_list_widget = QListWidget()
        self.file_list_widget.setStyleSheet("QListWidget { border: none; background: transparent; }")
        self.file_list_widget.hide()
        file_area_layout.addWidget(self.file_list_widget, 1)

        left_panel_layout.addWidget(file_area, 1)

        self.clear_button = QPushButton("Törlés")
        self.clear_button.setObjectName("clear_button")
        set_button_icon(self.clear_button, ICON_TRASH, CLR_DANGER, CLR_DANGER_DIS)
        self.clear_button.clicked.connect(self.clear_data)
        self.clear_button.setEnabled(False)
        left_panel_layout.addWidget(self.clear_button)

        content_layout.addWidget(left_panel, stretch=3)

        # Fájllista láthatóságának automatikus kezelése modell-jelzőkkel
        self.file_list_widget.model().rowsInserted.connect(self._update_file_list_state)
        self.file_list_widget.model().modelReset.connect(self._update_file_list_state)

        # ===== JOBB PANEL =====
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(16, 12, 16, 16)
        right_layout.setSpacing(10)

        self.save_button = QPushButton("Mentés adatbázisba")
        set_button_icon(self.save_button, ICON_SAVE, CLR_PRIMARY, CLR_PRIMARY_DIS)
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.confirm_and_save)

        self.header_row = QHBoxLayout()
        self.header_row.setSpacing(8)
        self.header_row.addWidget(self.save_button, alignment=Qt.AlignVCenter)
        self.header_row.addStretch()
        right_layout.addLayout(self.header_row)

        # Táblázatterület: mindig látható; üres állapotban a _PlaceholderTableView
        # "Nincs adat" szöveget rajzol a viewport-ra.
        self.table_view = _PlaceholderTableView()
        self.table_view.setSortingEnabled(True)
        right_layout.addWidget(self.table_view, 1)

        content_layout.addWidget(right_widget, stretch=10)

    # -------------------------------------------------------------------------
    # Közös metódusok
    # -------------------------------------------------------------------------

    def _update_file_list_state(self):
        """Váltja a no_file_label / file_list_widget láthatóságát."""
        has_files = self.file_list_widget.count() > 0
        self.no_file_label.setVisible(not has_files)
        self.file_list_widget.setVisible(has_files)

    def confirm_and_save(self):
        """Közös mentési folyamat: üresség-ellenőrzés → validáció → dialog → progress → DB."""
        data = self.get_data_for_save()

        if data.empty:
            QMessageBox.warning(self, "Hiba", "Nincs betöltött adat a mentéshez.")
            return

        if not self.validate_for_insert(data):
            return

        reply = QMessageBox.question(
            self,
            "Megerősítés",
            "Biztosan szeretnéd az adatokat menteni az adatbázisba?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        self.show_progress("Adatok mentése folyamatban...")
        QTimer.singleShot(100, lambda: self.run_database_save(data))

    def clear_data(self):
        """Alap törlés: fájllista, táblázat és gombok visszaállítása.

        A subclassoknak super().clear_data() hívása után kell nullázniuk
        a saját DataFrame-jüket és egyéb állapotot.
        """
        self.file_list_widget.clear()
        self._update_file_list_state()  # clear() modelReset-et vált ki, de explicit is hívjuk
        self.table_view.setModel(None)
        self.clear_button.setEnabled(False)
        self.save_button.setEnabled(False)

    def show_progress(self, message: str = "Adatok mentése folyamatban..."):
        """Megjeleníti a DB művelet progress dialógust."""
        self.progress_dialog = DbOperationProgressDialog()
        self.progress_dialog.set_message(message)
        self.progress_dialog.show()
        QApplication.processEvents()

    def hide_progress(self):
        """Bezárja a progress dialógust (a run_database_save végén hívandó)."""
        if self.progress_dialog:
            self.progress_dialog.accept()
            self.progress_dialog = None

    def update_table_view(
        self,
        df: pd.DataFrame,
        formatters: dict | None = None,
        alignments: dict | None = None,
    ):
        """Frissíti a táblázatot a megadott DataFrame-mel és formázókkal."""
        if df.empty:
            return
        model = PandasModel(
            df,
            formatters=formatters or {},
            alignments=alignments or {},
        )
        self.table_view.setModel(model)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

    # -------------------------------------------------------------------------
    # Entitásspecifikus metódusok — subclassoknak kötelező implementálni
    # -------------------------------------------------------------------------

    def load_files(self):
        """Fájl(ok) megnyitása, beolvasása és a belső DataFrame feltöltése."""
        raise NotImplementedError

    def get_data_for_save(self) -> pd.DataFrame:
        """Visszaadja a mentendő DataFrame-et (validáció és DB mentés előtt)."""
        raise NotImplementedError

    def validate_for_insert(self, df: pd.DataFrame) -> bool:
        """Ellenőrzi a mentési feltételeket; False esetén hibaüzenetet jelenít meg."""
        raise NotImplementedError

    def run_database_save(self, df: pd.DataFrame):
        """Elvégzi a DB mentést; végén kötelező hide_progress() hívás."""
        raise NotImplementedError
