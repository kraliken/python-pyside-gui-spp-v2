# ui/dialogs/file_import_progress.py
#
# ProgressDialog — modális várakozó dialógus Excel fájl importálás közben.
#
# Hasonló a DbOperationProgressDialog-hoz, de fájlbeolvasási és validációs
# műveletek során jelenik meg (nem DB-mentésnél).
#
# Megjelenik: fájl beolvasása, oszlopvalidáció, adat-előkészítés alatt.
# Bezárul: a feldolgozás végeztével a hívó kód explicit bezárja (.close() / .accept()).

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel
from PySide6.QtCore import Qt


class ProgressDialog(QDialog):
    """Egyszerű modális dialógus fájlimportálás közbeni visszajelzéshez."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Importálás folyamatban")

        # setModal(True): blokkolja a főablak interakcióját, amíg a dialógus nyitva van
        self.setModal(True)
        self.setMinimumWidth(300)

        layout = QVBoxLayout()

        # Az üzenetcímke — mutatja az aktuális feldolgozási lépést
        self.label = QLabel("Feldolgozás...")
        self.label.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.label)
        self.setLayout(layout)
