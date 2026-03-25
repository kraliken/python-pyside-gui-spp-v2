# ui/views/customer/query_view.py
#
# CustomerQueryView — Vevő staging tábla lekérdezési nézet.
#
# Ez a nézet az IremsVevo_stage adatbázistábla tartalmát jeleníti meg.
# A staging tábla egy átmeneti tároló: ide kerülnek az importált vevői adatok,
# mielőtt a tárolt eljárás a végleges Irems_Hist táblába menti őket.
#
# Eszközsáv gombok:
#   - Lekérdezés:        betölti az IremsVevo_stage tábla tartalmát
#   - Dátumválasztó:     könyvelési dátum kiválasztása (mindig mai napot mutat)
#   - Mentés history-ba: a tárolt eljárás hívásával áthelyezi az adatokat Hist-be
#   - Törlés:            törli az IremsVevo_stage tábla összes sorát
#
# A VendorQueryView-val azonos szerkezetű, csak az adatbázis tábla neve különbözik.

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QSizePolicy,
    QMessageBox,
    QTableView,
    QHeaderView,
    QDateEdit,
)
from PySide6.QtCore import Qt, QTimer, QDate
import pandas as pd
from database.database import DatabaseManager
from ui.icons import (
    ICON_SEARCH,
    ICON_HISTORY,
    ICON_TRASH,
    set_button_icon,
    CLR_PRIMARY,
    CLR_PRIMARY_DIS,
    CLR_SECONDARY,
    CLR_SECONDARY_DIS,
    CLR_DANGER,
    CLR_DANGER_DIS,
)
from models.pandas_model import PandasModel
from ui.dialogs.db_operation_progress import DbOperationProgressDialog


