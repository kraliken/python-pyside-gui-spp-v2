from PySide6.QtWidgets import QApplication
import sys
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)

    # QSS stíluslap betöltése (B2)
    with open("assets/styles/style.qss", "r", encoding="utf-8") as f:
        app.setStyleSheet(f.read())

    # Főablak létrehozása
    window = MainWindow(app)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
