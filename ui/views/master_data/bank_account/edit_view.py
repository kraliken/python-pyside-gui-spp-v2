from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTableView,
    QFileDialog,
    QMessageBox,
    QHeaderView,
    QApplication,
)
from database.database import DatabaseManager
import pandas as pd
import os
from models.pandas_model import PandasModel
from PySide6.QtCore import QTimer
from ui.dialogs.db_operation_progress import DbOperationProgressDialog


class BankAccountEditView(QWidget):
    def __init__(self):
        super().__init__()

        # ===== FŐ LAYOUT =====
        main_layout = QVBoxLayout()
        content_layout = QHBoxLayout()
        main_layout.addLayout(content_layout)
        self.setLayout(main_layout)

        # ===== BAL OLDAL =====
        left_layout = QVBoxLayout()

        self.title_label = QLabel("Bankszámlaszám")

        button_row = QHBoxLayout()

        self.select_button = QPushButton("Importálás")
        self.select_button.clicked.connect(self.load_xlsx_files)
        self.select_button.setFixedWidth(150)

        self.clear_button = QPushButton("Törlés")
        self.clear_button.clicked.connect(self.clear_import_table)
        self.clear_button.setEnabled(False)
        self.clear_button.setFixedWidth(150)

        self.save_button = QPushButton("Mentés adatbázisba")
        self.save_button.setEnabled(False)
        self.save_button.setFixedWidth(150)
        self.save_button.clicked.connect(self.confirm_and_save)

        button_row.addWidget(self.title_label)
        # --- Stretch középre ---
        button_row.addStretch()
        button_row.addWidget(self.select_button)
        button_row.addWidget(self.clear_button)
        button_row.addWidget(self.save_button)

        left_layout.addLayout(button_row)

        self.table_view = QTableView()
        self.table_view.setSortingEnabled(True)
        # self.table_view.horizontalHeader().setStretchLastSection(True)
        # self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

        left_layout.addWidget(self.table_view)

        content_layout.addLayout(left_layout, stretch=6)

        # ===== JOBB OLDAL =====
        self.title_label = QLabel("Bankszámlaszám törzs lekérdezése")

        right_layout = QVBoxLayout()
        right_layout.addWidget(self.title_label)

        content_layout.addLayout(right_layout, stretch=6)

        self.progress_dialog = None

        self.db = DatabaseManager()

        self.expected_columns = [
            "Bankszamlaszam",
            "Bankszamlaszam_fokonyv",
            "Bankszamlaszam_deviza",
            "Bankszamlaszam_tipus",
        ]

    def load_xlsx_files(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Válassz .XLS fájlokat", "", "XLSX fájlok (*.xlsx)"
        )

        if not file_path:
            return

        filename = os.path.basename(file_path)

        try:
            self.df = pd.read_excel(file_path)

            if self.df.columns.tolist() != self.expected_columns:
                QMessageBox.warning(
                    self,
                    "Fejléc eltérés",
                    f"A(z) '{filename}' fájl fejlécszerkezete eltér az elvárttól.",
                )

            self.df["Bankszamlaszam"] = self.df["Bankszamlaszam"].astype("string")

            # Főkönyvi szám: float → int → string, NaN esetén "NA"
            self.df["Bankszamlaszam_fokonyv"] = self.df["Bankszamlaszam_fokonyv"].apply(
                lambda x: str(int(x)) if pd.notnull(x) else "NA"
            )

            # Deviza mező: üres esetén "NA"
            self.df["Bankszamlaszam_deviza"] = self.df["Bankszamlaszam_deviza"].fillna(
                "NA"
            )

            # Az utolsó oszlopban viszont maradjon None (SQL NULL)
            self.df["Bankszamlaszam_tipus"] = self.df["Bankszamlaszam_tipus"].where(
                pd.notnull(self.df["Bankszamlaszam_tipus"]), ""
            )

            model = PandasModel(self.df)
            self.table_view.setModel(model)

            header = self.table_view.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.Fixed)

            header.resizeSection(0, 230)  # 0. oszlop = 250 px
            header.resizeSection(1, 170)
            header.resizeSection(2, 170)
            header.resizeSection(3, 170)

            self.clear_button.setEnabled(True)
            self.save_button.setEnabled(True)

        except Exception as e:
            QMessageBox.warning(
                self, "Hiba", f"{filename} beolvasása sikertelen:\n{str(e)}"
            )

    def clear_import_table(self):

        self.df_all = pd.DataFrame()
        self.table_view.setModel(None)

        self.clear_button.setEnabled(False)
        self.save_button.setEnabled(False)

    def confirm_and_save(self):

        reply = QMessageBox.question(
            self,
            "Megerősítés",
            "Biztosan szeretnéd az adatokat menteni az adatbázisba?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        # Progress dialog megjelenítése
        self.progress_dialog = DbOperationProgressDialog()
        self.progress_dialog.set_message("Adatok mentése folyamatban...")
        self.progress_dialog.show()
        QApplication.processEvents()

        QTimer.singleShot(100, lambda: self.run_database_save())

    def run_database_save(self):

        success, message = self.db.insert_bank_account_number_rows_bulk(self.df)

        self.progress_dialog.accept()
        self.progress_dialog = None

        if success:
            self.clear_import_table()
            QMessageBox.information(self, "Siker", message)
        else:
            QMessageBox.critical(self, "Hiba", message)
