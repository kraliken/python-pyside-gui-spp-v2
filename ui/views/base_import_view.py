# ui/views/base_import_view.py
#
# BaseImportView — közös alaposztály az összes import nézethez.
#
# Az alkalmazásban háromféle entitást lehet importálni: Bank, Szállító, Vevő.
# Mindegyiknek hasonló a felépítése: bal panel (fájlválasztó) + jobb panel (táblázat + gombok).
# Ez az osztály ezt a közös részt valósítja meg, hogy ne kelljen minden nézetben
# újra megírni — ez a "ne ismételd magad" (DRY) elv a szoftverfejlesztésben.
#
# Az import folyamat lépései:
#   1. Fájl kiválasztása → beolvasás pandas DataFrame-be
#   2. „Validálás" → oszlopszám, adattípus, kötelező mezők ellenőrzése
#   3. „Mentés adatbázisba" → megerősítő kérdés → progress dialógus → DB beszúrás
#   4. Ha hiba volt: „Hibák exportja" → hibás sorok mentése .xlsx fájlba
#
# Leszármazott osztályok (subclassok) kötelezően implementálják:
#   - load_files()          — fájl(ok) megnyitása és DataFrame feltöltése
#   - get_data_for_save()   — a mentendő DataFrame visszaadása
#   - validate_for_insert() — entitásspecifikus validáció
#   - run_database_save()   — tényleges DB mentés

import os
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QLabel,
    QListWidget,
    QTableView,
    QHeaderView,
    QMessageBox,
    QApplication,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QStyle,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor, QBrush
import pandas as pd
from models.pandas_model import PandasModel
from ui.dialogs.db_operation_progress import DbOperationProgressDialog
from database.database import DatabaseManager
from ui.icons import (
    ICON_UPLOAD, ICON_SAVE, ICON_TRASH, ICON_CHECK_CIRCLE, ICON_DOWNLOAD,
    set_button_icon,
    CLR_PRIMARY, CLR_PRIMARY_DIS, CLR_SECONDARY, CLR_SECONDARY_DIS,
    CLR_DANGER, CLR_DANGER_DIS,
)

# Az alkalmazás gyökérkönyvtára (v2/) — az exports/ mappa elérési útjához szükséges
_APP_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)


class _HighlightDelegate(QStyledItemDelegate):
    """Egyéni delegált, amely QSS stíluslap jelenlétében is helyesen jeleníti meg
    a PandasModel BackgroundRole / ForegroundRole által megadott sor-kiemelési
    színeket (hibás sorok: #fff5f5 háttér, #e03131 szöveg).

    Probléma: a Qt QStyleSheetStyle az alternate-background-color QSS szabály esetén
    felülírja a modell BackgroundRole-ját, így a hibás sorok piros kiemelése elvész.

    Megoldás: ez a delegált a hátteret és a szöveget manuálisan rajzolja,
    megkerülve a QSS rendering pipeline-t — így a kiemelés biztosan megjelenik.
    """

    def paint(self, painter, option: QStyleOptionViewItem, index):
        # Lekérjük a cella háttér- és szövegszínét a modelltől
        bg = index.data(Qt.BackgroundRole)
        fg = index.data(Qt.ForegroundRole)

        if (
            bg is not None
            and isinstance(bg, QBrush)
            and not (option.state & QStyle.State_Selected)  # kijelölt soroknál ne alkalmazzuk
        ):
            bg_color = bg.color()
            fg_color = (
                fg.color()
                if (fg is not None and isinstance(fg, QBrush))
                else option.palette.color(option.palette.Text)  # alapértelmezett szövegszín
            )

            # Háttér kézi festése (QSS override-ot kikerülve)
            painter.fillRect(option.rect, bg_color)

            # Szöveg kézi festése
            text = index.data(Qt.DisplayRole)
            if text:
                align = index.data(Qt.TextAlignmentRole) or int(
                    Qt.AlignLeft | Qt.AlignVCenter
                )
                text_rect = option.rect.adjusted(8, 2, -8, -2)  # 8px belső margó
                painter.save()
                painter.setPen(fg_color)
                painter.setFont(option.font)
                painter.drawText(text_rect, int(align), str(text))
                painter.restore()
        else:
            # Normál (nem hibás) soroknál az alapértelmezett Qt rajzolást használjuk
            super().paint(painter, option, index)


