# ui/main_window.py
#
# MainWindow — az alkalmazás főablaka.
#
# Felépítése:
#   ┌─────────────────────────────────────────────────┐
#   │  Fejlécsáv (40px, sötét #151929)                │
#   ├──────────────┬──────────────────────────────────┤
#   │  Sidebar     │  QStackedWidget (tartalomterület) │
#   │  (210px,     │                                   │
#   │  sötét)      │  Csak egy nézet látható egyszerre │
#   └──────────────┴──────────────────────────────────┘
#
# Navigáció:
#   - A sidebar nav gombjaira kattintva a _navigate() metódus vált nézetet
#     a QStackedWidget-ben, és átállítja az aktív gomb stílusát
#   - A kezdőlap kártyáiról érkező navigate_to Signal szintén _navigate()-et hív
#
# Változások (B1 — sidebar):
#   - QMenuBar eltávolítva, bal oldali sötét sidebar váltja ki.
#   - _build_header(): sötét fejlécsáv (#151929), alkalmazásnév + verzió.
#   - _build_sidebar(): 210px sötét panel (#1e2130), szekciók, nav gombok.
#   - _navigate(): aktív/inaktív gombállapot váltása (inline setStyleSheet).
#
# Változások (HomeView integráció):
#   - home_view.navigate_to Signal bekötve → _handle_home_navigate().
#   - _action_map: "bank_import" / "vendor_import" / "customer_import"
#     string-kulcsok → (view, sidebar_button) párok.
#   - _nav_buttons index-térkép a kódban kommentben dokumentálva.

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
)
from PySide6.QtCore import Qt

# Az összes nézet importálása — minden entitáshoz (Bank, Szállító, Vevő, Beállítások)
# külön osztály van, amelyet a QStackedWidget kezel
from ui.views.home.home_view import HomeView
from ui.views.bank.query_view import BankQueryView
from ui.views.bank.import_view import BankImportView

from ui.views.vendor.query_view import VendorQueryView
from ui.views.vendor.import_view import VendorImportView
from ui.views.vendor.excel_import_view import VendorExcelImportView

from ui.views.customer.query_view import CustomerQueryView
from ui.views.customer.import_view import CustomerImportView
from ui.views.customer.excel_import_view import CustomerExcelImportView

from ui.views.master_data.bank_account.edit_view import BankAccountEditView
from ui.views.master_data.bank_internal_code.edit_view import BankInternalCodeEditView
from ui.views.master_data.partner.edit_view import PartnerEditView


# Sidebar és fejléc színkonstansok — egy helyen definiálva, hogy könnyen módosíthatók legyenek
_HEADER_BG = "#151929"          # fejlécsáv háttérszíne (nagyon sötét kék-szürke)
_SIDEBAR_BG = "#1e2130"         # sidebar háttérszíne (sötét kék-szürke)
_SIDEBAR_ACTIVE_BG = "#2a3150"  # aktív nav gomb háttere (kissé világosabb kék)
_SIDEBAR_ACTIVE_BORDER = "#3b5bdb"  # aktív gomb bal szegélye (indigo kék)
_SIDEBAR_TEXT = "#c9d1d9"       # nav gomb szövegszíne (halvány fehér)
_SIDEBAR_SECTION = "#6e7891"    # szekciócímke szövegszíne (szürke)
_SIDEBAR_WIDTH = 210            # sidebar szélessége pixelben


