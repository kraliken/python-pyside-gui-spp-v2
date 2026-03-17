# ui/views/master_data/partner/edit_view.py
#
# Partnerek beállítás nézet.
# C1: Lekérdezés gomb → DB lekérdezés → táblázat feltöltése + rekordszám label.
# C2 (szerkesztés/törlés): még NEM implementálva.
# DB tábla: dbo.Partner_mapping  (UMS_parnter — typo az adatbázisban)

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTableView,
    QHeaderView,
    QLineEdit,
    QFrame,
    QSizePolicy,
    QMessageBox,
)
from PySide6.QtCore import Qt, QTimer
from models.pandas_model import PandasModel
from database.database import DatabaseManager
from ui.dialogs.db_operation_progress import DbOperationProgressDialog
from ui.icons import (
    ICON_SEARCH,
    ICON_PLUS,
    ICON_TRASH,
    ICON_SAVE,
    set_button_icon,
    CLR_PRIMARY,
    CLR_PRIMARY_DIS,
    CLR_SECONDARY,
    CLR_SECONDARY_DIS,
    CLR_DANGER,
    CLR_DANGER_DIS,
)

# DB oszlop → megjelenítési név leképezés (UMS_parnter: typo az adatbázisban)
_COL_MAP = {
    "UMS_parnter": "UMS partner",
    "Combosoft_partner": "Combosoft partner",
}


class PartnerEditView(QWidget):
    def __init__(self):
        super().__init__()
        self._selected_count = 0
        self._db = DatabaseManager()
        self._progress_dialog = None
        self._setup_ui()

    # ------------------------------------------------------------------ #
    #  UI felépítés                                                        #
    # ------------------------------------------------------------------ #

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 16, 0, 16)
        main_layout.setSpacing(12)

        # --- Cím ---
        title = QLabel("Partnerek")
        title.setObjectName("view_title")
        main_layout.addWidget(title)

        # --- Eszközsáv ---
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.setContentsMargins(0, 0, 24, 0)

        self.query_button = QPushButton("Lekérdezés")
        set_button_icon(self.query_button, ICON_SEARCH, CLR_PRIMARY, CLR_PRIMARY_DIS)
        self.query_button.clicked.connect(self._prepare_query)
        toolbar.addWidget(self.query_button)

        self.add_row_button = QPushButton("Új sor")
        self.add_row_button.setObjectName("secondary_button")
        set_button_icon(self.add_row_button, ICON_PLUS, CLR_SECONDARY, CLR_SECONDARY_DIS)
        self.add_row_button.setEnabled(False)
        toolbar.addWidget(self.add_row_button)

        self.delete_button = QPushButton("Törlés")
        self.delete_button.setObjectName("delete_button")
        set_button_icon(self.delete_button, ICON_TRASH, CLR_DANGER, CLR_DANGER_DIS)
        self.delete_button.setEnabled(False)
        toolbar.addWidget(self.delete_button)

        self.save_button = QPushButton("Mentés")
        set_button_icon(self.save_button, ICON_SAVE, CLR_PRIMARY, CLR_PRIMARY_DIS)
        self.save_button.setEnabled(False)
        toolbar.addWidget(self.save_button)

        toolbar.addStretch()

        self.record_count_label = QLabel("")
        self.record_count_label.setObjectName("record_count_label")
        toolbar.addWidget(self.record_count_label)

        main_layout.addLayout(toolbar)

        # --- Tartalom (táblázat + jobb panel) ---
        content_layout = QHBoxLayout()
        content_layout.setSpacing(0)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # Bal: info label (kezdeti állapot) + táblázat (lekérdezés után)
        table_area = QWidget()
        table_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table_area_layout = QVBoxLayout(table_area)
        table_area_layout.setContentsMargins(0, 0, 0, 0)
        table_area_layout.setSpacing(0)

        self.info_label = QLabel(
            "Kattints a Lekérdezés gombra a partnerek betöltéséhez"
        )
        self.info_label.setObjectName("empty_label")
        self.info_label.setAlignment(Qt.AlignCenter)
        table_area_layout.addWidget(self.info_label)

        self.table_view = QTableView()
        self.table_view.setSortingEnabled(True)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSelectionBehavior(QTableView.SelectRows)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table_view.hide()
        table_area_layout.addWidget(self.table_view)

        content_layout.addWidget(table_area, 1)

        # Jobb: részlet panel
        detail_panel = QFrame()
        detail_panel.setObjectName("detail_panel")
        detail_panel.setFixedWidth(280)
        detail_panel.setStyleSheet("QFrame#detail_panel { background: white; }")
        detail_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(16, 16, 16, 16)
        detail_layout.setSpacing(10)

        panel_title = QLabel("Kiválasztott partner adatai")
        panel_title.setObjectName("detail_panel_title")
        panel_title.setWordWrap(True)
        detail_layout.addWidget(panel_title)

        detail_layout.addSpacing(4)

        detail_layout.addWidget(self._make_field_label("UMS partner"))
        self.ums_partner_edit = QLineEdit()
        self.ums_partner_edit.setEnabled(False)
        detail_layout.addWidget(self.ums_partner_edit)

        detail_layout.addWidget(self._make_field_label("Combosoft partner"))
        self.combosoft_partner_edit = QLineEdit()
        self.combosoft_partner_edit.setEnabled(False)
        detail_layout.addWidget(self.combosoft_partner_edit)

        detail_layout.addStretch()

        content_layout.addWidget(detail_panel)

        main_layout.addLayout(content_layout, 1)

    # ------------------------------------------------------------------ #
    #  Lekérdezés (C1)                                                    #
    # ------------------------------------------------------------------ #

    def _prepare_query(self):
        self._progress_dialog = DbOperationProgressDialog()
        self._progress_dialog.set_message("Adatok lekérdezése folyamatban...")
        self._progress_dialog.show()
        QTimer.singleShot(100, self._load_data)

    def _load_data(self):
        try:
            df = self._db.query_partner_mapping()
            df = df.drop(columns=["ID"], errors="ignore")
            df = df.rename(columns=_COL_MAP)

            self.table_view.setModel(PandasModel(df))
            self.info_label.hide()
            self.table_view.show()

            self.record_count_label.setText(f"{len(df)} rekord")
        except Exception as e:
            QMessageBox.critical(
                self,
                "Adatbázis hiba",
                f"Sikertelen lekérdezés.\n\nRészletek:\n{e}",
            )
            self.record_count_label.setText("")
        finally:
            if self._progress_dialog:
                self._progress_dialog.accept()
                self._progress_dialog = None

    # ------------------------------------------------------------------ #
    #  Segédek                                                             #
    # ------------------------------------------------------------------ #

    def _make_field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-size: 12px; color: #495057; background: transparent;")
        return label

    def _update_toolbar_state(self):
        n = self._selected_count
        self.delete_button.setText(f"  Törlés ({n})" if n > 0 else "  Törlés")
        self.delete_button.setEnabled(n > 0)
