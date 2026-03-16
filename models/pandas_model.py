from PySide6.QtCore import Qt, QAbstractTableModel
from PySide6.QtGui import QColor, QBrush
import pandas as pd


class PandasModel(QAbstractTableModel):

    def __init__(
        self,
        df: pd.DataFrame,
        formatters: dict[str, callable] = None,
        alignments: dict[str, Qt.AlignmentFlag] = None,
    ):
        super().__init__()
        self._df = df
        self._formatters = formatters or {}
        self._alignments = alignments or {}
        self.invalid_rows = set()  # hibás sorok indexei

    def rowCount(self, parent=None):
        return self._df.shape[0]

    def columnCount(self, parent=None):
        return self._df.shape[1]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        # value = self._df.iloc[index.row(), index.column()]
        # column = self._df.columns[index.column()]

        row = index.row()
        col = index.column()
        value = self._df.iloc[row, col]
        column = self._df.columns[col]

        if role == Qt.DisplayRole:
            formatter = self._formatters.get(column)
            if formatter:
                try:
                    return formatter(value)
                except Exception:
                    return str(value)
            return str(value)

        elif role == Qt.TextAlignmentRole:
            alignment = self._alignments.get(column)
            if alignment:
                return alignment

        elif role == Qt.BackgroundRole and row in self.invalid_rows:
            return QBrush(QColor(255, 200, 200))  # világos piros háttér
        elif role == Qt.ForegroundRole and row in self.invalid_rows:
            return QBrush(QColor(64, 64, 64))  # sötétszürke szöveg

        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self._df.columns[section]
            else:
                return section + 1
        return None

    def sort(self, column, order):
        """Oszlop szerinti rendezés"""
        colname = self._df.columns[column]
        ascending = order == Qt.AscendingOrder
        self.layoutAboutToBeChanged.emit()
        self._df.sort_values(
            by=colname, ascending=ascending, inplace=True, ignore_index=True
        )
        self.layoutChanged.emit()

    def set_invalid_rows(self, rows: set):
        self.invalid_rows = rows
        self.layoutChanged.emit()
