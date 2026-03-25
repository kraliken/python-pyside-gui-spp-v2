# ui/dialogs/db_operation_progress.py
#
# DbOperationProgressDialog — modális várakozó dialógus adatbázis-műveletek közben.
#
# "Modális" azt jelenti: amíg ez a dialógus látható, a felhasználó nem tud
# a főablakban más elemre kattintani. Ez megakadályozza, hogy egy már futó
# DB-mentés közben újabb mentést indítsanak el.
#
# Megjelenik: mentés history-ba, törlés és egyéb DB-műveletek alatt.
# Bezárul: a művelet befejezése után a hívó kód explicit bezárja (.close() / .accept()).

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar
from PySide6.QtCore import Qt


class DbOperationProgressDialog(QDialog):
    """Egyszerű modális dialógus, amely egy szöveges üzenetet jelenít meg
    az adatbázis-művelet ideje alatt.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Adatbázis művelet")

        # setModal(True): blokkolja a főablak interakcióját, amíg a dialógus nyitva van
        self.setModal(True)
        self.setMinimumWidth(300)

        layout = QVBoxLayout()

        # Az üzenetcímke — szövege futásközben frissíthető a set_message() metódussal
        self.label = QLabel("Mentés folyamatban...")
        self.label.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.label)
        self.setLayout(layout)

    def set_message(self, message: str):
        """Frissíti a dialógusban megjelenített szöveget.

        Pl. a több lépéses DB-műveleteknél az aktuális lépést lehet kiírni:
        "Staging tábla törlése..." → "Adatok mentése..." → "Tárolt eljárás hívása..."
        """
        self.label.setText(message)
