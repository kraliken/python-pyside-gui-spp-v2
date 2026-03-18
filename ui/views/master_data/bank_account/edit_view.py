# ui/views/master_data/bank_account/edit_view.py
#
# Bankszámlaszámok beállítás nézet.
# C1: Lekérdezés gomb → DB lekérdezés → táblázat feltöltése + rekordszám label.
# C2a: selectionChanged signal → jobb panel feltöltése + mezők engedélyezése.
# C2b: Új sor gomb → üres jobb panel, mezők engedélyezése, Mentés aktiválása.
# C2c: Mentés gomb → INSERT (új sor) / UPDATE (meglévő sor) DB-be.
# C2d: Törlés gomb → megerősítés dialog → DELETE ID alapján → táblázat frissítése.
# DB tábla: dbo.Bankszamlaszam_torzs

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTableView,
    QHeaderView,
    QLineEdit,
    QComboBox,
    QFrame,
    QSizePolicy,
    QMessageBox,
)
import os
import re
from datetime import datetime

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

_APP_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..")
)

# DB oszlop → megjelenítési név leképezés
_COL_MAP = {
    "Bankszamlaszam": "Bankszámlaszám",
    "Bankszamlaszam_fokonyv": "Főkönyv",
    "Bankszamlaszam_deviza": "Deviza",
    "Bankszamlaszam_tipus": "Típus",
    "Partner": "Partner",
}