class MainWindow(QMainWindow):
    """Az alkalmazás főablaka — fejlécsáv, sidebar navigáció, QStackedWidget tartalomterület."""

    def __init__(self, app):
        super().__init__()
        self.app = app

        # Nav gombok listája (sorrendben, ahogy a sidebarba kerülnek)
        self._nav_buttons: list[QPushButton] = []
        # Az éppen aktív (kijelölt) nav gomb referenciája
        self._active_button: QPushButton | None = None

        self.setWindowTitle("BPiON Adatfeldolgozó")

        # Minimumméret dinamikusan a képernyő méretéből számolva:
        # a felhasználó visszakicsinyítheti, de csak kicsit (screen - 200/150px)
        screen = app.primaryScreen().availableGeometry()
        min_w = max(1200, screen.width() - 200)
        min_h = max(650, screen.height() - 150)
        self.setMinimumSize(min_w, min_h)

        # QMenuBar elrejtése — sidebar váltja ki (nincs szükség menüsorra)
        self.menuBar().hide()

        # --- Az összes nézet példányosítása induláskor ---
        # (nem "lazy loading" — minden nézet kész van, csak a láthatóság vált)
        self.home_view = HomeView()
        self.bank_query_view = BankQueryView()
        self.bank_import_view = BankImportView()
        self.vendor_query_view = VendorQueryView()
        self.vendor_import_view = VendorImportView()
        self.vendor_excel_import_view = VendorExcelImportView()
        self.customer_query_view = CustomerQueryView()
        self.customer_import_view = CustomerImportView()
        self.customer_excel_import_view = CustomerExcelImportView()
        self.bank_account_number_edit_view = BankAccountEditView()
        self.bank_internal_code_edit_view = BankInternalCodeEditView()
        self.partner_edit_view = PartnerEditView()

        # --- Főwidget: minden widget ebbe kerül ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Fejlécsáv: teljes szélességben, felül
        main_layout.addWidget(self._build_header())

        # Törzsterület: sidebar bal oldalt + tartalomterület jobb oldalt
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        body_layout.addWidget(self._build_sidebar())

        # QStackedWidget — a tartalomterület:
        # egyszerre csak egy widget látható; nav gomb kattintásra vált
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setStyleSheet("QStackedWidget { background: white; }")
        for view in [
            self.home_view,
            self.bank_query_view,
            self.bank_import_view,
            self.vendor_query_view,
            self.vendor_import_view,
            self.vendor_excel_import_view,
            self.customer_query_view,
            self.customer_import_view,
            self.customer_excel_import_view,
            self.bank_account_number_edit_view,
            self.bank_internal_code_edit_view,
            self.partner_edit_view,
        ]:
            self.stacked_widget.addWidget(view)

        body_layout.addWidget(self.stacked_widget, 1)  # stretch=1: kitölti a fennmaradó helyet
        main_layout.addWidget(body, 1)

        # Kezdőlap „Gyors műveletek" kártyák → navigáció bekötése.
        # HomeView.navigate_to Signal-t bocsát ki kártyára kattintáskor;
        # az _action_map köti össze a string-kulcsokat a nézettel és sidebar-gombbal.
        #
        # _nav_buttons index-térkép (a _build_sidebar() add() hívásainak sorrendje):
        #   0  Kezdőlap
        #   1  Bank › Lekérdezés
        #   2  Bank › Importálás              ← bank_import
        #   3  Szállító › Lekérdezés
        #   4  Szállító › Importálás (.XLSX)  ← vendor_import
        #   5  Vevő › Lekérdezés
        #   6  Vevő › Importálás (.XLSX)      ← customer_import
        #   7  Bankszámlaszám
        #   8  Bank belső kód
        #   9  Partnerek
        self._action_map = {
            "bank_import": (self.bank_import_view, self._nav_buttons[2]),
            "vendor_import": (self.vendor_excel_import_view, self._nav_buttons[4]),
            "customer_import": (self.customer_excel_import_view, self._nav_buttons[6]),
        }
        self.home_view.navigate_to.connect(self._handle_home_navigate)

        # Kezdőlap legyen az alapértelmezetten aktív nézet
        self._navigate(self.home_view, self._nav_buttons[0])

    # ------------------------------------------------------------------ #
    #  Fejlécsáv                                                           #
    # ------------------------------------------------------------------ #

    def _build_header(self) -> QWidget:
        """Felépíti a sötét fejlécsávot (40px magas, teljes szélességű).

        Jelenleg csak a verziószámot tartalmazza jobb oldalon.
        Az alkalmazásnév feliratos label ki van kommentelve.
        """
        header = QWidget()
        header.setObjectName("app_header")
        header.setFixedHeight(40)
        # objectName-alapú selector: csak ezt a widgetet stílozza, a gyermekeket nem
        header.setStyleSheet(f"QWidget#app_header {{ background: {_HEADER_BG}; }}")

        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 0, 16, 0)

        # Alkalmazásnév felirat — kikommentelve (fejléc egyszerűsítés)
        # title = QLabel("■  SPP Adatfeldolgozó")
        # title.setObjectName("header_title")
        # title.setStyleSheet(
        #     "color: white; font-size: 13px; font-weight: 600; background: transparent;"
        # )
        # layout.addWidget(title)
        layout.addStretch()   # verziót jobb oldalra tolja

        # Verziószám — jobb oldalon, halvány szürke szöveg
        version = QLabel("v0.1")
        version.setObjectName("header_version")
        version.setStyleSheet(
            f"color: {_SIDEBAR_SECTION}; font-size: 12px; background: transparent;"
        )
        layout.addWidget(version)

        return header

    # ------------------------------------------------------------------ #
    #  Sidebar                                                             #
    # ------------------------------------------------------------------ #

    def _build_sidebar(self) -> QWidget:
        """Felépíti a bal oldali navigációs sávot (210px széles, sötét háttér).

        A sidebar szekciókból áll: Kezdőlap, BANK, SZÁLLÍTÓ, VEVŐ, BEÁLLÍTÁSOK.
        Minden szekció szekciócímkéből (kis nagybetűs felirat) és nav gombokból áll.
        Alul kilépés gomb van.

        Az add() belső segédfüggvény létrehozza a nav gombot, beköteli a kattintást,
        és hozzáadja az önfenntartó _nav_buttons listához (az index-alapú hivatkozáshoz).
        """
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(_SIDEBAR_WIDTH)
        sidebar.setStyleSheet(f"QWidget#sidebar {{ background: {_SIDEBAR_BG}; }}")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(2)

        def add(label: str, view: QWidget) -> None:
            """Nav gomb létrehozása, bekötése és hozzáadása a listához.

            A lambda-ban a `btn` helyi változó kötésre kerül (closure),
            így minden gombnak saját referenciája van a kattintáskezelőben.
            """
            btn = self._make_nav_button(label)
            btn.clicked.connect(lambda: self._navigate(view, btn))
            layout.addWidget(btn)
            self._nav_buttons.append(btn)

        # Kezdőlap (index 0)
        add("  Kezdőlap", self.home_view)

        layout.addSpacing(8)  # vizuális elválasztó a szekciók között

        # BANK szekció (index 1-2)
        layout.addWidget(self._make_section_label("BANK"))
        add("  Lekérdezés", self.bank_query_view)      # index 1
        add("  Importálás", self.bank_import_view)      # index 2

        layout.addSpacing(8)

        # SZÁLLÍTÓ szekció (index 3-4)
        layout.addWidget(self._make_section_label("SZÁLLÍTÓ"))
        add("  Lekérdezés", self.vendor_query_view)                    # index 3
        # add("  Importálás (.XLS)", self.vendor_import_view)           # kikommentelve (legacy)
        add("  Importálás (.XLSX)", self.vendor_excel_import_view)     # index 4

        layout.addSpacing(8)

        # VEVŐ szekció (index 5-6)
        layout.addWidget(self._make_section_label("VEVŐ"))
        add("  Lekérdezés", self.customer_query_view)                  # index 5
        # add("  Importálás (.XLS)", self.customer_import_view)         # kikommentelve (legacy)
        add("  Importálás (.XLSX)", self.customer_excel_import_view)   # index 6

        layout.addSpacing(8)

        # BEÁLLÍTÁSOK szekció (index 7-9)
        layout.addWidget(self._make_section_label("BEÁLLÍTÁSOK"))
        add("  Bankszámlaszám", self.bank_account_number_edit_view)    # index 7
        add("  Bank belső kód", self.bank_internal_code_edit_view)     # index 8
        add("  Partnerek", self.partner_edit_view)                     # index 9

        layout.addStretch()   # a kilépés gombot az aljára tolja

        # Kilépés gomb — az app.quit()-ot hívja (eseményhurok leállítása = alkalmazás bezárása)
        exit_btn = QPushButton("  Kilépés")
        exit_btn.setFlat(True)
        exit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        exit_btn.setFixedHeight(36)
        exit_btn.setStyleSheet(
            f"""
            QPushButton {{
                color: {_SIDEBAR_SECTION};
                background: transparent;
                border: none;
                text-align: left;
                padding-left: 20px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                color: {_SIDEBAR_TEXT};
                background: rgba(255, 255, 255, 0.05);
            }}
            """
        )
        exit_btn.clicked.connect(self.app.quit)
        layout.addWidget(exit_btn)

        return sidebar

    # ------------------------------------------------------------------ #
    #  Segédmetódusok                                                      #
    # ------------------------------------------------------------------ #

    def _make_section_label(self, text: str) -> QLabel:
        """Szekciócímke (pl. 'BANK', 'SZÁLLÍTÓ') — kis nagybetűs, szürke felirat."""
        label = QLabel(text)
        label.setObjectName("sidebar_section")
        label.setFixedHeight(24)
        label.setStyleSheet(
            f"color: {_SIDEBAR_SECTION}; font-size: 10px; font-weight: 600; "
            f"padding-left: 20px; background: transparent;"
        )
        return label

    def _make_nav_button(self, text: str) -> QPushButton:
        """Nav gomb létrehozása alapstílussal (inaktív állapot)."""
        btn = QPushButton(text)
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(36)
        self._apply_inactive_style(btn)
        return btn

    def _apply_active_style(self, btn: QPushButton) -> None:
        """Aktív nav gomb stílusa: fehér szöveg, kék bal szegély, sötét kék háttér."""
        btn.setStyleSheet(
            f"""
            QPushButton {{
                color: white;
                background: {_SIDEBAR_ACTIVE_BG};
                border: none;
                border-left: 3px solid {_SIDEBAR_ACTIVE_BORDER};
                text-align: left;
                padding-left: 17px;
                font-size: 13px;
            }}
            """
        )

    def _apply_inactive_style(self, btn: QPushButton) -> None:
        """Inaktív nav gomb stílusa: halvány szöveg, átlátszó háttér, hover hatás."""
        btn.setStyleSheet(
            f"""
            QPushButton {{
                color: {_SIDEBAR_TEXT};
                background: transparent;
                border: none;
                border-left: 3px solid transparent;
                text-align: left;
                padding-left: 17px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                color: white;
                background: rgba(255, 255, 255, 0.05);
            }}
            """
        )

    def _navigate(self, view: QWidget, button: QPushButton) -> None:
        """Nézet- és gombváltás kezelése.

        1. A QStackedWidget a kért nézetre vált (currentWidget változik)
        2. Az előző aktív gomb visszakap inaktív stílust
        3. Az új gomb aktív stílust kap
        4. Az _active_button referencia frissül

        Ez a metódus minden navigáció (sidebar kattintás és HomeView kártyák) esetén hívódik.
        """
        self.stacked_widget.setCurrentWidget(view)
        if self._active_button and self._active_button is not button:
            self._apply_inactive_style(self._active_button)
        self._apply_active_style(button)
        self._active_button = button

    def _handle_home_navigate(self, action: str) -> None:
        """Kezdőlap kártyáiról érkező navigáció kezelése.

        A HomeView navigate_to Signal string értéket bocsát ki (pl. "bank_import").
        Az _action_map tartalmazza a string → (nézet, gomb) leképezést.
        """
        if action in self._action_map:
            view, btn = self._action_map[action]
            self._navigate(view, btn)

    def quit_app(self) -> None:
        """Kilépés az alkalmazásból (az eseményhurok leállításával)."""
        self.app.quit()
