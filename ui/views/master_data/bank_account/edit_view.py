# ui/views/master_data/bank_account/edit_view.py
#
# BankAccountEditView — Bankszámlaszámok beállítás nézet (CRUD).
#
# Adatbázis tábla: dbo.Bankszamlaszam_torzs
# Oszlopok: ID (auto), Bankszamlaszam, Bankszamlaszam_fokonyv,
#           Bankszamlaszam_deviza, Bankszamlaszam_tipus, Partner
#
# Műveletek:
#   C1: Lekérdezés gomb → DB lekérdezés → táblázat feltöltése + rekordszám label
#   C2a: Sorra kattintás (selectionChanged) → jobb panel feltöltése, mezők engedélyezése
#   C2b: Új sor gomb → üres jobb panel, mezők engedélyezése, Mentés aktiválása
#   C2c: Mentés gomb → INSERT (új sor) / UPDATE (meglévő sor) validációval
#   C2d: Törlés gomb → megerősítés → DELETE ID alapján → táblázat frissítése
#   C3:  Exportálás gomb → Excel fájl az exports/ mappába
#
# Fontos: a _df_full tartalmazza az ID oszlopot is (a megjelenített modellből el van rejtve).
# Az ID kell a DELETE és UPDATE műveletekhez.

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTableView,
    QHeaderView,
    QLineEdit,    # egysoros szövegbeviteli mező
    QComboBox,    # legördülő lista
    QFrame,       # keretezett konténer (jobb panel alapja)
    QSizePolicy,
    QMessageBox,
)
import os
import re                  # reguláris kifejezés (bankszámlaszám formátum validáláshoz)
from datetime import datetime  # exportált fájlnévhez időbélyeg

from PySide6.QtCore import Qt, QTimer
from models.pandas_model import PandasModel
from database.database import DatabaseManager
from ui.dialogs.db_operation_progress import DbOperationProgressDialog
from ui.icons import (
    ICON_SEARCH,
    ICON_PLUS,
    ICON_TRASH,
    ICON_SAVE,
    ICON_DOWNLOAD,
    set_button_icon,
    CLR_PRIMARY,
    CLR_PRIMARY_DIS,
    CLR_SECONDARY,
    CLR_SECONDARY_DIS,
    CLR_DANGER,
    CLR_DANGER_DIS,
)

# Az alkalmazás gyökérkönyvtárának meghatározása
# __file__ = ez a fájl abszolút útvonala
# "..", "..", "..", ".." = 4 szinttel feljebb (bank_account → master_data → views → ui → v2)
_APP_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..")
)

# DB oszlopnév → megjelenítési név leképezés (a táblázat fejléceihez és az exporthoz)
_COL_MAP = {
    "Bankszamlaszam": "Bankszámlaszám",
    "Bankszamlaszam_fokonyv": "Főkönyv",
    "Bankszamlaszam_deviza": "Deviza",
    "Bankszamlaszam_tipus": "Típus",
    "Partner": "Partner",
}


