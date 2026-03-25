# ui/views/home/home_view.py
#
# HomeView — kezdőlap nézet.
#
# Ez az első nézet, amelyet a felhasználó lát az alkalmazás indulásakor.
# Három fő részből áll:
#   1. App fejléc: ikon + alkalmazásnév + rövid leírás
#   2. Gyors műveletek kártyák: Bank / Szállító / Vevő importálás
#      (kattintásra átnavigál a megfelelő importnézetbe)
#   3. Stage állapot panel: mutatja, hány sor van az egyes staging táblákban
#
# Navigáció:
#   A kártyák navigate_to Signal-t bocsátanak ki (pl. "bank_import").
#   A MainWindow ezt a Signalt fogja fel és vált nézetet.
#
# Stage állapot:
#   Jelenleg hardcoded demo értékekkel működik (fejlesztői mód).
#   Éles üzemen a _load_stage_counts() metódusban lehet DB-re váltani.
#
# Változások (B2 / HomeView implementáció):
#   - Teljes újraírás: korábbi egy-label placeholder helyett valódi dashboard
#   - SVG ikonok: inline SVG stringek → QSvgRenderer + QPainter → QPixmap
#   - Gyors műveletek: 3 kattintható kártya (Bank/Szállító/Vevő importálás)
#     A kártyák a navigate_to Signal-on keresztül navigáltatják a MainWindow-t.
#   - Stage állapot panel: staging táblák sorszáma DB-ből (vagy hardcoded demo)
#   - showEvent: nézetre váltáskor automatikusan frissíti a stage sorokat.

from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QByteArray, QTimer
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

from database.database import DatabaseManager


# ============================================================
#  SVG ikonok (Feather Icons stílusú, outline)
#
#  Minden SVG string `{c}` helyőrzőt tartalmaz a szín számára.
#  Az _icon() segédfüggvény futásidőben helyettesíti be a kívánt színt.
# ============================================================

# Adatbázis ikon (app fejléchez és a gyors művelet előnézetéhez)
_SVG_DATABASE = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
     fill="none" stroke="{c}" stroke-width="1.5"
     stroke-linecap="round" stroke-linejoin="round">
  <ellipse cx="12" cy="5" rx="9" ry="3"/>
  <path d="M21 12c0 1.657-4.03 3-9 3S3 13.657 3 12"/>
  <path d="M3 5v14c0 1.657 4.03 3 9 3s9-1.343 9-3V5"/>
</svg>"""

# Rács ikon (Bank importálás kártyához)
_SVG_GRID = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
     fill="none" stroke="{c}" stroke-width="1.5"
     stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="3" width="7" height="7" rx="1"/>
  <rect x="14" y="3" width="7" height="7" rx="1"/>
  <rect x="3" y="14" width="7" height="7" rx="1"/>
  <rect x="14" y="14" width="7" height="7" rx="1"/>
</svg>"""

# Tehergépkocsi ikon (Szállító importálás kártyához)
_SVG_TRUCK = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
     fill="none" stroke="{c}" stroke-width="1.5"
     stroke-linecap="round" stroke-linejoin="round">
  <rect x="1" y="3" width="15" height="13" rx="1"/>
  <path d="M16 8h4l3 3v5h-7V8z"/>
  <circle cx="5.5" cy="18.5" r="2.5"/>
  <circle cx="18.5" cy="18.5" r="2.5"/>
</svg>"""

# Felhasználók ikon (Vevő importálás kártyához)
_SVG_USERS = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
     fill="none" stroke="{c}" stroke-width="1.5"
     stroke-linecap="round" stroke-linejoin="round">
  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
  <circle cx="9" cy="7" r="4"/>
  <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
  <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
</svg>"""

# Pipa-kör ikon (stage állapot: van adat)
_SVG_CHECK_CIRCLE = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
     fill="none" stroke="{c}" stroke-width="2"
     stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="10"/>
  <polyline points="9 12 11 14 15 10"/>
</svg>"""

# Óra ikon (stage állapot: üres vagy ismeretlen)
_SVG_CLOCK = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
     fill="none" stroke="{c}" stroke-width="1.5"
     stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="10"/>
  <polyline points="12 6 12 12 16 14"/>
</svg>"""


def _icon(svg_template: str, size: int, color: str) -> QPixmap:
    """SVG string → QPixmap (átlátszó háttér).

    Lépések:
      1. `{c}` helyőrző cseréje a kívánt színre az SVG szövegben
      2. Szöveg → QByteArray (Qt bináris formátum)
      3. QSvgRenderer: értelmezi az SVG-t
      4. QPixmap: üres, átlátszó kép létrehozása
      5. QPainter: rárajzolja az SVG-t a pixmapra
    """
    data = QByteArray(svg_template.replace("{c}", color).encode("utf-8"))
    renderer = QSvgRenderer(data)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


