# ui/views/bank/query_view.py
#
# BankQueryView — Bank staging tábla lekérdezési nézet.
#
# Ez a nézet a Bank_stage adatbázistábla tartalmát jeleníti meg.
# A staging tábla egy átmeneti tároló: ide kerülnek az importált banki adatok,
# mielőtt a tárolt eljárás a végleges Bank_Hist táblába menti őket.
#
# Eszközsáv gombok:
#   - Lekérdezés:        betölti a Bank_stage tábla aktuális tartalmát
#   - Mentés history-ba: a tárolt eljárás hívásával áthelyezi az adatokat Bank_Hist-be
#   - Törlés:            törli a Bank_stage tábla összes sorát
#
# Gombaktivációs logika:
#   - Lekérdezés után: „Mentés history-ba" és „Törlés" gombok aktívak lesznek
#   - Törlés / Mentés után: a gombok ismét tiltottá válnak (_has_data = False)

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


class BankQueryView(QWidget):
    """Bank staging tábla lekérdező nézet.

    Megjeleníti a Bank_stage tábla aktuális tartalmát, és lehetővé teszi
    az adatok history táblába mentését vagy törlését.
    """

    def __init__(self):
        super().__init__()

        # Fő függőleges elrendezés: eszközsáv felül, tartalom alul
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # --- Eszközsáv (cím + gombok vízszintesen) ---
        control_panel_layout = QHBoxLayout()
        control_panel_layout.setSpacing(8)

        self.title_label = QLabel("Bank stage tábla lekérdezése")
        self.title_label.setObjectName("view_title")  # QSS: 18px félkövér
        control_panel_layout.addWidget(self.title_label)

        control_panel_layout.addStretch()  # a cím és a gombok közé rugalmas tér kerül

        # Lekérdezés gomb — betölti a Bank_stage tábla adatait
        self.query_button = QPushButton("Lekérdezés")
        set_button_icon(self.query_button, ICON_SEARCH, CLR_PRIMARY, CLR_PRIMARY_DIS)
        control_panel_layout.addWidget(self.query_button)

        # Dátumválasztó — kikommentelve (jövőbeli dátumszűrő funkcióhoz tervezve)
        # self.hist_date_edit = QDateEdit()
        # self.hist_date_edit.setDisplayFormat("yyyy. MM. dd.")
        # self.hist_date_edit.setCalendarPopup(True)
        # self.hist_date_edit.setDate(QDate.currentDate())
        # self.hist_date_edit.setFixedWidth(158)
        # self.hist_date_edit.setEnabled(False)
        # control_panel_layout.addWidget(self.hist_date_edit, alignment=Qt.AlignVCenter)

        # Mentés history-ba gomb — tiltott, amíg nincs lekérdezett adat
        self.save_to_bank_hist_table_button = QPushButton("Mentés history-ba")
        self.save_to_bank_hist_table_button.setObjectName("secondary_button")
        set_button_icon(
            self.save_to_bank_hist_table_button,
            ICON_HISTORY,
            CLR_SECONDARY,
            CLR_SECONDARY_DIS,
        )
        self.save_to_bank_hist_table_button.setEnabled(False)
        self.save_to_bank_hist_table_button.clicked.connect(
            self.save_to_bank_hist_table
        )
        control_panel_layout.addWidget(
            self.save_to_bank_hist_table_button, alignment=Qt.AlignVCenter
        )

        # Törlés gomb — törli a Bank_stage összes sorát; tiltott, amíg nincs adat
        self.delete_button = QPushButton("Törlés")
        self.delete_button.setObjectName("delete_button")
        set_button_icon(self.delete_button, ICON_TRASH, CLR_DANGER, CLR_DANGER_DIS)
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self.delete_data)
        control_panel_layout.addWidget(self.delete_button)

        layout.addLayout(control_panel_layout)

        # --- Tartalom terület (info szöveg vagy táblázat) ---
        self.center_widget = QWidget()
        self.center_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.content_layout = QVBoxLayout()
        self.center_widget.setLayout(self.content_layout)

        # Tájékoztató szöveg — lekérdezés előtt látható
        self.info_label = QLabel(
            "Kattints a Lekérdezés gombra a Bank_stage tábla adatainak betöltéséhez"
        )
        self.info_label.setObjectName("empty_label")  # QSS: szürke, középre igazított
        self.info_label.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(self.info_label)

        # Táblázat — lekérdezés után jelenik meg (kezdetben rejtett)
        self.table_view = QTableView()
        self.table_view.setSortingEnabled(True)
        self.table_view.hide()
        self.content_layout.addWidget(self.table_view)

        layout.addWidget(self.center_widget)
        self.setLayout(layout)

        # Belső állapot
        self.progress_dialog = None  # az aktív progress dialógus referenciája
        self._has_data = False  # True, ha van megjelenített adat → gombok aktívak

        # Adatbázis kapcsolat és lekérdezés gomb bekötése
        self.db = DatabaseManager()
        self.query_button.clicked.connect(self.prepare_query)

    def _update_save_button_state(self):
        """Szinkronizálja a „Mentés history-ba" gomb aktív/tiltott állapotát
        a _has_data flag értékével."""
        self.save_to_bank_hist_table_button.setEnabled(self._has_data)

    def prepare_query(self):
        """Lekérdezés gomb handler: megjeleníti a progress dialógust,
        majd 100ms késleltetéssel elindítja az adatbetöltést.

        A QTimer.singleShot() azért kell, hogy a progress dialógus
        valóban megjelenjen, mielőtt a DB hívás blokkolja a GUI szálat.
        """
        self.progress_dialog = DbOperationProgressDialog()
        self.progress_dialog.set_message("Adatok lekérdezése folyamatban...")
        self.progress_dialog.show()

        QTimer.singleShot(100, self.load_data)

    def load_data(self):
        """Lekérdezi a Bank_stage tábla adatait és megjeleníti a táblázatban.

        Column11 (összeg) különleges megjelenítése: magyar ezres elválasztó
        (szóköz) és tizedes vesszővel (pl. "1 234 567,89").
        """
        try:
            df = self.db.query_bank_data()
            if df.empty:
                # Üres tábla esetén tájékoztató szöveg, gombok tiltva
                self._has_data = False
                self.info_label.setText(
                    "A Bank_stage tábla jelenleg üres, nincs megjeleníthető adat."
                )
                self._update_save_button_state()
                self.delete_button.setEnabled(False)
            else:
                # Összeg formázó: "1234.56" → "1 234,56" (magyar számformátum)
                def format_thousands(val):
                    try:
                        number = float(str(val).replace(",", "."))
                        return f"{number:,.2f}".replace(",", " ").replace(".", ",")
                    except ValueError:
                        return val

                formatters = {"Column11": format_thousands}
                alignments = {"Column11": Qt.AlignRight | Qt.AlignVCenter}

                model = PandasModel(df, formatters=formatters, alignments=alignments)
                self.table_view.setModel(model)
                header = self.table_view.horizontalHeader()
                header.setSectionResizeMode(
                    QHeaderView.Interactive
                )  # húzható oszlopszélesség
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
            # Progress dialógus bezárása — a finally blokk hiba esetén is lefut
            if hasattr(self, "progress_dialog") and self.progress_dialog:
                self.progress_dialog.accept()
                self.progress_dialog = None

    def delete_data(self):
        """Törlés gomb handler: megerősítő kérdés után törli a Bank_stage tartalmát."""
        confirm = QMessageBox.question(
            self,
            "Megerősítés",
            "Biztosan törölni szeretnéd a banki adatokat?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if confirm == QMessageBox.Yes:
            # Progress dialógus megjelenítése, majd 100ms után törlés
            self.progress_dialog = DbOperationProgressDialog()
            self.progress_dialog.set_message("Adatok törlése folyamatban...")
            self.progress_dialog.show()

            QTimer.singleShot(100, self.perform_delete_data)

    def perform_delete_data(self):
        """Elvégzi a tényleges törlést az adatbázisban, majd frissíti a nézetet."""
        success, message = self.db.delete_bank_stage()

        if self.progress_dialog:
            self.progress_dialog.accept()
            self.progress_dialog = None

        if success:
            QMessageBox.information(self, "Sikeres törlés", message)
            # Táblázat elrejtése, tájékoztató szöveg visszaállítása
            self.table_view.hide()
            self.info_label.setText("A banki adatok törölve lettek.")
            self.info_label.show()
            self._has_data = False
            self._update_save_button_state()
            self.delete_button.setEnabled(False)
        else:
            QMessageBox.critical(self, "Hiba", f"Törlés sikertelen:\n\n{message}")

    def save_to_bank_hist_table(self):
        """„Mentés history-ba" gomb handler: megerősítő kérdés után
        a tárolt eljárás hívásával a staging adatokat Bank_Hist-be menti."""
        confirm = QMessageBox.question(
            self,
            "Megerősítés",
            "Biztosan menteni szeretnéd a banki adatokat a Bank_Hist táblába?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if confirm == QMessageBox.Yes:
            self.progress_dialog = DbOperationProgressDialog()
            self.progress_dialog.set_message("Adatok mentése folyamatban...")
            self.progress_dialog.show()

            QTimer.singleShot(100, self.perform_save_to_irems_hist_table)

    def perform_save_to_irems_hist_table(self):
        """Elvégzi a tényleges history-ba mentést a tárolt eljárás hívásával.

        Megjegyzés: a hist_date_edit jelenleg kikommentelve van, ezért
        a date_str változó nem kerül átadásra a call_bank_insert1()-nek.
        """
        date_str = self.hist_date_edit.date().toString("yyyy-MM-dd")
        success, message = self.db.call_bank_insert1()

        if self.progress_dialog:
            self.progress_dialog.accept()
            self.progress_dialog = None

        if success:
            QMessageBox.information(self, "Sikeres mentés", message)
            # Táblázat elrejtése mentés után
            self.table_view.hide()
            self.info_label.setText("A banki adatok mentve a Bank_Hist táblába.")
            self.info_label.show()
            self._has_data = False
            self._update_save_button_state()
            self.delete_button.setEnabled(False)
        else:
            QMessageBox.critical(self, "Hiba", f"Mentés sikertelen:\n\n{message}")
