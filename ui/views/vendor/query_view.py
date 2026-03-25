# ui/views/vendor/query_view.py
#
# VendorQueryView — Szállító staging tábla lekérdezési nézet.
#
# Ez a nézet az IremsSzallito_stage adatbázistábla tartalmát jeleníti meg.
# A staging tábla egy átmeneti tároló: ide kerülnek az importált szállítói adatok,
# mielőtt a tárolt eljárás a végleges Irems_Hist táblába menti őket.
#
# Eszközsáv gombok:
#   - Lekérdezés:        betölti az IremsSzallito_stage tábla tartalmát
#   - Dátumválasztó:     könyvelési dátum kiválasztása (mindig mai napot mutat)
#   - Mentés history-ba: a tárolt eljárás hívásával áthelyezi az adatokat Hist-be
#   - Törlés:            törli az IremsSzallito_stage tábla összes sorát
#
# Gombaktivációs logika (_has_data flag):
#   - Lekérdezés után: „Mentés history-ba" és „Törlés" gombok aktívak lesznek
#   - Törlés / Mentés után: a gombok ismét tiltottá válnak

# PySide6 Qt widgetek importálása
from PySide6.QtWidgets import (
    QWidget,          # alap Qt widget — minden UI elem alaposztálya
    QVBoxLayout,      # függőleges elrendező (elemeket egymás alá rakja)
    QHBoxLayout,      # vízszintes elrendező (elemeket egymás mellé rakja)
    QPushButton,      # kattintható gomb
    QLabel,           # szöveg vagy kép megjelenítése
    QSizePolicy,      # widget méretezési viselkedése
    QMessageBox,      # felugró üzenet / megerősítő dialógus
    QTableView,       # táblázatos adatok megjelenítése (modell alapú)
    QHeaderView,      # táblázat fejlécének kezelője
    QDateEdit,        # dátumválasztó mező (naptárral)
)
# Qt alap típusok: Qt (igazítási konstansok), QTimer (késleltetett végrehajtás),
# QDate (aktuális dátum lekérdezéséhez)
from PySide6.QtCore import Qt, QTimer, QDate

import pandas as pd  # adatkezelés — a DB lekérdezés eredménye DataFrame formában érkezik

from database.database import DatabaseManager  # SQL Server kapcsolat és lekérdezések
from ui.icons import (
    ICON_SEARCH,       # nagyítólencse SVG ikon (lekérdezés gomb)
    ICON_HISTORY,      # óra/history SVG ikon (mentés history-ba)
    ICON_TRASH,        # kuka SVG ikon (törlés)
    set_button_icon,   # segédfüggvény: gombon SVG ikont állít be
    CLR_PRIMARY,       # elsődleges kék szín (aktív állapot)
    CLR_PRIMARY_DIS,   # elsődleges szürke szín (tiltott állapot)
    CLR_SECONDARY,     # másodlagos szürke szín (aktív)
    CLR_SECONDARY_DIS, # másodlagos szürke szín (tiltott)
    CLR_DANGER,        # vörös szín (aktív törlés gomb)
    CLR_DANGER_DIS,    # halvány vörös szín (tiltott törlés gomb)
)
from models.pandas_model import PandasModel                    # DataFrame → QTableView modell
from ui.dialogs.db_operation_progress import DbOperationProgressDialog  # várakozó dialógus


