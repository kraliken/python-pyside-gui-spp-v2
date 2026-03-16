# db_operation_progress.py

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar
from PySide6.QtCore import Qt


class DbOperationProgressDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Adatbázis művelet")
        self.setModal(True)
        self.setMinimumWidth(300)

        layout = QVBoxLayout()

        self.label = QLabel("Mentés folyamatban...")
        self.label.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.label)

        self.setLayout(layout)

    def set_message(self, message: str):
        self.label.setText(message)