class CustomerQueryView(QWidget):
    """Vevő staging tábla lekérdező nézet.

    Megjeleníti az IremsVevo_stage tábla aktuális tartalmát,
    és lehetővé teszi az adatok Irems_Hist táblába mentését vagy törlését.
    """

    def __init__(self):
        super().__init__()

        # Fő függőleges elrendezés
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # --- Eszközsáv ---
        control_panel_layout = QHBoxLayout()
        control_panel_layout.setSpacing(8)

        # Nézetcím (QSS "view_title": 18px félkövér)
        self.title_label = QLabel("Vevő stage tábla lekérdezése")
        self.title_label.setObjectName("view_title")
        self.title_label.setAlignment(Qt.AlignLeft)
        control_panel_layout.addWidget(self.title_label, alignment=Qt.AlignVCenter)

        control_panel_layout.addStretch()

        # Lekérdezés gomb
        self.query_button = QPushButton("Lekérdezés")
        set_button_icon(self.query_button, ICON_SEARCH, CLR_PRIMARY, CLR_PRIMARY_DIS)
        control_panel_layout.addWidget(self.query_button, alignment=Qt.AlignVCenter)

        # Dátumválasztó — könyvelési dátum (history mentésnél átadódik a tárolt eljárásnak)
        # Disabled állapot: szerkeszthetetlen, de az ikon és a mai dátum látható
        self.hist_date_edit = QDateEdit()
        self.hist_date_edit.setDisplayFormat("yyyy. MM. dd.")
        self.hist_date_edit.setCalendarPopup(True)
        self.hist_date_edit.setDate(QDate.currentDate())
        self.hist_date_edit.setFixedWidth(158)
        self.hist_date_edit.setEnabled(False)
        control_panel_layout.addWidget(self.hist_date_edit, alignment=Qt.AlignVCenter)

        # Mentés history-ba gomb — csak lekérdezés után aktív
        self.save_to_irems_hist_table_button = QPushButton("Mentés history-ba")
        self.save_to_irems_hist_table_button.setObjectName("secondary_button")
        set_button_icon(
            self.save_to_irems_hist_table_button,
            ICON_HISTORY,
            CLR_SECONDARY,
            CLR_SECONDARY_DIS,
        )
        self.save_to_irems_hist_table_button.setEnabled(False)
        self.save_to_irems_hist_table_button.clicked.connect(
            self.save_to_irems_hist_table
        )
        control_panel_layout.addWidget(
            self.save_to_irems_hist_table_button, alignment=Qt.AlignVCenter
        )

        # Törlés gomb — csak lekérdezés után aktív
        self.delete_button = QPushButton("Törlés")
        self.delete_button.setObjectName("delete_button")
        set_button_icon(self.delete_button, ICON_TRASH, CLR_DANGER, CLR_DANGER_DIS)
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self.delete_data)
        control_panel_layout.addWidget(self.delete_button, alignment=Qt.AlignVCenter)

        layout.addLayout(control_panel_layout)

        # --- Tartalom terület ---
        self.center_widget = QWidget()
        self.center_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.content_layout = QVBoxLayout()
        self.center_widget.setLayout(self.content_layout)

        # Tájékoztató szöveg lekérdezés előtt
        self.info_label = QLabel(
            "Kattints a Lekérdezés gombra az IremsVevo_stage tábla adatainak betöltéséhez"
        )
        self.info_label.setObjectName("empty_label")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(self.info_label)

        # Táblázat — kezdetben rejtett
        self.table_view = QTableView()
        self.table_view.setSortingEnabled(True)
        self.table_view.hide()
        self.content_layout.addWidget(self.table_view)

        layout.addWidget(self.center_widget)
        self.setLayout(layout)

        # Belső állapot
        self.progress_dialog = None
        self._has_data = False  # True = van adat → gombok aktívak

        self.db = DatabaseManager()
        self.query_button.clicked.connect(self.prepare_query)

    def _update_save_button_state(self):
        """'Mentés history-ba' gomb állapotának szinkronizálása a _has_data flag alapján."""
        self.save_to_irems_hist_table_button.setEnabled(self._has_data)

    def prepare_query(self):
        """Progress dialógus megjelenítése, majd 100ms után adatbetöltés indítása.

        A QTimer.singleShot() késleltetés azért kell, hogy a dialógus valóban
        látható legyen, mielőtt a DB hívás blokkolja a GUI szálat.
        """
        self.progress_dialog = DbOperationProgressDialog()
        self.progress_dialog.set_message("Adatok lekérdezése folyamatban...")
        self.progress_dialog.show()

        QTimer.singleShot(100, self.load_data)

    def load_data(self):
        """Lekérdezi az IremsVevo_stage tábla adatait és megjeleníti a táblázatban."""
        try:
            df = self.db.query_customer_data()
            if df.empty:
                self._has_data = False
                self.info_label.setText(
                    "Az IremsVevo_stage tábla jelenleg üres, nincs megjeleníthető adat."
                )
                self._update_save_button_state()
                self.delete_button.setEnabled(False)
            else:
                # QHeaderView.Stretch: minden oszlop egyenlő szélességű
                model = PandasModel(df)
                self.table_view.setModel(model)
                self.table_view.horizontalHeader().setSectionResizeMode(
                    QHeaderView.Stretch
                )
                self.info_label.hide()
                self.table_view.show()
                self._has_data = True
                self._update_save_button_state()
                self.delete_button.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Adatbázis hiba",
                f"Sikertelen csatlakozás vagy lekérdezés.\n\nRészletek:\n{e}",
            )
            self._has_data = False
            self._update_save_button_state()
            self.delete_button.setEnabled(False)
        finally:
            # Progress dialógus lezárása hiba esetén is
            if hasattr(self, "progress_dialog") and self.progress_dialog:
                self.progress_dialog.accept()
                self.progress_dialog = None

    def delete_data(self):
        """Törlés gomb handler: megerősítő kérdés után törli az IremsVevo_stage tartalmát."""
        confirm = QMessageBox.question(
            self,
            "Megerősítés",
            "Biztosan törölni szeretnéd a vevő adatokat?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if confirm == QMessageBox.Yes:
            self.progress_dialog = DbOperationProgressDialog()
            self.progress_dialog.set_message("Adatok törlése folyamatban...")
            self.progress_dialog.show()

            QTimer.singleShot(100, self.perform_delete_data)

    def perform_delete_data(self):
        """Elvégzi a tényleges törlést az adatbázisban, majd frissíti a nézetet."""
        success, message = self.db.delete_customer_stage()

        if self.progress_dialog:
            self.progress_dialog.accept()
            self.progress_dialog = None

        if success:
            QMessageBox.information(self, "Sikeres törlés", message)
            self.table_view.hide()
            self.info_label.setText("A vevő adatok törölve lettek.")
            self.info_label.show()
            self._has_data = False
            self._update_save_button_state()
            self.delete_button.setEnabled(False)
        else:
            QMessageBox.critical(self, "Hiba", f"Törlés sikertelen:\n\n{message}")

    def save_to_irems_hist_table(self):
        """'Mentés history-ba' gomb handler: megerősítő kérdés után
        az IremsVevo_Stage adatait az Irems_Hist táblába menti."""
        confirm = QMessageBox.question(
            self,
            "Megerősítés",
            "Biztosan menteni szeretnéd a vevő adatokat az Irems_Hist táblába?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if confirm == QMessageBox.Yes:
            self.progress_dialog = DbOperationProgressDialog()
            self.progress_dialog.set_message("Adatok mentése folyamatban...")
            self.progress_dialog.show()

            QTimer.singleShot(100, self.perform_save_to_irems_hist_table)

    def perform_save_to_irems_hist_table(self):
        """Elvégzi a history-ba mentést: dátum kiolvasás + tárolt eljárás hívás.

        A dátum az 'yyyy-MM-dd' formátumban kerül át a dbo.vevo_insert1 eljáráshoz.
        """
        date_str = self.hist_date_edit.date().toString("yyyy-MM-dd")
        success, message = self.db.call_customer_insert1(date_str)

        if self.progress_dialog:
            self.progress_dialog.accept()
            self.progress_dialog = None

        if success:
            QMessageBox.information(self, "Sikeres mentés", message)
            self.table_view.hide()
            self.info_label.setText("A vevő adatok mentve az Irems_Hist táblába.")
            self.info_label.show()
            self._has_data = False
            self._update_save_button_state()
            self.delete_button.setEnabled(False)
        else:
            QMessageBox.critical(self, "Hiba", f"Mentés sikertelen:\n\n{message}")
