from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel
from PySide6.QtCore import Qt


class ProgressDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Importálás folyamatban")
        self.setModal(True)
        self.setMinimumWidth(300)

        layout = QVBoxLayout()

        self.label = QLabel("Feldolgozás...")
        self.label.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.label)

        self.setLayout(layout)
