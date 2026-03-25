# models/pandas_model.py
#
# PandasModel — pandas DataFrame és Qt táblázat (QTableView) közötti híd.
#
# A Qt táblázat (QTableView) nem tud közvetlenül pandas DataFrame-et megjeleníteni.
# Ehhez egy "modell" közvetítő osztály kell, amely a Qt MVC (Model-View-Controller)
# tervezési mintájának megfelelően adja át az adatokat a nézetnek.
#
# A PandasModel a QAbstractTableModel-ből örököl — a Qt ezt az alap osztályt
# biztosítja egyéni táblázatmodellek készítéséhez.

from PySide6.QtCore import Qt, QAbstractTableModel
from PySide6.QtGui import QColor, QBrush
import pandas as pd


class PandasModel(QAbstractTableModel):
    """Qt-kompatibilis táblázatmodell pandas DataFrame-hez.

    Funkciók:
      - Adatok megjelenítése QTableView-ban
      - Oszlopankénti formázó függvények (pl. ezres elválasztó, dátumformátum)
      - Oszlopankénti igazítás (balra, jobbra, középre)
      - Hibás sorok piros kiemelése (halvány piros háttér + piros szöveg)
      - Oszlop szerinti rendezés kattintásra
    """

    def __init__(
        self,
        df: pd.DataFrame,
        formatters: dict[str, callable] = None,
        alignments: dict[str, Qt.AlignmentFlag] = None,
    ):
        """
        df          — a megjelenítendő pandas DataFrame
        formatters  — szótár: oszlopnév → formázó függvény (pl. lambda x: f"{x:,.2f}")
        alignments  — szótár: oszlopnév → Qt igazítási flag (pl. Qt.AlignRight)
        """
        super().__init__()
        self._df = df
        # Ha nincs megadva formázó/igazítás szótár, üres szótárat használunk
        self._formatters = formatters or {}
        self._alignments = alignments or {}
        # Hibás sorok indexeinek halmaza — ezek pirossal jelennek meg
        self.invalid_rows = set()

    # --- Qt kötelező metódusok: a nézetnek ezek adják meg a táblázat méretét ---

    def rowCount(self, parent=None):
        """Visszaadja a sorok számát (a DataFrame sorainak száma)."""
        return self._df.shape[0]

    def columnCount(self, parent=None):
        """Visszaadja az oszlopok számát (a DataFrame oszlopainak száma)."""
        return self._df.shape[1]

    def data(self, index, role=Qt.DisplayRole):
        """Visszaadja egy adott cella megjelenítési adatát a Qt által kért szerepkör alapján.

        A Qt több "role"-t (szerepkört) kér le egy cellához:
          - DisplayRole:       a megjelenítendő szöveg
          - TextAlignmentRole: szöveg igazítása a cellán belül
          - BackgroundRole:    cella háttérszíne
          - ForegroundRole:    szöveg (betű) színe
        """
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()
        value = self._df.iloc[row, col]     # sor+oszlop alapján kiolvassuk az értéket
        column = self._df.columns[col]      # az oszlop neve (fejléc)

        if role == Qt.DisplayRole:
            # Ha van egyéni formázó az adott oszlophoz, alkalmazzuk
            formatter = self._formatters.get(column)
            if formatter:
                try:
                    return formatter(value)
                except Exception:
                    # Ha a formázó hibát dob (pl. None érték), egyszerű stringgé alakítunk
                    return str(value)
            return str(value)

        elif role == Qt.TextAlignmentRole:
            # Egyéni igazítás az oszlophoz (pl. számok jobbra igazítva)
            alignment = self._alignments.get(column)
            if alignment:
                return alignment

        elif role == Qt.BackgroundRole and row in self.invalid_rows:
            # Hibás sor: halvány piros háttér
            return QBrush(QColor("#fff5f5"))  # design-spec: halvány piros háttér
        elif role == Qt.ForegroundRole and row in self.invalid_rows:
            # Hibás sor: piros szöveg
            return QBrush(QColor("#e03131"))  # design-spec: piros szöveg

        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        """Visszaadja a táblázat fejléc-feliratait.

        Vízszintes fejléc (Horizontal): az oszlopneveket adja vissza (DataFrame column names)
        Függőleges fejléc (Vertical):   sorszámokat jelenít meg (1-től kezdve)
        """
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self._df.columns[section]
            else:
                return section + 1   # 0-tól indexel, de 1-től jelenítjük meg
        return None

    def sort(self, column, order):
        """Oszlop szerinti rendezés — a fejlécre kattintva hívja meg a Qt.

        A layoutAboutToBeChanged / layoutChanged jelzésekkel értesítjük a nézetet,
        hogy az adatok sorrendje megváltozott, és újra kell rajzolni a táblázatot.
        """
        colname = self._df.columns[column]
        ascending = order == Qt.AscendingOrder
        self.layoutAboutToBeChanged.emit()
        self._df.sort_values(
            by=colname, ascending=ascending, inplace=True, ignore_index=True
        )
        self.layoutChanged.emit()

    def set_invalid_rows(self, rows: set):
        """Beállítja a hibás sorok indexeinek halmazát, majd frissíti a nézetet.

        Pl. importáláskor a validációs hibás sorokat pirossal jelöli meg.
        """
        self.invalid_rows = rows
        self.layoutChanged.emit()   # frissítés: a nézet újrarajzolja a táblázatot