# ============================================================
#  HomeView
# ============================================================


class HomeView(QWidget):
    """Kezdőlap — alkalmazásleírás, gyors műveletek kártyák, stage állapot."""

    # Signal: nézetre navigálás (MainWindow köti be)
    # Lehetséges értékek: "bank_import" | "vendor_import" | "customer_import"
    navigate_to = Signal(str)

    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        # Stage állapot ikonok és számlálók nyilvántartása (kulcs = entitás neve)
        self._stage_icon_labels: dict[str, QLabel] = {}
        self._stage_count_labels: dict[str, QLabel] = {}
        self._setup_ui()

    # ------------------------------------------------------------------ #
    #  UI felépítése                                                       #
    # ------------------------------------------------------------------ #

    def _setup_ui(self):
        """Felépíti a kezdőlap teljes layoutját:
        app fejléc → szekciócím → gyors műveletek → szekciócím → stage panel → stretch
        """
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(22)

        root.addLayout(self._build_app_header())

        root.addWidget(self._build_section_label("GYORS MŰVELETEK"))
        root.addLayout(self._build_action_cards())
        root.addWidget(self._build_section_label("STAGE ÁLLAPOT"))
        root.addWidget(self._build_stage_panel())
        root.addStretch()   # az alján maradó helyet kitölti (az elemek felül tömörülnek)

        # Első stage frissítés rövid késleltetéssel — az UI már látható, mielőtt DB hívás indul
        QTimer.singleShot(300, self._load_stage_counts)

    # ---- App fejléc (ikon + alkalmazásnév + leírás) ----

    def _build_app_header(self) -> QHBoxLayout:
        """Felépíti az app fejlécet: kék database ikon + cím + leíró szöveg."""
        layout = QHBoxLayout()
        layout.setSpacing(14)

        # Kék keretű ikon doboz (50x50px, lekerekített sarkú)
        icon_box = QFrame()
        icon_box.setFixedSize(50, 50)
        icon_box.setStyleSheet(
            "background: #dbe4ff; border-radius: 10px; border: none;"
        )
        icon_inner = QHBoxLayout(icon_box)
        icon_inner.setContentsMargins(0, 0, 0, 0)
        db_lbl = QLabel()
        db_lbl.setPixmap(_icon(_SVG_DATABASE, 28, "#3b5bdb"))  # indigo kék ikon
        db_lbl.setAlignment(Qt.AlignCenter)
        db_lbl.setStyleSheet("background: transparent;")
        icon_inner.addWidget(db_lbl, alignment=Qt.AlignCenter)
        layout.addWidget(icon_box)

        # Cím + leíró szöveg (függőlegesen egymás alatt)
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title = QLabel("SPP Adatbetöltő")
        title.setStyleSheet(
            "font-size: 20px; font-weight: 700; color: #1c1c2e; background: transparent;"
        )
        # Rövid leírás egy sorban (wordWrap kikapcsolva)
        ver = QLabel(
            "Banki tranzakciós fájlok és szállítói / vevői fizetési adatok importálásához, validálásához és SQL Server adatbázisba való szinkronizálásához."
        )
        ver.setWordWrap(False)
        # ver.setFixedWidth(720)  # opcionális fix szélesség
        ver.setStyleSheet("font-size: 12px; color: #868e96; background: transparent;")
        text_col.addWidget(title)
        text_col.addWidget(ver)
        layout.addLayout(text_col)
        layout.addStretch()   # a fejléc után maradó helyet kitölti (bal igazítás)

        return layout

    # ---- Szekciócím ----

    def _build_section_label(self, text: str) -> QLabel:
        """Kis nagybetűs szekciócímke (pl. 'GYORS MŰVELETEK', 'STAGE ÁLLAPOT')."""
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #868e96; "
            "letter-spacing: 1px; background: transparent;"
        )
        return lbl

    # ---- Gyors műveletek kártyák ----

    def _build_action_cards(self) -> QHBoxLayout:
        """Felépíti a három gyors művelet kártyát vízszintesen egymás mellé."""
        layout = QHBoxLayout()
        layout.setSpacing(12)

        # Kártyák definíciói: (ikon SVG, cím, leírás, action string)
        cards = [
            (
                _SVG_GRID,
                "Bank importálás",
                "Banki tranzakciós fájlok betöltése\nés szinkronizálása az adatbázisba.",
                "bank_import",    # ezt a string-et bocsátja ki a navigate_to Signal
            ),
            (
                _SVG_TRUCK,
                "Szállító importálás",
                "Szállítói fizetési adatok\nimportálása XLSX formátumból.",
                "vendor_import",
            ),
            (
                _SVG_USERS,
                "Vevő importálás",
                "Vevői fizetési adatok importálása XLSX formátumból.",
                "customer_import",
            ),
        ]

        for svg, title, desc, action in cards:
            layout.addWidget(self._make_action_card(svg, title, desc, action))

        return layout

    def _make_action_card(self, svg: str, title: str, desc: str, action: str) -> QFrame:
        """Egyetlen gyors művelet kártya felépítése.

        A kártya egy fehér, lekerekített sarkú QFrame, amely kattintásra
        a navigate_to Signalt bocsátja ki a megadott action string-gel.

        Felépítése:
          - Felső sor: ikon (kék keretben) + nyíl (→)
          - Cím
          - Leírás
        """
        card = QFrame()
        card.setObjectName("action_card")
        card.setCursor(Qt.PointingHandCursor)   # mutató kurzor kattintható elemre
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        card.setStyleSheet(
            """
            QFrame#action_card {
                background: white;
                border: 1px solid #dee2e6;
                border-radius: 8px;
            }
            QFrame#action_card:hover {
                border-color: #4c6ef5;
                background: #f8f9ff;
            }
            """
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Felső sor: ikon doboz balra, nyíl jobbra
        top = QHBoxLayout()
        top.setSpacing(0)

        # Ikon doboz (42x42px, kék háttér, lekerekített)
        icon_box = QFrame()
        icon_box.setFixedSize(42, 42)
        icon_box.setStyleSheet("background: #dbe4ff; border-radius: 8px; border: none;")
        icon_inner = QHBoxLayout(icon_box)
        icon_inner.setContentsMargins(0, 0, 0, 0)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(_icon(svg, 22, "#3b5bdb"))
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("background: transparent;")
        icon_inner.addWidget(icon_lbl, alignment=Qt.AlignCenter)
        top.addWidget(icon_box)

        top.addStretch()

        # Nyíl → jelzi, hogy kattintható elem
        arrow = QLabel("→")
        arrow.setStyleSheet("color: #adb5bd; font-size: 15px; background: transparent;")
        top.addWidget(arrow, alignment=Qt.AlignTop)
        layout.addLayout(top)

        # Kártyacím
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            "font-size: 14px; font-weight: 600; color: #1c1c2e; background: transparent;"
        )
        layout.addWidget(title_lbl)

        # Rövid leírás
        desc_lbl = QLabel(desc)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(
            "font-size: 12px; color: #868e96; background: transparent;"
        )
        layout.addWidget(desc_lbl)

        # Kattintáskezelő: a navigate_to Signal-t bocsátja ki az action string-gel
        # Lambda closure: `a=action` rögzíti az aktuális action értéket
        card.mousePressEvent = lambda _e, a=action: self.navigate_to.emit(a)

        return card

    # ---- Stage állapot panel ----

    def _build_stage_panel(self) -> QFrame:
        """Felépíti a stage állapot panelt (fehér, lekerekített doboz, 3 sor).

        Minden sor egy staging táblát képvisel (Bank, Szállító, Vevő).
        A sorok ikoncímkéi és számlálócímkéi a _stage_icon_labels /
        _stage_count_labels szótárakba kerülnek, hogy _load_stage_counts()
        frissíteni tudja őket.
        """
        panel = QFrame()
        panel.setObjectName("stage_panel")
        panel.setStyleSheet(
            "QFrame#stage_panel { background: white; border: 1px solid #dee2e6; border-radius: 8px; }"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Staging táblák neve és belső kulcsa
        stages = [
            ("bank", "Bank stage"),
            ("vendor", "Szállító stage"),
            ("customer", "Vevő stage"),
        ]

        for i, (key, name) in enumerate(stages):
            is_last = i == len(stages) - 1   # az utolsó sornál nincs alsó szegély
            row_widget, icon_lbl, count_lbl = self._make_stage_row(name, is_last)
            layout.addWidget(row_widget)
            # Nyilvántartásba vesszük, hogy _load_stage_counts() frissíthesse
            self._stage_icon_labels[key] = icon_lbl
            self._stage_count_labels[key] = count_lbl

        return panel

    def _make_stage_row(
        self, name: str, is_last: bool
    ) -> tuple[QFrame, QLabel, QLabel]:
        """Egyetlen stage állapot sor felépítése.

        Visszaad: (sor widget, ikon label, számlálócímke)
        Az ikon és a számláló referenciáit a hívó elmenti a szótárakba.
        """
        row = QFrame()
        row.setObjectName("stage_row")
        # Az utolsó sornál nincs alsó szegély (ne duplázódjon a panel szegélyével)
        border = "border: none;" if is_last else "border-bottom: 1px solid #e9ecef;"
        row.setStyleSheet(f"QFrame#stage_row {{ background: transparent; {border} }}")

        layout = QHBoxLayout(row)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Ikon: alapból óra (szürke) — _load_stage_counts() lecseréli pipa-körre ha van adat
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(20, 20)
        icon_lbl.setPixmap(_icon(_SVG_CLOCK, 20, "#ced4da"))
        icon_lbl.setStyleSheet("background: transparent;")
        layout.addWidget(icon_lbl)

        # Staging tábla neve
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            "font-size: 13px; color: #212529; background: transparent;"
        )
        layout.addWidget(name_lbl)
        layout.addStretch()   # a számláló a jobb oldalra kerül

        # Sorszámláló: alapból "..." — _load_stage_counts() frissíti
        count_lbl = QLabel("...")
        count_lbl.setStyleSheet(
            "font-size: 12px; color: #adb5bd; background: transparent;"
        )
        layout.addWidget(count_lbl)

        return row, icon_lbl, count_lbl

    # ------------------------------------------------------------------ #
    #  Stage számlálók frissítése                                          #
    # ------------------------------------------------------------------ #

    def _load_stage_counts(self):
        """Frissíti a stage állapot sorokat — sorszám és ikon alapján.

        FEJLESZTŐI MÓD: hardcoded értékek (DB kapcsolat nélkül).
        Éles gépen:
          1. Kommentezd ki a `counts = {"bank": 142, ...}` sort.
          2. Vedd ki a kommentet az ÉLES DB blokk elől.

        Állapot logika:
          - count < 0:  DB hiba → szürke óra ikon, "—" szöveg
          - count == 0: üres tábla → szürke óra ikon, "0 sor" szöveg
          - count > 0:  van adat → zöld pipa ikon, "X sor" szöveg (félkövér)
        """
        # ------------------------------------------------------------------
        # FEJLESZTŐI MÓD — fix (hardcoded) értékek, DB kapcsolat nélkül
        # ------------------------------------------------------------------
        counts = {"bank": 142, "vendor": 0, "customer": 38}

        # ------------------------------------------------------------------
        # ÉLES DB — valós lekérdezés (database.py: query_stage_counts)
        # ------------------------------------------------------------------
        # try:
        #     counts = self.db.query_stage_counts()
        # except Exception:
        #     for lbl in self._stage_count_labels.values():
        #         lbl.setText("—")
        #     return
        # ------------------------------------------------------------------

        for key, count in counts.items():
            icon_lbl = self._stage_icon_labels.get(key)
            count_lbl = self._stage_count_labels.get(key)
            if not (icon_lbl and count_lbl):
                continue

            if count < 0:
                # DB hiba eset
                icon_lbl.setPixmap(_icon(_SVG_CLOCK, 20, "#ced4da"))
                count_lbl.setText("—")
                count_lbl.setStyleSheet(
                    "font-size: 12px; color: #adb5bd; background: transparent;"
                )
            elif count == 0:
                # Üres staging tábla
                icon_lbl.setPixmap(_icon(_SVG_CLOCK, 20, "#ced4da"))
                count_lbl.setText("0 sor")
                count_lbl.setStyleSheet(
                    "font-size: 12px; color: #adb5bd; background: transparent;"
                )
            else:
                # Van adat → zöld pipa, félkövér szöveg
                icon_lbl.setPixmap(_icon(_SVG_CHECK_CIRCLE, 20, "#2f9e44"))
                count_lbl.setText(f"{count:,} sor".replace(",", "\u202f"))  # keskeny szóköz ezres elválasztó
                count_lbl.setStyleSheet(
                    "font-size: 12px; font-weight: 600; color: #2f9e44; "
                    "background: transparent;"
                )

    def showEvent(self, event):
        """Qt esemény: akkor hívódik, amikor ez a nézet láthatóvá válik.

        Automatikusan frissíti a stage sorokat, ha a felhasználó visszalép
        a kezdőlapra (pl. import után érdemes látni az aktuális sorszámokat).
        100ms késleltetés: a nézet rajzolása megtörténik, mielőtt a DB hívás indul.
        """
        super().showEvent(event)
        QTimer.singleShot(100, self._load_stage_counts)
