# ui/views/master_data/partner/edit_view.py
#
# PartnerEditView — Partnerek beállítás nézet (CRUD + UMS szinkron + export).
#
# Adatbázis tábla: dbo.Partner_mapping
# Oszlopok: ID (auto), UMS_parnter (typo az adatbázisban!), Combosoft_partner
#
# A BankAccountEditView-val azonos szerkezetű, de plusz funkciókkal:
#   - UMS szinkron gomb: a Bank_lek1 nézetből beolvassa az ismeretlen partnerneveket
#     a Partner_mapping táblába (dbo.partnerInsert tárolt eljárás)
#   - Hiányzó Combosoft export: csak azokat a sorokat exportálja, ahol
#     a Combosoft_partner oszlop üres (segédfunkció az adatkitöltéshez)
#
# Műveletek:
#   C1: Lekérdezés → DB lekérdezés → táblázat + rekordszám
#   C2i: Sorra kattintás → jobb panel feltöltése
#   C2j: Új sor gomb → INSERT mód
#   C2k: Mentés → INSERT / UPDATE
#   C2l: Törlés → DELETE ID alapján
#   C3:  Exportálás → teljes lista Excel-be
#   UMS szinkron: dbo.partnerInsert tárolt eljárás hívása

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
import os
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from models.pandas_model import PandasModel
from database.database import DatabaseManager
from ui.dialogs.db_operation_progress import DbOperationProgressDialog
from ui.icons import (
    ICON_SEARCH,
    ICON_PLUS,
    ICON_UPLOAD,    # felfelé nyíl ikon (UMS szinkron gombhoz)
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

# Alkalmazás gyökérkönyvtár (4 szinttel feljebb)
_APP_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..")
)

# DB oszlopnév → megjelenítési név (megjegyzés: "UMS_parnter" typo az adatbázisban)
_COL_MAP = {
    "UMS_parnter": "UMS partner",
    "Combosoft_partner": "Combosoft partner",
}


