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


class VendorQueryView(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        control_panel_layout = QHBoxLayout()
        control_panel_layout.setSpacing(8)

        self.title_label = QLabel("Szállító lekérdezés")
        self.title_label.setObjectName("view_title")
        self.title_label.setAlignment(Qt.AlignLeft)
        control_panel_layout.addWidget(self.title_label, alignment=Qt.AlignVCenter)

        control_panel_layout.addStretch()

        self.query_button = QPushButton("Lekérdezés")
        set_button_icon(self.query_button, ICON_SEARCH, CLR_PRIMARY, CLR_PRIMARY_DIS)
        control_panel_layout.addWidget(self.query_button, alignment=Qt.AlignVCenter)

        self.hist_date_edit = QDateEdit()
        self.hist_date_edit.setDisplayFormat("yyyy. MM. dd.")
        self.hist_date_edit.setCalendarPopup(True)
        self.hist_date_edit.setDate(QDate.currentDate())
        self.hist_date_edit.setFixedWidth(158)
        self.hist_date_edit.setEnabled(False)
        control_panel_layout.addWidget(self.hist_date_edit, alignment=Qt.AlignVCenter)

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

        self.delete_button = QPushButton("Törlés")
        self.delete_button.setObjectName("delete_button")
        set_button_icon(self.delete_button, ICON_TRASH, CLR_DANGER, CLR_DANGER_DIS)
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self.delete_data)
        control_panel_layout.addWidget(self.delete_button, alignment=Qt.AlignVCenter)

        layout.addLayout(control_panel_layout)

        self.center_widget = QWidget()
        self.center_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.content_layout = QVBoxLayout()
        self.center_widget.setLayout(self.content_layout)

        self.info_label = QLabel(
            "Kattints a Lekérdezés gombra az IremsSzallito_stage tábla adatainak betöltéséhez"
        )
        self.info_label.setObjectName("empty_label")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(self.info_label)

        self.table_view = QTableView()
        self.table_view.setSortingEnabled(True)
        self.table_view.hide()
        self.content_layout.addWidget(self.table_view)

        layout.addWidget(self.center_widget)

        self.setLayout(layout)

        self.progress_dialog = None
        self._has_data = False

        self.db = DatabaseManager()
        self.query_button.clicked.connect(self.prepare_query)

    def _update_save_button_state(self):
        self.save_to_irems_hist_table_button.setEnabled(self._has_data)

    def prepare_query(self):
        self.progress_dialog = DbOperationProgressDialog()
        self.progress_dialog.set_message("Adatok lekérdezése folyamatban...")
        self.progress_dialog.show()

        QTimer.singleShot(100, self.load_data)

    def load_data(self):
        try:
            df = self.db.query_vendor_data()
            if df.empty:
                self._has_data = False
                self.info_label.setText(
                    "Az IremsSzallito_stage tábla jelenleg üres, nincs megjeleníthető adat."
                )
                self._update_save_button_state()
                self.delete_button.setEnabled(False)
            else:
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
            if hasattr(self, "progress_dialog") and self.progress_dialog:
                self.progress_dialog.accept()
                self.progress_dialog = None

    def delete_data(self):
        confirm = QMessageBox.question(
            self,
            "Megerősítés",
            "Biztosan törölni szeretnéd a szállító adatokat?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if confirm == QMessageBox.Yes:

            self.progress_dialog = DbOperationProgressDialog()
            self.progress_dialog.set_message("Adatok törlése folyamatban...")
            self.progress_dialog.show()

            QTimer.singleShot(100, self.perform_delete_data)

    def perform_delete_data(self):
        success, message = self.db.delete_vendor_stage()

        if self.progress_dialog:
            self.progress_dialog.accept()
            self.progress_dialog = None

        if success:
            QMessageBox.information(self, "Sikeres törlés", message)
            self.table_view.hide()
            self.info_label.setText("A szállító adatok törölve lettek.")
            self.info_label.show()
            self._has_data = False
            self._update_save_button_state()
            self.delete_button.setEnabled(False)
        else:
            QMessageBox.critical(self, "Hiba", f"Törlés sikertelen:\n\n{message}")

    def save_to_irems_hist_table(self):
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
        date_str = self.hist_date_edit.date().toString("yyyy-MM-dd")
        success, message = self.db.call_vendor_insert1(date_str)

        if self.progress_dialog:
            self.progress_dialog.accept()
            self.progress_dialog = None

        if success:
            QMessageBox.information(self, "Sikeres mentés", message)
            self.table_view.hide()
            self.info_label.setText("A szállító adatok mentve az Irems_Hist táblába.")
            self.info_label.show()
            self._has_data = False
            self._update_save_button_state()
            self.delete_button.setEnabled(False)
        else:
            QMessageBox.critical(self, "Hiba", f"Mentés sikertelen:\n\n{message}")