class BankAccountEditView(QWidget):
    """Bankszámlaszámok kezelő nézet.

    Bal oldal: a tábla tartalma QTableView-ban. Jobb oldal (320px-es panel):
    az aktuálisan szerkesztett sor mezői. A két panel között szinkron: sorra
    kattintáskor a jobb panel feltöltődik, szerkesztés után Mentéssel frissül a DB.
    """

    def __init__(self):
        super().__init__()
        self._selected_count = 0    # kijelölt sorok száma (a Törlés gomb feliratához)
        self._current_id = None     # szerkesztett sor ID-ja (None = új sor módban)
        self._is_new_row = False    # True: Új sor gomb megnyomva, INSERT kell
        self._df_full = None        # teljes DataFrame az ID oszloppal (kijelölés nyomon követéséhez)
        self._db = DatabaseManager()
        self._progress_dialog = None
        self._setup_ui()

    # ------------------------------------------------------------------ #
    #  UI felépítés                                                        #
    # ------------------------------------------------------------------ #

    def _setup_ui(self):
        """Az egész nézet UI-ját felépíti egyetlen metódusban."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 16, 0, 16)  # bal: 24px margó (sidebar után)
        main_layout.setSpacing(12)

        # --- Cím ---
        title = QLabel("Bankszámlaszámok")
        title.setObjectName("view_title")  # QSS: 18px félkövér
        main_layout.addWidget(title)

        # --- Eszközsáv ---
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.setContentsMargins(0, 0, 0, 0)

        # Lekérdezés gomb — balra a toolbarban
        self.query_button = QPushButton("Lekérdezés")
        set_button_icon(self.query_button, ICON_SEARCH, CLR_PRIMARY, CLR_PRIMARY_DIS)
        self.query_button.clicked.connect(self._prepare_query)
        toolbar.addWidget(self.query_button)

        toolbar.addStretch()  # rugalmas tér: bal gombok és jobb (detail panel fölötti) gombok között

        # Exportálás gomb — mindig aktív (a DB-ből kérdezi le az adatokat)
        self.export_button = QPushButton("Exportálás")
        self.export_button.setObjectName("secondary_button")
        set_button_icon(self.export_button, ICON_DOWNLOAD, CLR_SECONDARY, CLR_SECONDARY_DIS)
        self.export_button.clicked.connect(self._on_export)
        toolbar.addWidget(self.export_button)

        # CRUD gombsor — 320px-es fix szélességű widget, pontosan a detail panel fölött igazodik
        crud_widget = QWidget()
        crud_widget.setFixedWidth(320)
        crud_layout = QHBoxLayout(crud_widget)
        crud_layout.setContentsMargins(16, 0, 16, 0)
        crud_layout.setSpacing(6)

        # Új sor gomb — csak lekérdezés után aktív (add_row_button.setEnabled(True) a _load_data-ban)
        self.add_row_button = QPushButton("Új sor")
        self.add_row_button.setObjectName("secondary_button")
        set_button_icon(self.add_row_button, ICON_PLUS, CLR_SECONDARY, CLR_SECONDARY_DIS)
        self.add_row_button.setEnabled(False)  # alapból tiltott
        self.add_row_button.clicked.connect(self._on_add_row)
        crud_layout.addWidget(self.add_row_button)

        # Törlés gomb — csak ha van kijelölt sor (_update_toolbar_state aktiválja)
        self.delete_button = QPushButton("Törlés")
        self.delete_button.setObjectName("delete_button")
        set_button_icon(self.delete_button, ICON_TRASH, CLR_DANGER, CLR_DANGER_DIS)
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self._on_delete)
        crud_layout.addWidget(self.delete_button)

        # Mentés gomb — soron kattintáskor vagy Új sor módban aktiválódik
        self.save_button = QPushButton("Mentés")
        set_button_icon(self.save_button, ICON_SAVE, CLR_PRIMARY, CLR_PRIMARY_DIS)
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._on_save)
        crud_layout.addWidget(self.save_button)

        crud_layout.addStretch()
        toolbar.addWidget(crud_widget)

        main_layout.addLayout(toolbar)

        # --- Tartalom: táblázat (bal, rugalmas) + részlet panel (jobb, fix 320px) ---
        content_layout = QHBoxLayout()
        content_layout.setSpacing(0)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # Bal terület: info szöveg (lekérdezés előtt) + táblázat (lekérdezés után)
        table_area = QWidget()
        table_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table_area_layout = QVBoxLayout(table_area)
        table_area_layout.setContentsMargins(0, 0, 0, 0)
        table_area_layout.setSpacing(0)

        self.info_label = QLabel(
            "Kattints a Lekérdezés gombra a bankszámlaszámok betöltéséhez"
        )
        self.info_label.setObjectName("empty_label")
        self.info_label.setAlignment(Qt.AlignCenter)
        table_area_layout.addWidget(self.info_label)

        # QTableView konfigurálás:
        # - setSortingEnabled: fejlécre kattintva rendezés
        # - setAlternatingRowColors: váltakozó sor színek (QSS alapján)
        # - SelectRows: teljes sor kijelölés (nem csak cella)
        # - setStretchLastSection: utolsó oszlop kitölti a maradék helyet
        # - verticalHeader().setVisible(False): sorszámok elrejtése
        self.table_view = QTableView()
        self.table_view.setSortingEnabled(True)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSelectionBehavior(QTableView.SelectRows)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table_view.hide()
        table_area_layout.addWidget(self.table_view)

        # Rekordszám label — táblázat alatt, szürke kis betűkkel
        self.record_count_label = QLabel("")
        self.record_count_label.setObjectName("record_count_label")
        self.record_count_label.setStyleSheet("font-size: 12px; color: #868e96; padding: 4px 0 0 2px;")
        table_area_layout.addWidget(self.record_count_label)

        content_layout.addWidget(table_area, 1)  # stretch=1: rugalmas méretezés

        # Jobb panel: szerkesztő mezők (fix 320px)
        # QFrame#detail_panel: ObjectName alapú QSS szelektorral fehér háttér
        # (típus-szelektort nem használunk, mert a leszármazott QFrame-eket is érintené)
        detail_panel = QFrame()
        detail_panel.setObjectName("detail_panel")
        detail_panel.setFixedWidth(320)
        detail_panel.setStyleSheet("QFrame#detail_panel { background: white; }")
        detail_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(16, 16, 16, 16)
        detail_layout.setSpacing(10)

        # Bankszámlaszám mező — regex validálás a Mentés előtt (DDDDDDDD-DDDDDDDD formátum)
        detail_layout.addWidget(self._make_field_label("Bankszámlaszám"))
        self.ba_number_edit = QLineEdit()
        self.ba_number_edit.setEnabled(False)  # alapból tiltott (C2a/C2b aktiválja)
        detail_layout.addWidget(self.ba_number_edit)

        # Főkönyvi szám mező
        detail_layout.addWidget(self._make_field_label("Főkönyv"))
        self.ba_ledger_edit = QLineEdit()
        self.ba_ledger_edit.setEnabled(False)
        detail_layout.addWidget(self.ba_ledger_edit)

        # Deviza legördülő (HUF/EUR/USD)
        detail_layout.addWidget(self._make_field_label("Deviza"))
        self.ba_currency_combo = QComboBox()
        self.ba_currency_combo.addItems(["HUF", "EUR", "USD"])
        self.ba_currency_combo.setEnabled(False)
        detail_layout.addWidget(self.ba_currency_combo)

        # Típus mező (pl. "folyószámla", "megtakarítási" stb.)
        detail_layout.addWidget(self._make_field_label("Típus"))
        self.ba_type_edit = QLineEdit()
        self.ba_type_edit.setEnabled(False)
        detail_layout.addWidget(self.ba_type_edit)

        # Partner legördülő (SPP = Shopper Park Plus, SRP = Shopper Retail Park)
        detail_layout.addWidget(self._make_field_label("Partner"))
        self.ba_partner_combo = QComboBox()
        self.ba_partner_combo.addItems(["SPP", "SRP"])
        self.ba_partner_combo.setEnabled(False)
        detail_layout.addWidget(self.ba_partner_combo)

        detail_layout.addStretch()  # a mezők felfelé tolódnak, alul üres tér marad

        content_layout.addWidget(detail_panel)

        main_layout.addLayout(content_layout, 1)  # stretch=1: tartalom kitölti a maradék teret

    # ------------------------------------------------------------------ #
    #  Lekérdezés (C1)                                                    #
    # ------------------------------------------------------------------ #

    def _prepare_query(self):
        """Progress dialógus megjelenítése, majd 100ms késleltetéssel lekérdezés."""
        self._progress_dialog = DbOperationProgressDialog()
        self._progress_dialog.set_message("Adatok lekérdezése folyamatban...")
        self._progress_dialog.show()
        QTimer.singleShot(100, self._load_data)

    def _load_data(self):
        """Lekérdezi a Bankszamlaszam_torzs táblát és megjeleníti a táblázatban.

        _df_full: az ID oszlopot is tartalmazó teljes DataFrame — ezt tároljuk
        el, hogy a DELETE/UPDATE műveleteknél ki tudjuk nyerni az ID-t.
        A táblázatban az ID nem jelenik meg (df_display = df.drop("ID")).
        """
        try:
            df = self._db.query_bank_account_numbers()
            self._df_full = df.copy()  # ID megtartva a CRUD műveletekhez

            # Megjelenítési DataFrame: ID eldobva, oszlopnevek magyarra fordítva
            df_display = df.drop(columns=["ID"], errors="ignore").rename(
                columns=_COL_MAP
            )

            model = PandasModel(df_display)
            self.table_view.setModel(model)
            self.table_view.clearSelection()
            # selectionChanged signal: sorra kattintáskor hívja _on_selection_changed-t
            self.table_view.selectionModel().selectionChanged.connect(
                self._on_selection_changed
            )
            self.info_label.hide()
            self.table_view.show()

            self.record_count_label.setText(f"{len(df_display)} rekord")
            self.add_row_button.setEnabled(True)  # Új sor gomb aktiválása
            self._selected_count = 0
            self._reset_detail_panel()
            self._update_toolbar_state()
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
    #  Kijelölés kezelése (C2a)                                           #
    # ------------------------------------------------------------------ #

    def _on_selection_changed(self, selected, deselected):
        """Sorra kattintáskor frissíti a jobb panel mezőit a kijelölt sor adataival.

        Ha pontosan 1 sor van kijelölve: jobb panel feltöltése + engedélyezése.
        Ha 0 vagy több sor van kijelölve: jobb panel ürítése + letiltása.
        """
        indexes = self.table_view.selectionModel().selectedRows()
        self._selected_count = len(indexes)
        self._update_toolbar_state()  # Törlés gomb felirat frissítése (pl. "Törlés (2)")

        if len(indexes) == 1:
            row = indexes[0].row()
            self._is_new_row = False
            # ID kinyerése a _df_full-ból (a megjelenített modellben nincs ID oszlop)
            if self._df_full is not None:
                self._current_id = int(self._df_full.iloc[row]["ID"])

            # Mezőértékek kiolvasása a modellből (fejléc alapján pozíció szerinti keresés)
            model = self.table_view.model()
            headers = [
                model.headerData(col, Qt.Horizontal)
                for col in range(model.columnCount())
            ]

            def get_val(col_name):
                """Segédfüggvény: oszlopnév alapján visszaadja a cella értékét."""
                if col_name in headers:
                    col = headers.index(col_name)
                    val = model.data(model.index(row, col))
                    return str(val) if val is not None else ""
                return ""

            # Jobb panel mezőinek feltöltése
            self.ba_number_edit.setText(get_val("Bankszámlaszám"))
            self.ba_ledger_edit.setText(get_val("Főkönyv"))

            # Deviza combo: a meglévő érték pozíciójának megkeresése
            deviza = get_val("Deviza")
            idx = self.ba_currency_combo.findText(deviza)
            self.ba_currency_combo.setCurrentIndex(idx if idx >= 0 else 0)

            self.ba_type_edit.setText(get_val("Típus"))

            # Partner combo: hasonlóan
            partner = get_val("Partner")
            idx = self.ba_partner_combo.findText(partner)
            self.ba_partner_combo.setCurrentIndex(idx if idx >= 0 else 0)

            self._enable_detail_panel(True)   # mezők szerkeszthetővé tétele
            self.save_button.setEnabled(True) # Mentés gomb aktiválása
        else:
            self._reset_detail_panel()  # több/nulla kijelölt sor: panel törlése

    def _reset_detail_panel(self):
        """Jobb panel törlése és letiltása.

        A _selected_count-ot NEM módosítja — azt kizárólag _on_selection_changed kezeli.
        """
        self._current_id = None
        self._is_new_row = False
        self.ba_number_edit.clear()
        self.ba_ledger_edit.clear()
        self.ba_currency_combo.setCurrentIndex(0)
        self.ba_type_edit.clear()
        self.ba_partner_combo.setCurrentIndex(0)
        self._enable_detail_panel(False)
        self.save_button.setEnabled(False)

    def _enable_detail_panel(self, enabled: bool):
        """Egyszerre engedélyezi vagy tiltja a jobb panel összes beviteli mezőjét."""
        self.ba_number_edit.setEnabled(enabled)
        self.ba_ledger_edit.setEnabled(enabled)
        self.ba_currency_combo.setEnabled(enabled)
        self.ba_type_edit.setEnabled(enabled)
        self.ba_partner_combo.setEnabled(enabled)

    # ------------------------------------------------------------------ #
    #  Új sor (C2b)                                                       #
    # ------------------------------------------------------------------ #

    def _on_add_row(self):
        """Új sor mód aktiválása: jobb panel ürítése, mezők engedélyezése.

        A táblázat kijelölés törlésre kerül, hogy egyértelmű legyen:
        a felhasználó most nem szerkeszt, hanem új adatot visz be.
        """
        self.table_view.clearSelection()
        self._is_new_row = True
        self._current_id = None
        self.ba_number_edit.clear()
        self.ba_ledger_edit.clear()
        self.ba_currency_combo.setCurrentIndex(0)
        self.ba_type_edit.clear()
        self.ba_partner_combo.setCurrentIndex(0)
        self._enable_detail_panel(True)
        self.save_button.setEnabled(True)
        self.ba_number_edit.setFocus()  # fókusz a bankszámlaszám mezőre

    # ------------------------------------------------------------------ #
    #  Mentés (C2c)                                                       #
    # ------------------------------------------------------------------ #

    def _on_save(self):
        """Mentés gomb handler: validálás, megerősítés, majd INSERT vagy UPDATE.

        Validáció:
          1. Bankszámlaszám mező nem lehet üres
          2. Bankszámlaszám formátum: DDDDDDDD-DDDDDDDD vagy DDDDDDDD-DDDDDDDD-DDDDDDDD
          3. Duplikáció ellenőrzés a betöltött adatok alapján (UPDATE esetén saját sor kizárva)
          4. Főkönyv mező nem lehet üres
        """
        number = self.ba_number_edit.text().strip()
        ledger = self.ba_ledger_edit.text().strip()
        deviza = self.ba_currency_combo.currentText()
        tipus = self.ba_type_edit.text().strip()
        partner = self.ba_partner_combo.currentText()

        errors = []

        if not number:
            errors.append("• A Bankszámlaszám mező nem lehet üres.")
        elif not re.fullmatch(r"\d{8}-\d{8}(-\d{8})?", number):
            # Regex: 8 jegy - 8 jegy (opcionálisan - 8 jegy)
            errors.append(
                "• A Bankszámlaszám formátuma érvénytelen.\n"
                "  Elfogadott formátum: DDDDDDDD-DDDDDDDD vagy DDDDDDDD-DDDDDDDD-DDDDDDDD"
            )
        else:
            # Duplikáció ellenőrzés: van-e már ilyen bankszámlaszám a listában?
            if self._df_full is not None:
                existing = self._df_full[
                    self._df_full["Bankszamlaszam"].astype(str) == number
                ]
                # UPDATE esetén a saját sorát kizárjuk
                if not self._is_new_row and self._current_id is not None:
                    existing = existing[existing["ID"] != self._current_id]
                if not existing.empty:
                    errors.append(
                        f'• A(z) "{number}" bankszamlaszam mar szerepel a listaban.'
                    )

        if not ledger:
            errors.append("• A Főkönyv mező nem lehet üres.")

        if errors:
            QMessageBox.warning(self, "Érvénytelen adatok", "\n".join(errors))
            # Fókusz az első hibás mezőre
            if not number or (
                number and not re.fullmatch(r"\d{8}-\d{8}(-\d{8})?", number)
            ):
                self.ba_number_edit.setFocus()
            elif not ledger:
                self.ba_ledger_edit.setFocus()
            return

        # Megerősítő dialógus
        confirm_msg = (
            "Biztosan hozzáadod az új bankszámlaszámot?"
            if self._is_new_row
            else "Biztosan mented a módosításokat?"
        )
        reply = QMessageBox.question(
            self,
            "Megerősítés",
            confirm_msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,  # alapértelmezett válasz: Nem (biztonságosabb)
        )
        if reply != QMessageBox.Yes:
            return

        # Adatbázis művelet: INSERT (új sor) vagy UPDATE (meglévő)
        if self._is_new_row:
            ok, msg = self._db.insert_bank_account(
                number, ledger, deviza, tipus, partner
            )
        else:
            ok, msg = self._db.update_bank_account(
                self._current_id, number, ledger, deviza, tipus, partner
            )

        if ok:
            QMessageBox.information(self, "Mentés sikeres", msg)
            self._prepare_query()  # táblázat újratöltése + panel és toolbar reset
        else:
            QMessageBox.critical(
                self,
                "Mentési hiba",
                f"Sikertelen mentés.\n\nRészletek:\n{msg}",
            )

    # ------------------------------------------------------------------ #
    #  Törlés (C2d)                                                       #
    # ------------------------------------------------------------------ #

    def _on_delete(self):
        """Törlés gomb handler: megerősítés, majd DELETE az összes kijelölt sorhoz.

        Több sor is kijelölhető (SelectRows mód) — mindegyiket egyenként törli.
        Hiba esetén összesített hibaüzenet jelenik meg.
        """
        indexes = self.table_view.selectionModel().selectedRows()
        if not indexes:
            return

        count = len(indexes)
        confirm_msg = (
            f"Biztosan törlöd a kijelölt {count} sort?"
            if count > 1
            else "Biztosan törlöd a kijelölt sort?"
        )
        reply = QMessageBox.question(
            self,
            "Törlés megerősítése",
            confirm_msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # ID-k kinyerése a _df_full-ból (a modell nem tartalmazza az ID-t)
        ids_to_delete = []
        if self._df_full is not None:
            for idx in indexes:
                ids_to_delete.append(int(self._df_full.iloc[idx.row()]["ID"]))

        errors = []
        for id_ in ids_to_delete:
            ok, err_msg = self._db.delete_bank_account(id_)
            if not ok:
                errors.append(err_msg)

        if errors:
            QMessageBox.critical(
                self,
                "Törlési hiba",
                "Egy vagy több sor törlése sikertelen:\n\n" + "\n".join(errors),
            )
        else:
            self._prepare_query()  # táblázat frissítése

    # ------------------------------------------------------------------ #
    #  Export (C3)                                                        #
    # ------------------------------------------------------------------ #

    def _on_export(self):
        """Progress dialógus, majd 100ms késleltetéssel az Excel export futtatása."""
        self._progress_dialog = DbOperationProgressDialog()
        self._progress_dialog.set_message("Exportálás folyamatban...")
        self._progress_dialog.show()
        QTimer.singleShot(100, self._run_export)

    def _run_export(self):
        """Lekérdezi és Excel fájlba menti a bankszámlaszámokat az exports/ mappába.

        A fájlnév időbélyeget tartalmaz (pl. bankszamlaszamok_2025-03-25_143012.xlsx).
        Az exports/ mappa automatikusan létrejön, ha nem létezik (os.makedirs exist_ok=True).
        """
        try:
            df = self._db.query_bank_account_numbers()
            df_export = df.rename(columns={"ID": "ID", **_COL_MAP})
            exports_dir = os.path.join(_APP_ROOT, "exports")
            os.makedirs(exports_dir, exist_ok=True)
            filename = f"bankszamlaszamok_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.xlsx"
            filepath = os.path.join(exports_dir, filename)
            df_export.to_excel(filepath, index=False)
            if self._progress_dialog:
                self._progress_dialog.accept()
                self._progress_dialog = None
            QMessageBox.information(
                self, "Exportálás sikeres", f"Fájl mentve:\nexports/{filename}"
            )
        except Exception as e:
            if self._progress_dialog:
                self._progress_dialog.accept()
                self._progress_dialog = None
            QMessageBox.critical(
                self, "Exportálási hiba", f"Sikertelen exportálás.\n\nRészletek:\n{e}"
            )

    # ------------------------------------------------------------------ #
    #  Segédek                                                             #
    # ------------------------------------------------------------------ #

    def _make_field_label(self, text: str) -> QLabel:
        """Egységes stílusú mező-felirat label létrehozása a jobb panelhez."""
        label = QLabel(text)
        label.setStyleSheet("font-size: 12px; color: #495057; background: transparent;")
        return label

    def _update_toolbar_state(self):
        """Törlés gomb feliratának és állapotának frissítése a kijelölt sorok száma alapján.

        Ha 0 sor kijelölve: "Törlés" felirat, tiltott állapot
        Ha N>0 sor kijelölve: "Törlés (N)" felirat, aktív állapot
        """
        n = self._selected_count
        self.delete_button.setText(f"  Törlés ({n})" if n > 0 else "  Törlés")
        self.delete_button.setEnabled(n > 0)