class PartnerEditView(QWidget):
    """Partnerek kezelő nézet.

    UMS partner: a banki UMS fájlban szereplő partvernév (Column30 normalizálva).
    Combosoft partner: az Irems/Combosoft rendszerben használt párosítandó név.
    Az UMS szinkron automatikusan beolvassa az ismeretlen UMS partnerneveket.
    """

    def __init__(self):
        super().__init__()
        self._selected_count = 0
        self._current_id = None
        self._is_new_row = False
        self._df_full = None
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

        # Cím
        title = QLabel("Partnerek")
        title.setObjectName("view_title")
        main_layout.addWidget(title)

        # Eszközsáv
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.setContentsMargins(0, 0, 0, 0)

        # Lekérdezés gomb
        self.query_button = QPushButton("Lekérdezés")
        set_button_icon(self.query_button, ICON_SEARCH, CLR_PRIMARY, CLR_PRIMARY_DIS)
        self.query_button.clicked.connect(self._prepare_query)
        toolbar.addWidget(self.query_button)

        # UMS szinkron gomb — mindig aktív (nem függ a lekérdezéstől)
        # Meghívja a dbo.partnerInsert tárolt eljárást, amely a Bank_lek1 nézetből
        # beolvassa az ismeretlen partnerneveket a Partner_mapping táblába
        self.sync_button = QPushButton("UMS szinkron")
        self.sync_button.setObjectName("secondary_button")
        set_button_icon(self.sync_button, ICON_UPLOAD, CLR_SECONDARY, CLR_SECONDARY_DIS)
        self.sync_button.clicked.connect(self._on_ums_sync)
        toolbar.addWidget(self.sync_button)

        toolbar.addStretch()

        # Hiányzó Combosoft export gomb — csak azokat exportálja, ahol Combosoft üres
        # Segédfunkció: az adatrögzítőnek megmutatja, melyik UMS partnerhez kell
        # még megadni a Combosoft párját
        self.export_missing_button = QPushButton("Hiányzó Combosoft")
        self.export_missing_button.setObjectName("secondary_button")
        set_button_icon(self.export_missing_button, ICON_DOWNLOAD, CLR_SECONDARY, CLR_SECONDARY_DIS)
        self.export_missing_button.clicked.connect(self._on_export_missing_combosoft)
        toolbar.addWidget(self.export_missing_button)

        # Teljes lista exportálás
        self.export_button = QPushButton("Exportálás")
        self.export_button.setObjectName("secondary_button")
        set_button_icon(self.export_button, ICON_DOWNLOAD, CLR_SECONDARY, CLR_SECONDARY_DIS)
        self.export_button.clicked.connect(self._on_export)
        toolbar.addWidget(self.export_button)

        # CRUD gombsor (fix 320px, detail panel fölött)
        crud_widget = QWidget()
        crud_widget.setFixedWidth(320)
        crud_layout = QHBoxLayout(crud_widget)
        crud_layout.setContentsMargins(16, 0, 16, 0)
        crud_layout.setSpacing(6)

        self.add_row_button = QPushButton("Új sor")
        self.add_row_button.setObjectName("secondary_button")
        set_button_icon(self.add_row_button, ICON_PLUS, CLR_SECONDARY, CLR_SECONDARY_DIS)
        self.add_row_button.setEnabled(False)
        self.add_row_button.clicked.connect(self._on_add_row)
        crud_layout.addWidget(self.add_row_button)

        self.delete_button = QPushButton("Törlés")
        self.delete_button.setObjectName("delete_button")
        set_button_icon(self.delete_button, ICON_TRASH, CLR_DANGER, CLR_DANGER_DIS)
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self._on_delete)
        crud_layout.addWidget(self.delete_button)

        self.save_button = QPushButton("Mentés")
        set_button_icon(self.save_button, ICON_SAVE, CLR_PRIMARY, CLR_PRIMARY_DIS)
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._on_save)
        crud_layout.addWidget(self.save_button)

        crud_layout.addStretch()
        toolbar.addWidget(crud_widget)

        main_layout.addLayout(toolbar)

        # Tartalom: táblázat + jobb panel
        content_layout = QHBoxLayout()
        content_layout.setSpacing(0)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # Bal: info label + táblázat + rekordszám
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
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table_view.hide()
        table_area_layout.addWidget(self.table_view)

        self.record_count_label = QLabel("")
        self.record_count_label.setObjectName("record_count_label")
        self.record_count_label.setStyleSheet("font-size: 12px; color: #868e96; padding: 4px 0 0 2px;")
        table_area_layout.addWidget(self.record_count_label)

        content_layout.addWidget(table_area, 1)

        # Jobb panel (fix 320px, fehér háttér)
        detail_panel = QFrame()
        detail_panel.setObjectName("detail_panel")
        detail_panel.setFixedWidth(320)
        detail_panel.setStyleSheet("QFrame#detail_panel { background: white; }")
        detail_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(16, 16, 16, 16)
        detail_layout.setSpacing(10)

        # UMS partner mező — kötelező (ha üres, a Mentés nem engedélyezett)
        detail_layout.addWidget(self._make_field_label("UMS partner"))
        self.ums_partner_edit = QLineEdit()
        self.ums_partner_edit.setEnabled(False)
        detail_layout.addWidget(self.ums_partner_edit)

        # Combosoft partner mező — opcionális (üres is lehet)
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
        """Lekérdezi a Partner_mapping táblát és megjeleníti."""
        try:
            df = self._db.query_partner_mapping()
            self._df_full = df.copy()

            df_display = df.drop(columns=["ID"], errors="ignore").rename(columns=_COL_MAP)

            model = PandasModel(df_display)
            self.table_view.setModel(model)
            self.table_view.clearSelection()
            self.table_view.selectionModel().selectionChanged.connect(
                self._on_selection_changed
            )
            self.info_label.hide()
            self.table_view.show()

            self.record_count_label.setText(f"{len(df_display)} rekord")
            self.add_row_button.setEnabled(True)
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
    #  Kijelölés kezelése (C2i)                                           #
    # ------------------------------------------------------------------ #

    def _on_selection_changed(self, selected, deselected):
        """Sorra kattintáskor feltölti a jobb panel mezőit."""
        indexes = self.table_view.selectionModel().selectedRows()
        self._selected_count = len(indexes)
        self._update_toolbar_state()

        if len(indexes) == 1:
            row = indexes[0].row()
            self._is_new_row = False
            if self._df_full is not None:
                self._current_id = int(self._df_full.iloc[row]["ID"])

            model = self.table_view.model()
            headers = [
                model.headerData(col, Qt.Horizontal)
                for col in range(model.columnCount())
            ]

            def get_val(col_name):
                if col_name in headers:
                    col = headers.index(col_name)
                    val = model.data(model.index(row, col))
                    return str(val) if val is not None else ""
                return ""

            self.ums_partner_edit.setText(get_val("UMS partner"))
            self.combosoft_partner_edit.setText(get_val("Combosoft partner"))
            self._enable_detail_panel(True)
            self.save_button.setEnabled(True)
        else:
            self._reset_detail_panel()

    def _reset_detail_panel(self):
        """Jobb panel törlése + mezők letiltása. A _selected_count-ot NEM érinti."""
        self._current_id = None
        self._is_new_row = False
        self.ums_partner_edit.clear()
        self.combosoft_partner_edit.clear()
        self._enable_detail_panel(False)
        self.save_button.setEnabled(False)

    def _enable_detail_panel(self, enabled: bool):
        self.ums_partner_edit.setEnabled(enabled)
        self.combosoft_partner_edit.setEnabled(enabled)

    # ------------------------------------------------------------------ #
    #  Új sor (C2j)                                                       #
    # ------------------------------------------------------------------ #

    def _on_add_row(self):
        self.table_view.clearSelection()
        self._is_new_row = True
        self._current_id = None
        self.ums_partner_edit.clear()
        self.combosoft_partner_edit.clear()
        self._enable_detail_panel(True)
        self.save_button.setEnabled(True)
        self.ums_partner_edit.setFocus()

    # ------------------------------------------------------------------ #
    #  Mentés (C2k)                                                       #
    # ------------------------------------------------------------------ #

    def _on_save(self):
        """Mentés gomb handler: validálás (csak UMS partner kötelező), majd DB művelet."""
        ums = self.ums_partner_edit.text().strip()
        combosoft = self.combosoft_partner_edit.text().strip()

        # Csak az UMS partner kötelező — Combosoft üres is lehet
        if not ums:
            QMessageBox.warning(
                self,
                "Érvénytelen adatok",
                "• Az UMS partner mező nem lehet üres.",
            )
            self.ums_partner_edit.setFocus()
            return

        confirm_msg = (
            "Biztosan hozzáadod az új partnert?"
            if self._is_new_row
            else "Biztosan mented a módosításokat?"
        )
        reply = QMessageBox.question(
            self,
            "Megerősítés",
            confirm_msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        if self._is_new_row:
            ok, msg = self._db.insert_partner(ums, combosoft)
        else:
            ok, msg = self._db.update_partner(self._current_id, ums, combosoft)

        if ok:
            QMessageBox.information(self, "Mentés sikeres", msg)
            self._prepare_query()
        else:
            QMessageBox.critical(
                self,
                "Mentési hiba",
                f"Sikertelen mentés.\n\nRészletek:\n{msg}",
            )

    # ------------------------------------------------------------------ #
    #  Törlés (C2l)                                                       #
    # ------------------------------------------------------------------ #

    def _on_delete(self):
        """Törlés gomb handler: megerősítés, majd DELETE a kijelölt sorokhoz."""
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

        ids_to_delete = []
        if self._df_full is not None:
            for idx in indexes:
                ids_to_delete.append(int(self._df_full.iloc[idx.row()]["ID"]))

        errors = []
        for id_ in ids_to_delete:
            ok, err_msg = self._db.delete_partner(id_)
            if not ok:
                errors.append(err_msg)

        if errors:
            QMessageBox.critical(
                self,
                "Törlési hiba",
                "Egy vagy több sor törlése sikertelen:\n\n" + "\n".join(errors),
            )
        else:
            self._prepare_query()

    # ------------------------------------------------------------------ #
    #  UMS szinkronizálás                                                 #
    # ------------------------------------------------------------------ #

    def _on_ums_sync(self):
        """UMS szinkron gomb handler: megerősítés, majd tárolt eljárás hívása.

        A dbo.partnerInsert eljárás a Bank_lek1 nézetből (amely az importált
        UMS adatokat tartalmazza) beolvassa az ismeretlen partnerneveket.
        Csak azokat a sorokat adja hozzá, amelyek még nem szerepelnek
        a Partner_mapping táblában.
        """
        reply = QMessageBox.question(
            self,
            "UMS szinkronizálás",
            "Az UMS partner lista szinkronizálása beolvassa a Bank lekérdezésből\n"
            "azokat a partnerneveket, amelyek még nem szerepelnek a listában.\n\n"
            "Folytatod?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self._progress_dialog = DbOperationProgressDialog()
        self._progress_dialog.set_message("UMS szinkronizálás folyamatban...")
        self._progress_dialog.show()
        QTimer.singleShot(100, self._run_ums_sync)

    def _run_ums_sync(self):
        """Elvégzi az UMS szinkronizálást: dbo.partnerInsert tárolt eljárás hívása."""
        try:
            ok, result = self._db.call_partner_insert()
            if self._progress_dialog:
                self._progress_dialog.accept()
                self._progress_dialog = None
            if ok:
                QMessageBox.information(self, "Szinkronizálás sikeres", result)
                self._prepare_query()  # táblázat frissítése az új sorokkal
            else:
                QMessageBox.critical(
                    self,
                    "Szinkronizálási hiba",
                    f"Sikertelen szinkronizálás.\n\nRészletek:\n{result}",
                )
        except Exception as e:
            if self._progress_dialog:
                self._progress_dialog.accept()
                self._progress_dialog = None
            QMessageBox.critical(
                self, "Szinkronizálási hiba", f"Sikertelen szinkronizálás.\n\nRészletek:\n{e}"
            )

    # ------------------------------------------------------------------ #
    #  Export (C3)                                                        #
    # ------------------------------------------------------------------ #

    def _on_export(self):
        """Teljes partner lista Excel exportja."""
        self._progress_dialog = DbOperationProgressDialog()
        self._progress_dialog.set_message("Exportálás folyamatban...")
        self._progress_dialog.show()
        QTimer.singleShot(100, self._run_export)

    def _run_export(self):
        """Lekérdezi és Excel fájlba menti a partner mappinget."""
        try:
            df = self._db.query_partner_mapping()
            df_export = df.rename(columns={"ID": "ID", **_COL_MAP})
            exports_dir = os.path.join(_APP_ROOT, "exports")
            os.makedirs(exports_dir, exist_ok=True)
            filename = f"partnerek_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.xlsx"
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

    def _on_export_missing_combosoft(self):
        """Hiányzó Combosoft partner export indítása."""
        self._progress_dialog = DbOperationProgressDialog()
        self._progress_dialog.set_message("Exportálás folyamatban...")
        self._progress_dialog.show()
        QTimer.singleShot(100, self._run_export_missing)

    def _run_export_missing(self):
        """Csak azokat a sorokat exportálja, ahol a Combosoft_partner mező üres.

        Segédfunkció: az adatrögzítőnek megmutatja, melyik UMS partnerhez
        kell még megadni a Combosoft párosítást.
        Ha minden sornál ki van töltve, tájékoztató üzenet jelenik meg.
        """
        try:
            df = self._db.query_partner_mapping()
            # Üres vagy NaN Combosoft_partner értékű sorok kiszűrése
            missing = df[
                df["Combosoft_partner"].isna()
                | (df["Combosoft_partner"].astype(str).str.strip() == "")
            ]
            if self._progress_dialog:
                self._progress_dialog.accept()
                self._progress_dialog = None
            if missing.empty:
                QMessageBox.information(
                    self,
                    "Nincs hiányzó adat",
                    "Minden sorhoz van Combosoft partner megadva.",
                )
                return

            df_export = missing.rename(columns={"ID": "ID", **_COL_MAP})
            exports_dir = os.path.join(_APP_ROOT, "exports")
            os.makedirs(exports_dir, exist_ok=True)
            filename = f"partnerek_ures_combosoft_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.xlsx"
            filepath = os.path.join(exports_dir, filename)
            df_export.to_excel(filepath, index=False)
            QMessageBox.information(
                self,
                "Exportálás sikeres",
                f"{len(df_export)} sor exportálva.\nFájl mentve:\nexports/{filename}",
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
        """Egységes stílusú mező-felirat label."""
        label = QLabel(text)
        label.setStyleSheet("font-size: 12px; color: #495057; background: transparent;")
        return label

    def _update_toolbar_state(self):
        """Törlés gomb felirat és állapot frissítése."""
        n = self._selected_count
        self.delete_button.setText(f"  Törlés ({n})" if n > 0 else "  Törlés")
        self.delete_button.setEnabled(n > 0)