class _PlaceholderTableView(QTableView):
    """QTableView leszármazott, amely üres modell esetén 'Nincs adat' szöveget
    rajzol a táblázat közepére — így a felhasználó tudja, hogy nincs megjelenítendő adat.

    Ez elegánsabb, mint egy külön QLabel-t rejtegetni/mutatni.
    """

    _PLACEHOLDER = "Nincs adat"

    def paintEvent(self, event):
        # Először az alap táblázat rajzolódik (fejléc, sorok, szegélyek)
        super().paintEvent(event)
        # Ha nincs modell vagy a modellben nincs sor, kiírjuk a helyőrző szöveget
        model = self.model()
        if model is None or model.rowCount() == 0:
            painter = QPainter(self.viewport())
            painter.setPen(QColor("#868e96"))   # szürke szöveg
            painter.drawText(self.viewport().rect(), Qt.AlignCenter, self._PLACEHOLDER)


class BaseImportView(QWidget):
    """Közös alaposztály az összes import nézethez.

    Az osztály kiszervezi a kétpaneles elrendezést, a megerősítő/progress
    dialógusok kezelését és a táblázat frissítését. A leszármazottaknak a
    következő metódusokat kell implementálniuk:
      - load_files()           — fájl(ok) betöltése és df feltöltése
      - get_data_for_save()    — a mentendő DataFrame visszaadása
      - validate_for_insert()  — validációs logika
      - run_database_save()    — tényleges DB mentés (hide_progress() hívással)

    Validálás–mentés folyamat:
      1. Fájl betöltése → „Validálás" gomb aktív, „Mentés" inaktív
      2. „Validálás" → ha OK: „Mentés" aktív; ha hiba: „Hibák exportja" aktív
      3. „Mentés adatbázisba" → megerősítő dialog → DB mentés
      4. „Hibák exportja" → hibás sorok .xlsx-be exportálva (exports/ mappa)
    """

    def __init__(self):
        super().__init__()
        self.progress_dialog = None          # az aktív progress dialógus referenciája
        self.db = DatabaseManager()          # adatbázis kapcsolat
        self._error_rows: set = set()        # hibás sorok indexei (validáció során töltődik)

    def setup_ui(self, title: str, import_button_label: str = "Importálás"):
        """Felépíti a kétpaneles elrendezést.

        Felül: oldalnézet-cím (view_title stílussal).
        Bal oldal: fehér panel (left_panel) — alcím, fájl-kiválasztó gomb,
                   no_file_label / fájllista, Törlés gomb.
        Jobb oldal: Validálás + Mentés + Hibák exportja gombok (header_row),
                    táblázat (_PlaceholderTableView).

        A subclass az __init__-ben a self.header_row-ba szúrhat be extra
        widgeteket a save_button UTÁN, stretch ELÉ (insertWidget pozíció: 3).
        """
        # Fő függőleges elrendezés: cím felül, kétpaneles tartalom alul
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Oldalnézet-cím (view_title stílussal, 24px bal margóval) ---
        self.title_label = QLabel(title)
        self.title_label.setObjectName("view_title")
        title_bar = QWidget()
        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(24, 16, 24, 8)
        title_bar_layout.addWidget(self.title_label)
        main_layout.addWidget(title_bar)

        # --- Kétpaneles tartalom (bal + jobb) ---
        content_layout = QHBoxLayout()
        content_layout.setSpacing(0)
        content_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addLayout(content_layout, 1)  # stretch=1: kitölti a fennmaradó helyet

        # ===== BAL PANEL — fájlválasztó és fájllista =====
        left_panel = QWidget()
        left_panel.setObjectName("left_panel")   # QSS: fehér háttér, jobb szegély
        left_panel_layout = QVBoxLayout(left_panel)
        left_panel_layout.setContentsMargins(16, 12, 16, 16)
        left_panel_layout.setSpacing(10)

        # Fájl kiválasztó gomb — kattintásra megnyitja a fájlböngészőt (load_files())
        self.select_button = QPushButton(import_button_label)
        set_button_icon(self.select_button, ICON_UPLOAD, CLR_PRIMARY, CLR_PRIMARY_DIS)
        self.select_button.clicked.connect(self.load_files)
        left_panel_layout.addWidget(self.select_button)

        # Fájlterület doboz: mindig látható keretes doboz
        # Belül váltakozó két widget:
        #   - no_file_label: "Nincs betöltött fájl" (ha még nincs fájl)
        #   - file_list_widget: betöltött fájlok listája (ha van legalább egy)
        file_area = QWidget()
        file_area.setObjectName("file_area_box")
        file_area.setStyleSheet(
            "QWidget#file_area_box { background: white; border: 1px solid #dee2e6; border-radius: 4px; }"
        )
        file_area_layout = QVBoxLayout(file_area)
        file_area_layout.setContentsMargins(4, 4, 4, 4)
        file_area_layout.setSpacing(0)

        # Helyőrző szöveg — fájl betöltése előtt látható
        self.no_file_label = QLabel("Nincs betöltött fájl")
        self.no_file_label.setObjectName("no_file_label")
        self.no_file_label.setAlignment(Qt.AlignCenter)
        file_area_layout.addWidget(self.no_file_label)

        # Fájllista — betöltött fájlok neveit tartalmazza (kezdetben rejtett)
        self.file_list_widget = QListWidget()
        self.file_list_widget.setStyleSheet("QListWidget { border: none; background: transparent; }")
        self.file_list_widget.hide()
        file_area_layout.addWidget(self.file_list_widget, 1)

        left_panel_layout.addWidget(file_area, 1)  # stretch=1: kitölti a fennmaradó helyet

        # Törlés gomb — törli a betöltött fájlokat és a táblázatot; kezdetben tiltott
        self.clear_button = QPushButton("Törlés")
        self.clear_button.setObjectName("clear_button")
        set_button_icon(self.clear_button, ICON_TRASH, CLR_DANGER, CLR_DANGER_DIS)
        self.clear_button.clicked.connect(self.clear_data)
        self.clear_button.setEnabled(False)
        left_panel_layout.addWidget(self.clear_button)

        # A bal panel 3x akkora széles, mint amekkora lenne alapértelmezetten
        content_layout.addWidget(left_panel, stretch=3)

        # Fájllista láthatóságának automatikus kezelése:
        # ha új elem kerül a listába → fájllista látható; ha törlés → helyőrző látható
        self.file_list_widget.model().rowsInserted.connect(self._update_file_list_state)
        self.file_list_widget.model().modelReset.connect(self._update_file_list_state)

        # ===== JOBB PANEL — gombok és táblázat =====
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(16, 12, 16, 16)
        right_layout.setSpacing(10)

        # --- Validálás gomb (kezdetben tiltott — fájl betöltése szükséges) ---
        self.validate_button = QPushButton("Validálás")
        set_button_icon(self.validate_button, ICON_CHECK_CIRCLE, CLR_PRIMARY, CLR_PRIMARY_DIS)
        self.validate_button.setEnabled(False)
        self.validate_button.clicked.connect(self._run_validation)

        # --- Mentés gomb (tiltott — sikeres validáció szükséges) ---
        self.save_button = QPushButton("Mentés adatbázisba")
        set_button_icon(self.save_button, ICON_SAVE, CLR_PRIMARY, CLR_PRIMARY_DIS)
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.confirm_and_save)

        # --- Hibák exportja gomb (rejtett — csak sikertelen validáció után jelenik meg) ---
        self.export_errors_button = QPushButton("Hibák exportja")
        self.export_errors_button.setObjectName("secondary_button")
        set_button_icon(self.export_errors_button, ICON_DOWNLOAD, CLR_SECONDARY, CLR_SECONDARY_DIS)
        self.export_errors_button.setEnabled(False)
        self.export_errors_button.hide()
        self.export_errors_button.clicked.connect(self._export_error_rows)

        # Gombsor (header_row): Validálás | Mentés | Hibák exportja | (stretch)
        # Extra gombot a subclassok a save_button UTÁN szúrhatnak be: insertWidget(pozíció, gomb)
        self.header_row = QHBoxLayout()
        self.header_row.setSpacing(8)
        self.header_row.addWidget(self.validate_button, alignment=Qt.AlignVCenter)
        self.header_row.addWidget(self.save_button, alignment=Qt.AlignVCenter)
        self.header_row.addWidget(self.export_errors_button, alignment=Qt.AlignVCenter)
        self.header_row.addStretch()   # jobb oldalon maradó helyet kitölti
        right_layout.addLayout(self.header_row)

        # Táblázat: mindig látható; üres állapotban "Nincs adat" szöveget jelenít meg
        # _HighlightDelegate: biztosítja a hibás sorok piros kiemelését QSS jelenlétében is
        self.table_view = _PlaceholderTableView()
        self.table_view.setSortingEnabled(True)
        self.table_view.setItemDelegate(_HighlightDelegate(self.table_view))
        right_layout.addWidget(self.table_view, 1)

        content_layout.addWidget(right_widget, stretch=10)

    # -------------------------------------------------------------------------
    # Közös segédmetódusok
    # -------------------------------------------------------------------------

    def _update_file_list_state(self):
        """Váltja a no_file_label / file_list_widget láthatóságát.

        Ha van legalább egy fájl a listában → fájllista látható, helyőrző rejtett.
        Ha üres a lista → helyőrző látható, fájllista rejtett.
        """
        has_files = self.file_list_widget.count() > 0
        self.no_file_label.setVisible(not has_files)
        self.file_list_widget.setVisible(has_files)

    def _on_file_loaded(self):
        """Fájl sikeres betöltése után hívandó állapotváltás.

        Aktiválja a Validálás gombot; Mentés és Hibák exportja gombokat
        visszaállítja alapállapotba (tiltott/rejtett). Törli az előző validáció eredményét.
        A subclassoknak ezt kell hívniuk a load_files() végén a gombkezelés helyett.
        """
        self._error_rows = set()               # előző validáció hibái törlődnek
        self.clear_button.setEnabled(True)
        self.validate_button.setEnabled(True)  # fájl betöltve → validálás lehetséges
        self.save_button.setEnabled(False)     # mentés csak validáció után
        self.export_errors_button.hide()
        self.export_errors_button.setEnabled(False)

    def _run_validation(self):
        """Validálás gomb handler: lefuttatja a validate_for_insert logikát.

        Siker esetén: Mentés gomb aktív, Validálás gomb tiltott.
        Hiba esetén: ha vannak hibás sorok, Hibák exportja gomb megjelenik.
        """
        data = self.get_data_for_save()
        if data.empty:
            QMessageBox.warning(self, "Hiba", "Nincs betöltött adat a validáláshoz.")
            return

        self._error_rows = set()
        result = self.validate_for_insert(data)

        if result:
            # Sikeres validáció: mentés engedélyezve
            self.save_button.setEnabled(True)
            self.validate_button.setEnabled(False)
            self.export_errors_button.hide()
            self.export_errors_button.setEnabled(False)
            QMessageBox.information(
                self, "Validáció sikeres", "Az adatok ellenőrzése hibátlan. Mentés engedélyezve."
            )
        else:
            # Sikertelen validáció: mentés tiltott, hibás sorok exportálhatók
            self.save_button.setEnabled(False)
            if self._error_rows:
                self.export_errors_button.show()
                self.export_errors_button.setEnabled(True)

    def _export_error_rows(self):
        """Hibás sorok exportálása .xlsx fájlba az exports/ mappába.

        A hibás sorok indexeit a validate_for_insert() írja self._error_rows-ba.
        Az exports/ mappa automatikusan létrejön, ha még nem létezik.
        A fájlnév tartalmazza az aktuális dátumot és időt (pl. validacios_hibak_2025-03-25_143022.xlsx).
        """
        if not self._error_rows:
            QMessageBox.warning(self, "Hiba", "Nincs exportálható hibás sor.")
            return

        data = self.get_data_for_save()
        if data.empty:
            QMessageBox.warning(self, "Hiba", "Nincs betöltött adat.")
            return

        try:
            # A hibás sorok kiválasztása az indexük alapján
            error_df = data.loc[sorted(self._error_rows)]
        except KeyError:
            QMessageBox.warning(self, "Hiba", "A hibás sorok már nem elérhetők.")
            return

        # Exports mappa létrehozása (ha nem létezik)
        exports_dir = os.path.join(_APP_ROOT, "exports")
        os.makedirs(exports_dir, exist_ok=True)

        # Időbélyeges fájlnév generálása
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        filename = f"validacios_hibak_{timestamp}.xlsx"
        filepath = os.path.join(exports_dir, filename)

        try:
            error_df.to_excel(filepath, index=False)
            QMessageBox.information(
                self,
                "Export sikeres",
                f"{len(error_df)} hibás sor exportálva:\n{filepath}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Hiba", f"Export sikertelen:\n{str(e)}")

    def confirm_and_save(self):
        """Közös mentési folyamat: üresség-ellenőrzés → megerősítő dialog → progress → DB.

        A validáció már a „Validálás" gombbal előzetesen megtörtént;
        a mentés csak sikeres validáció után érhető el.

        QTimer.singleShot(100, ...): 100ms késleltetéssel indítja a DB műveletet,
        hogy a progress dialógus meg tudjon jelenni a Qt eseményhuroknak köszönhetően
        (a GUI frissítés és a DB hívás ugyanazon a szálon fut).
        """
        data = self.get_data_for_save()

        if data.empty:
            QMessageBox.warning(self, "Hiba", "Nincs betöltött adat a mentéshez.")
            return

        # Megerősítő párbeszédablak — a felhasználónak jóvá kell hagynia a mentést
        reply = QMessageBox.question(
            self,
            "Megerősítés",
            "Biztosan szeretnéd az adatokat menteni az adatbázisba?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,   # alapértelmezett: Nem (biztonságosabb)
        )

        if reply != QMessageBox.Yes:
            return

        # Progress dialógus megjelenítése, majd 100ms után DB mentés indítása
        self.show_progress("Adatok mentése folyamatban...")
        QTimer.singleShot(100, lambda: self.run_database_save(data))

    def clear_data(self):
        """Alap törlés: fájllista, táblázat, gombok és validáció visszaállítása alapállapotba.

        A subclassoknak super().clear_data() hívása után kell nullázniuk
        a saját DataFrame-jüket és egyéb entitásspecifikus állapotukat.
        """
        self.file_list_widget.clear()
        self._update_file_list_state()
        self.table_view.setModel(None)      # táblázat törlése
        self._error_rows = set()
        self.clear_button.setEnabled(False)
        self.validate_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.export_errors_button.hide()
        self.export_errors_button.setEnabled(False)

    def show_progress(self, message: str = "Adatok mentése folyamatban..."):
        """Megjeleníti a DB művelet progress dialógust a megadott üzenettel."""
        self.progress_dialog = DbOperationProgressDialog()
        self.progress_dialog.set_message(message)
        self.progress_dialog.show()
        QApplication.processEvents()   # a GUI frissül, hogy a dialógus valóban megjelenjen

    def hide_progress(self):
        """Bezárja a progress dialógust.

        A run_database_save() végén kötelező meghívni, különben a dialógus
        a DB művelet után is nyitva marad és lefagyasztja a főablakot.
        """
        if self.progress_dialog:
            self.progress_dialog.accept()
            self.progress_dialog = None

    def update_table_view(
        self,
        df: pd.DataFrame,
        formatters: dict | None = None,
        alignments: dict | None = None,
    ):
        """Frissíti a táblázatot a megadott DataFrame-mel és formázókkal.

        Új PandasModel-t hoz létre és beállítja a táblázatra.
        Ha a DataFrame üres, nem tesz semmit (a táblázat marad "Nincs adat" állapotban).
        """
        if df.empty:
            return
        model = PandasModel(
            df,
            formatters=formatters or {},
            alignments=alignments or {},
        )
        self.table_view.setModel(model)
        # Interactive: a felhasználó maga állíthatja az oszlopszélességeket húzással
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

    # -------------------------------------------------------------------------
    # Entitásspecifikus metódusok — subclassoknak kötelező implementálni
    # -------------------------------------------------------------------------

    def load_files(self):
        """Fájl(ok) megnyitása, beolvasása és a belső DataFrame feltöltése.

        A végén _on_file_loaded() hívása szükséges a gombállapot kezeléséhez.
        """
        raise NotImplementedError

    def get_data_for_save(self) -> pd.DataFrame:
        """Visszaadja a mentendő DataFrame-et (validáció és DB mentés előtt)."""
        raise NotImplementedError

    def validate_for_insert(self, df: pd.DataFrame) -> bool:
        """Ellenőrzi a mentési feltételeket; False esetén hibaüzenetet jelenít meg.

        Hibás sorok esetén self._error_rows-ba kell írni az érintett indexeket,
        hogy a „Hibák exportja" gomb működhessen.
        """
        raise NotImplementedError

    def run_database_save(self, df: pd.DataFrame):
        """Elvégzi a DB mentést; végén kötelező hide_progress() hívás."""
        raise NotImplementedError
