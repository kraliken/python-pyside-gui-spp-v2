# main.py
#
# Az alkalmazás belépési pontja (entry point).
# Ez az egyetlen fájl, amelyet közvetlenül futtatunk: `python main.py`
#
# Feladatai:
#   1. Létrehozza a Qt alkalmazásobjektumot (QApplication) — ez a GUI keretrendszer "motora"
#   2. Betölti a globális stíluslapot (QSS = Qt Style Sheet, a CSS Qt-megfelelője)
#   3. Létrehozza a főablakot (MainWindow)
#   4. Elindítja a Qt eseményhurkot (event loop) — ez tartja életben az ablakot és kezeli a kattintásokat

from PySide6.QtWidgets import QApplication
import sys
from ui.main_window import MainWindow


def main():
    # QApplication: a PySide6 GUI alkalmazás alapobjektuma — minden Qt widgethez kötelező.
    # sys.argv: a parancssorból átadott argumentumok listája (Qt egyes funkcióihoz szükséges)
    app = QApplication(sys.argv)

    # QSS stíluslap betöltése (B2)
    # A style.qss fájl határozza meg az összes widget megjelenését (színek, betűméretek, szegélyek).
    # A globális setStyleSheet() hívás az egész alkalmazásra érvényes — nem kell nézetenként ismételni.
    with open("assets/styles/style.qss", "r", encoding="utf-8") as f:
        app.setStyleSheet(f.read())

    # Főablak létrehozása — a MainWindow tartalmazza a sidebar-t, fejlécet és az összes nézetet
    window = MainWindow(app)

    # showMaximized(): az ablak maximalizálva nyílik meg (kitölti az asztalt),
    # de NEM fullscreen — a felhasználó átméretezheti és visszakicsinyítheti
    window.showMaximized()

    # app.exec(): elindítja a Qt eseményhurkot (event loop).
    # Ez a hívás BLOKKOL: addig fut, amíg a felhasználó be nem zárja az ablakot.
    # sys.exit(): az event loop visszatérési kódjával lép ki a programból (0 = sikeres futás)
    sys.exit(app.exec())


# Ez a feltétel biztosítja, hogy a main() csak akkor fusson le,
# ha ezt a fájlt közvetlenül indítják el (nem importálják másik modulból)
if __name__ == "__main__":
    main()