class VendorQueryView(QWidget):
    """Szállító staging tábla lekérdező nézet.

    Megjeleníti az IremsSzallito_stage tábla aktuális tartalmát,
    és lehetővé teszi az adatok Irems_Hist táblába mentését vagy törlését.
    """

    def __init__(self):
        super().__init__()  # QWidget __init__ hívása (szülőosztály inicializálása)

        # Fő függőleges elrendezés: eszközsáv felül, tartalom alul
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 12, 16, 12)  # belső margók (px): bal, felső, jobb, alsó
        layout.setSpacing(12)                       # elemek közötti távolság (px)

        # --- Eszközsáv (cím + gombok vízszintesen) ---
        control_panel_layout = QHBoxLayout()
        control_panel_layout.setSpacing(8)

        # Nézetcím — QSS "view_title" objektumnévvel formázva (18px félkövér)
        self.title_label = QLabel("Szállító lekérdezés")
        self.title_label.setObjectName("view_title")
        self.title_label.setAlignment(Qt.AlignLeft)
        control_panel_layout.addWidget(self.title_label, alignment=Qt.AlignVCenter)

        control_panel_layout.addStretch()  # rugalmas tér: cím és gombok közé kerül

        # Lekérdezés gomb — betölti az IremsSzallito_stage tábla adatait
        self.query_button = QPushButton("Lekérdezés")
        set_button_icon(self.query_button, ICON_SEARCH, CLR_PRIMARY, CLR_PRIMARY_DIS)
        control_panel_layout.addWidget(self.query_button, alignment=Qt.AlignVCenter)

        # Dátumválasztó — könyvelési dátum megadásához (history mentésnél átadódik a tárolt eljárásnak)
        # setCalendarPopup(True): naptár ikon jelenik meg kattintásra
        # setEnabled(False): a mező le van tiltva szerkesztésre, de az ikon látható
        # Mindig a mai napot mutatja — QDate.currentDate() az induláskori dátumot adja
        self.hist_date_edit = QDateEdit()
        self.hist_date_edit.setDisplayFormat("yyyy. MM. dd.")   # megjelenítési formátum
        self.hist_date_edit.setCalendarPopup(True)             # naptár ikon a jobb oldalon
        self.hist_date_edit.setDate(QDate.currentDate())       # alapértelmezett: mai nap
        self.hist_date_edit.setFixedWidth(158)                 # fix szélesség (px)
        self.hist_date_edit.setEnabled(False)                  # szerkesztés tiltva
        control_panel_layout.addWidget(self.hist_date_edit, alignment=Qt.AlignVCenter)

        # Mentés history-ba gomb — a szállítói staging adatokat az Irems_Hist táblába menti
        # A gomb csak lekérdezés után aktív (_has_data flag alapján)
        self.save_to_irems_hist_table_button = QPushButton("Mentés history-ba")
        self.save_to_irems_hist_table_button.setObjectName("secondary_button")  # QSS: átlátszó, szürke keret
        set_button_icon(
            self.save_to_irems_hist_table_button,
            ICON_HISTORY,
            CLR_SECONDARY,
            CLR_SECONDARY_DIS,
        )
        self.save_to_irems_hist_table_button.setEnabled(False)  # alapból tiltott
        self.save_to_irems_hist_table_button.clicked.connect(
            self.save_to_irems_hist_table  # kattintáskor meghívódó metódus
        )
        control_panel_layout.addWidget(
            self.save_to_irems_hist_table_button, alignment=Qt.AlignVCenter
        )

        # Törlés gomb — törli az IremsSzallito_stage összes sorát; alapból tiltott
        self.delete_button = QPushButton("Törlés")
        self.delete_button.setObjectName("delete_button")  # QSS: piros keret
        set_button_icon(self.delete_button, ICON_TRASH, CLR_DANGER, CLR_DANGER_DIS)
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self.delete_data)
        control_panel_layout.addWidget(self.delete_button, alignment=Qt.AlignVCenter)

        layout.addLayout(control_panel_layout)

        # --- Tartalom terület (info szöveg vagy táblázat) ---
        self.center_widget = QWidget()
        self.center_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.content_layout = QVBoxLayout()
        self.center_widget.setLayout(self.content_layout)

        # Tájékoztató szöveg — lekérdezés előtt látható (QSS "empty_label": szürke, középre igazított)
        self.info_label = QLabel(
            "Kattints a Lekérdezés gombra az IremsSzallito_stage tábla adatainak betöltéséhez"
        )
        self.info_label.setObjectName("empty_label")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(self.info_label)

        # Táblázat — lekérdezés után jelenik meg (kezdetben rejtett)
        # setSortingEnabled: az oszlopfejlécre kattintva rendezés
        self.table_view = QTableView()
        self.table_view.setSortingEnabled(True)
        self.table_view.hide()   # kezdetben láthatatlan
        self.content_layout.addWidget(self.table_view)

        layout.addWidget(self.center_widget)

        self.setLayout(layout)  # a QWidget-nek megadjuk a fő elrendezőt

        # Belső állapotváltozók
        self.progress_dialog = None  # az aktív progress dialógus referenciája (None = nincs)
        self._has_data = False       # True, ha van megjelenített adat (gombok aktívak)

        # Adatbázis kapcsolat
        self.db = DatabaseManager()
        # Lekérdezés gomb összekapcsolása a kezelőmetódussal
        self.query_button.clicked.connect(self.prepare_query)

    def _update_save_button_state(self):
        """Szinkronizálja a 'Mentés history-ba' gomb aktív/tiltott állapotát
        a _has_data flag értékével."""
        self.save_to_irems_hist_table_button.setEnabled(self._has_data)

    def prepare_query(self):
        """Lekérdezés gomb handler: megjeleníti a progress dialógust,
        majd 100ms késleltetéssel elindítja az adatbetöltést.

        A QTimer.singleShot() azért kell, hogy a progress dialógus valóban
        megjelenjen, mielőtt a DB hívás blokkolja a GUI szálat.
        Python/Qt egyszálú: a DB lekérdezés végrehajtása alatt az UI befagy,
        ha nem adjuk meg a rövid késleltetést a dialógus megjelenéséhez.
        """
        self.progress_dialog = DbOperationProgressDialog()
        self.progress_dialog.set_message("Adatok lekérdezése folyamatban...")
        self.progress_dialog.show()

        QTimer.singleShot(100, self.load_data)  # 100ms után hívja load_data()-t

    def load_data(self):
        """Lekérdezi az IremsSzallito_stage tábla adatait és megjeleníti a táblázatban."""
        try:
            # DB lekérdezés: visszaad egy pandas DataFrame-et
            df = self.db.query_vendor_data()
            if df.empty:
                # Üres tábla esetén tájékoztató szöveg, gombok tiltva maradnak
                self._has_data = False
                self.info_label.setText(
                    "Az IremsSzallito_stage tábla jelenleg üres, nincs megjeleníthető adat."
                )
                self._update_save_button_state()
                self.delete_button.setEnabled(False)
            else:
                # DataFrame → PandasModel → QTableView
                # A szállítói staging táblának 9 oszlopa van (Column1..Column9)
                model = PandasModel(df)
                self.table_view.setModel(model)
                # QHeaderView.Stretch: minden oszlop egyforma szélességű, kitölti a helyet
                self.table_view.horizontalHeader().setSectionResizeMode(
                    QHeaderView.Stretch
                )
                self.info_label.hide()    # szöveg elrejtése
                self.table_view.show()   # táblázat megjelenítése
                self._has_data = True
                self._update_save_button_state()   # mentés gomb aktiválása
                self.delete_button.setEnabled(True)  # törlés gomb aktiválása
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
                self.progress_dialog.accept()   # dialógus bezárása
                self.progress_dialog = None

    def delete_data(self):
        """Törlés gomb handler: megerősítő kérdés után törli az IremsSzallito_stage tartalmát."""
        confirm = QMessageBox.question(
            self,
            "Megerősítés",
            "Biztosan törölni szeretnéd a szállító adatokat?",
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
        success, message = self.db.delete_vendor_stage()

        if self.progress_dialog:
            self.progress_dialog.accept()
            self.progress_dialog = None

        if success:
            QMessageBox.information(self, "Sikeres törlés", message)
            # Táblázat elrejtése, tájékoztató szöveg visszaállítása
            self.table_view.hide()
            self.info_label.setText("A szállító adatok törölve lettek.")
            self.info_label.show()
            self._has_data = False
            self._update_save_button_state()   # mentés gomb letiltása
            self.delete_button.setEnabled(False)  # törlés gomb letiltása
        else:
            QMessageBox.critical(self, "Hiba", f"Törlés sikertelen:\n\n{message}")

    def save_to_irems_hist_table(self):
        """'Mentés history-ba' gomb handler: megerősítő kérdés után
        a tárolt eljárás hívásával az IremsSzallito_stage adatait Irems_Hist-be menti."""
        confirm = QMessageBox.question(
            self,
            "Megerősítés",
            "Biztosan menteni szeretnéd a szállító adatokat az Irems_Hist táblába?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if confirm == QMessageBox.Yes:
            self.progress_dialog = DbOperationProgressDialog()
            self.progress_dialog.set_message("Adatok mentése folyamatban...")
            self.progress_dialog.show()

            QTimer.singleShot(100, self.perform_save_to_irems_hist_table)

    def perform_save_to_irems_hist_table(self):
        """Elvégzi a tényleges history-ba mentést a tárolt eljárás hívásával.

        A dátumot a hist_date_edit widgetből olvassuk ki (alapértelmezetten mai nap).
        Az 'yyyy-MM-dd' formátum az SQL Server DATE típusának megfelelő.
        A tárolt eljárás (dbo.szallito_insert1) ezt @datum paraméterként kapja.
        """
        # Dátum kiolvasása a dátumválasztó widgetből (pl. "2025-03-25")
        date_str = self.hist_date_edit.date().toString("yyyy-MM-dd")
        success, message = self.db.call_vendor_insert1(date_str)

        if self.progress_dialog:
            self.progress_dialog.accept()
            self.progress_dialog = None

        if success:
            QMessageBox.information(self, "Sikeres mentés", message)
            # Táblázat elrejtése mentés után
            self.table_view.hide()
            self.info_label.setText("A szállító adatok mentve az Irems_Hist táblába.")
            self.info_label.show()
            self._has_data = False
            self._update_save_button_state()
            self.delete_button.setEnabled(False)
        else:
            QMessageBox.critical(self, "Hiba", f"Mentés sikertelen:\n\n{message}")
