# ui/views/master_data/bank_internal_code/edit_view.py
#
# BankInternalCodeEditView — Bank belső kódok beállítás nézet (CRUD).
#
# Adatbázis tábla: dbo.Bank_belsokod
# Oszlopok: ID (auto), Belsokod, Fokony, FokonyvText
#
# A BankAccountEditView-val azonos szerkezetű, de kisebb formmal:
#   - 3 mező (Belső kód, Főkönyv, Leírás) vs 5 mező (bankszámlaszámoknál)
#   - Leírás mező QTextEdit (többsoros) a Leíráshoz — QLineEdit helyett
#   - Nincs deviza/partner combo — csak szöveges mezők
#
# Műveletek:
#   C1: Lekérdezés gomb → DB lekérdezés → táblázat + rekordszám
#   C2e: Sorra kattintás → jobb panel feltöltése
#   C2f: Új sor gomb → üres panel, szerkesztés mód
#   C2g: Mentés → INSERT / UPDATE
#   C2h: Törlés → megerősítés → DELETE ID alapján
#   C3:  Exportálás → Excel az exports/ mappába

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTableView,
    QHeaderView,
    QLineEdit,
    QTextEdit,    # többsoros szövegbeviteli mező (a Leírás mezőhöz)
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

# Alkalmazás gyökérkönyvtár (4 szinttel feljebb: bank_internal_code → master_data → views → ui → v2)
_APP_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..")
)

# DB oszlopnév → megjelenítési név leképezés (táblázat fejlécekhez és exporthoz)
_COL_MAP = {
    "Belsokod": "Belső kód",
    "Fokony": "Főkönyv",
    "FokonyvText": "Leírás",
}