class BankAccountEditView(QWidget):
    def __init__(self):
        super().__init__()
        self._selected_count = 0
        self._current_id = None  # a kijelölt/szerkesztett sor ID-ja (None = új sor)
        self._is_new_row = False  # True: Új sor módban vagyunk
        self._df_full = (
            None  # teljes DataFrame ID oszloppal (a kijelölés ID-jának kinyeréséhez)
        )
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
        title = QLabel("Bankszámlaszámok")
        title.setObjectName("view_title")
        main_layout.addWidget(title)

        # --- Eszközsáv ---
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.setContentsMargins(0, 0, 0, 0)

        self.query_button = QPushButton("Lekérdezés")
        set_button_icon(self.query_button, ICON_SEARCH, CLR_PRIMARY, CLR_PRIMARY_DIS)
        self.query_button.clicked.connect(self._prepare_query)
        toolbar.addWidget(self.query_button)

        toolbar.addStretch()

        self.export_button = QPushButton("Exportálás")
        self.export_button.setObjectName("secondary_button")
        set_button_icon(self.export_button, ICON_DOWNLOAD, CLR_SECONDARY, CLR_SECONDARY_DIS)
        self.export_button.clicked.connect(self._on_export)
        toolbar.addWidget(self.export_button)

        # CRUD gombsor — 320px-es fix widget, pontosan a detail panel fölött
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
            "Kattints a Lekérdezés gombra a bankszámlaszámok betöltéséhez"
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

        # Jobb: részlet panel
        detail_panel = QFrame()
        detail_panel.setObjectName("detail_panel")
        detail_panel.setFixedWidth(320)
        detail_panel.setStyleSheet("QFrame#detail_panel { background: white; }")
        detail_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(16, 16, 16, 16)
        detail_layout.setSpacing(10)

        detail_layout.addWidget(self._make_field_label("Bankszámlaszám"))
        self.ba_number_edit = QLineEdit()
        self.ba_number_edit.setEnabled(False)
        detail_layout.addWidget(self.ba_number_edit)

        detail_layout.addWidget(self._make_field_label("Főkönyv"))
        self.ba_ledger_edit = QLineEdit()
        self.ba_ledger_edit.setEnabled(False)
        detail_layout.addWidget(self.ba_ledger_edit)

        detail_layout.addWidget(self._make_field_label("Deviza"))
        self.ba_currency_combo = QComboBox()
        self.ba_currency_combo.addItems(["HUF", "EUR", "USD"])
        self.ba_currency_combo.setEnabled(False)
        detail_layout.addWidget(self.ba_currency_combo)

        detail_layout.addWidget(self._make_field_label("Típus"))
        self.ba_type_edit = QLineEdit()
        self.ba_type_edit.setEnabled(False)
        detail_layout.addWidget(self.ba_type_edit)

        detail_layout.addWidget(self._make_field_label("Partner"))
        self.ba_partner_combo = QComboBox()
        self.ba_partner_combo.addItems(["SPP", "SRP"])
        self.ba_partner_combo.setEnabled(False)
        detail_layout.addWidget(self.ba_partner_combo)

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
            df = self._db.query_bank_account_numbers()
            self._df_full = (
                df.copy()
            )  # ID oszlopot megtartjuk a kijelölés nyomon követéséhez

            df_display = df.drop(columns=["ID"], errors="ignore").rename(
                columns=_COL_MAP
            )

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
    #  Kijelölés kezelése (C2a)                                           #
    # ------------------------------------------------------------------ #

    def _on_selection_changed(self, selected, deselected):
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

            self.ba_number_edit.setText(get_val("Bankszámlaszám"))
            self.ba_ledger_edit.setText(get_val("Főkönyv"))

            deviza = get_val("Deviza")
            idx = self.ba_currency_combo.findText(deviza)
            self.ba_currency_combo.setCurrentIndex(idx if idx >= 0 else 0)

            self.ba_type_edit.setText(get_val("Típus"))

            partner = get_val("Partner")
            idx = self.ba_partner_combo.findText(partner)
            self.ba_partner_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self._enable_detail_panel(True)
            self.save_button.setEnabled(True)
        else:
            self._reset_detail_panel()

    def _reset_detail_panel(self):
        """Jobb panel törlése + mezők letiltása. A _selected_count-ot NEM érinti
        (azt kizárólag _on_selection_changed kezeli)."""
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
        self.ba_number_edit.setEnabled(enabled)
        self.ba_ledger_edit.setEnabled(enabled)
        self.ba_currency_combo.setEnabled(enabled)
        self.ba_type_edit.setEnabled(enabled)
        self.ba_partner_combo.setEnabled(enabled)

    # ------------------------------------------------------------------ #
    #  Új sor (C2b)                                                       #
    # ------------------------------------------------------------------ #

    def _on_add_row(self):
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
        self.ba_number_edit.setFocus()

    # ------------------------------------------------------------------ #
    #  Mentés (C2c)                                                       #
    # ------------------------------------------------------------------ #

    def _on_save(self):
        number = self.ba_number_edit.text().strip()
        ledger = self.ba_ledger_edit.text().strip()
        deviza = self.ba_currency_combo.currentText()
        tipus = self.ba_type_edit.text().strip()
        partner = self.ba_partner_combo.currentText()

        # --- Validáció ---
        errors = []

        if not number:
            errors.append("• A Bankszámlaszám mező nem lehet üres.")
        elif not re.fullmatch(r"\d{8}-\d{8}(-\d{8})?", number):
            errors.append(
                "• A Bankszámlaszám formátuma érvénytelen.\n"
                "  Elfogadott formátum: DDDDDDDD-DDDDDDDD vagy DDDDDDDD-DDDDDDDD-DDDDDDDD"
            )
        else:
            # Duplikáció ellenőrzés a betöltött adatok alapján
            if self._df_full is not None:
                existing = self._df_full[
                    self._df_full["Bankszamlaszam"].astype(str) == number
                ]
                # UPDATE esetén a saját sorát kizárjuk az ellenőrzésből
                if not self._is_new_row and self._current_id is not None:
                    existing = existing[existing["ID"] != self._current_id]
                if not existing.empty:
                    errors.append(
                        f'• A(z) "{number}" bankszamlaszam mar szerepel a listaban.'
                    )

        if not ledger:
            errors.append("• A Főkönyv mező nem lehet üres.")

        if errors:
            QMessageBox.warning(
                self,
                "Érvénytelen adatok",
                "\n".join(errors),
            )
            if not number or (
                number and not re.fullmatch(r"\d{8}-\d{8}(-\d{8})?", number)
            ):
                self.ba_number_edit.setFocus()
            elif not ledger:
                self.ba_ledger_edit.setFocus()
            return

        # --- Megerősítés ---
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
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # --- Mentés ---
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
            self._prepare_query()  # táblázat frissítése + panel + toolbar reset
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
            self._prepare_query()  # táblázat frissítése + panel + toolbar reset

    # ------------------------------------------------------------------ #
    #  Export (C3)                                                        #
    # ------------------------------------------------------------------ #

    def _on_export(self):
        self._progress_dialog = DbOperationProgressDialog()
        self._progress_dialog.set_message("Exportálás folyamatban...")
        self._progress_dialog.show()
        QTimer.singleShot(100, self._run_export)

    def _run_export(self):
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
        label = QLabel(text)
        label.setStyleSheet("font-size: 12px; color: #495057; background: transparent;")
        return label

    def _update_toolbar_state(self):
        n = self._selected_count
        self.delete_button.setText(f"  Törlés ({n})" if n > 0 else "  Törlés")
        self.delete_button.setEnabled(n > 0)