class BankInternalCodeEditView(QWidget):
    """Bank belső kódok kezelő nézet.

    A belső kód (pl. banki elszámolási kód) és a hozzá tartozó főkönyvi szám
    és leírás karbantartása. Struktúra: bal táblázat + jobb 320px-es szerkesztő panel.
    """

    def __init__(self):
        super().__init__()
        self._selected_count = 0    # kijelölt sorok száma
        self._current_id = None     # szerkesztett sor DB ID-ja
        self._is_new_row = False    # True: INSERT kell, False: UPDATE kell
        self._df_full = None        # teljes DataFrame ID oszloppal
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
        title = QLabel("Bank belső kódok")
        title.setObjectName("view_title")
        main_layout.addWidget(title)

        # Eszközsáv
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

        # CRUD gombsor — pontosan a detail panel fölött (fix 320px)
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

        # Tartalom: táblázat (bal) + szerkesztő panel (jobb)
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
            "Kattints a Lekérdezés gombra a bank belső kódok betöltéséhez"
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

        # Belső kód mező
        detail_layout.addWidget(self._make_field_label("Belső kód"))
        self.bc_code_edit = QLineEdit()
        self.bc_code_edit.setEnabled(False)
        detail_layout.addWidget(self.bc_code_edit)

        # Főkönyvi szám mező
        detail_layout.addWidget(self._make_field_label("Főkönyv"))
        self.bc_ledger_edit = QLineEdit()
        self.bc_ledger_edit.setEnabled(False)
        detail_layout.addWidget(self.bc_ledger_edit)

        # Leírás mező — QTextEdit (többsoros), fix 80px magassággal
        # A QLineEdit helyett QTextEdit-et használunk, mert a leírás hosszabb lehet
        detail_layout.addWidget(self._make_field_label("Leírás"))
        self.bc_description_edit = QTextEdit()
        self.bc_description_edit.setEnabled(False)
        self.bc_description_edit.setFixedHeight(80)  # kb. 4 sor magasság
        detail_layout.addWidget(self.bc_description_edit)

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
        """Lekérdezi a Bank_belsokod táblát és megjeleníti a táblázatban."""
        try:
            df = self._db.query_bank_internal_codes()
            self._df_full = df.copy()  # ID megtartva

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
    #  Kijelölés kezelése (C2e)                                           #
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

            self.bc_code_edit.setText(get_val("Belső kód"))
            self.bc_ledger_edit.setText(get_val("Főkönyv"))
            # setPlainText: QTextEdit-hez használjuk (nem setText)
            self.bc_description_edit.setPlainText(get_val("Leírás"))
            self._enable_detail_panel(True)
            self.save_button.setEnabled(True)
        else:
            self._reset_detail_panel()

    def _reset_detail_panel(self):
        """Jobb panel törlése + mezők letiltása. A _selected_count-ot NEM érinti."""
        self._current_id = None
        self._is_new_row = False
        self.bc_code_edit.clear()
        self.bc_ledger_edit.clear()
        self.bc_description_edit.clear()
        self._enable_detail_panel(False)
        self.save_button.setEnabled(False)

    def _enable_detail_panel(self, enabled: bool):
        self.bc_code_edit.setEnabled(enabled)
        self.bc_ledger_edit.setEnabled(enabled)
        self.bc_description_edit.setEnabled(enabled)

    # ------------------------------------------------------------------ #
    #  Új sor (C2f)                                                       #
    # ------------------------------------------------------------------ #

    def _on_add_row(self):
        """Új sor mód aktiválása — panel ürítése, szerkesztés engedélyezése."""
        self.table_view.clearSelection()
        self._is_new_row = True
        self._current_id = None
        self.bc_code_edit.clear()
        self.bc_ledger_edit.clear()
        self.bc_description_edit.clear()
        self._enable_detail_panel(True)
        self.save_button.setEnabled(True)
        self.bc_code_edit.setFocus()

    # ------------------------------------------------------------------ #
    #  Mentés (C2g)                                                       #
    # ------------------------------------------------------------------ #

    def _on_save(self):
        """Mentés gomb handler: validálás, megerősítés, INSERT vagy UPDATE."""
        code = self.bc_code_edit.text().strip()
        ledger = self.bc_ledger_edit.text().strip()
        # toPlainText(): QTextEdit-ből nyers szöveget olvas (HTML formázás nélkül)
        description = self.bc_description_edit.toPlainText().strip()

        errors = []
        if not code:
            errors.append("• A Belső kód mező nem lehet üres.")
        if not ledger:
            errors.append("• A Főkönyv mező nem lehet üres.")
        if not description:
            errors.append("• A Leírás mező nem lehet üres.")

        if errors:
            QMessageBox.warning(self, "Érvénytelen adatok", "\n".join(errors))
            # Fókusz az első hibás mezőre
            if not code:
                self.bc_code_edit.setFocus()
            elif not ledger:
                self.bc_ledger_edit.setFocus()
            else:
                self.bc_description_edit.setFocus()
            return

        confirm_msg = (
            "Biztosan hozzáadod az új belső kódot?"
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
            ok, msg = self._db.insert_bank_internal_code(code, ledger, description)
        else:
            ok, msg = self._db.update_bank_internal_code(
                self._current_id, code, ledger, description
            )

        if ok:
            QMessageBox.information(self, "Mentés sikeres", msg)
            self._prepare_query()  # táblázat frissítése
        else:
            QMessageBox.critical(
                self,
                "Mentési hiba",
                f"Sikertelen mentés.\n\nRészletek:\n{msg}",
            )

    # ------------------------------------------------------------------ #
    #  Törlés (C2h)                                                       #
    # ------------------------------------------------------------------ #

    def _on_delete(self):
        """Törlés gomb handler: megerősítés, majd DELETE az összes kijelölt sorhoz."""
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
            ok, err_msg = self._db.delete_bank_internal_code(id_)
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
    #  Export (C3)                                                        #
    # ------------------------------------------------------------------ #

    def _on_export(self):
        self._progress_dialog = DbOperationProgressDialog()
        self._progress_dialog.set_message("Exportálás folyamatban...")
        self._progress_dialog.show()
        QTimer.singleShot(100, self._run_export)

    def _run_export(self):
        """Lekérdezi és Excel fájlba menti a belső kódokat az exports/ mappába."""
        try:
            df = self._db.query_bank_internal_codes()
            df_export = df.rename(columns={"ID": "ID", **_COL_MAP})
            exports_dir = os.path.join(_APP_ROOT, "exports")
            os.makedirs(exports_dir, exist_ok=True)
            filename = f"belsokodok_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.xlsx"
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
        """Egységes stílusú mező-felirat label."""
        label = QLabel(text)
        label.setStyleSheet("font-size: 12px; color: #495057; background: transparent;")
        return label

    def _update_toolbar_state(self):
        """Törlés gomb felirat és állapot frissítése a kijelölt sorok száma alapján."""
        n = self._selected_count
        self.delete_button.setText(f"  Törlés ({n})" if n > 0 else "  Törlés")
        self.delete_button.setEnabled(n > 0)
