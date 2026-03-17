# ui/main_window.py
#
# Főablak — sidebar navigáció, fejlécsáv, QStackedWidget tartalomterület.
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


# Sidebar színek
_HEADER_BG = "#151929"
_SIDEBAR_BG = "#1e2130"
_SIDEBAR_ACTIVE_BG = "#2a3150"
_SIDEBAR_ACTIVE_BORDER = "#3b5bdb"
_SIDEBAR_TEXT = "#c9d1d9"
_SIDEBAR_SECTION = "#6e7891"
_SIDEBAR_WIDTH = 210


class MainWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._nav_buttons: list[QPushButton] = []
        self._active_button: QPushButton | None = None

        self.setWindowTitle("BPiON - GUI")
        self.setMinimumSize(1200, 650)

        # QMenuBar elrejtése — sidebar váltja ki
        self.menuBar().hide()

        # Nézetek létrehozása
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

        # Főwidget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Fejlécsáv (teljes szélességben, sötét)
        main_layout.addWidget(self._build_header())

        # Törzs: sidebar + tartalomterület
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        body_layout.addWidget(self._build_sidebar())

        # QStackedWidget — tartalomterület
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

        body_layout.addWidget(self.stacked_widget, 1)
        main_layout.addWidget(body, 1)

        # Kezdőlap „Gyors műveletek" kártyák → navigáció bekötése.
        # HomeView.navigate_to Signal-t bocsát ki; itt kötjük az egyes
        # action-stringeket a megfelelő nézethez és sidebar-gombhoz.
        #
        # _nav_buttons index-térkép (a _build_sidebar() sorrendje alapján):
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

        # Kezdőlap aktív alapértelmezetten
        self._navigate(self.home_view, self._nav_buttons[0])

    # ------------------------------------------------------------------ #
    #  Fejlécsáv                                                           #
    # ------------------------------------------------------------------ #

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("app_header")
        header.setFixedHeight(40)
        header.setStyleSheet(f"QWidget#app_header {{ background: {_HEADER_BG}; }}")

        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 0, 16, 0)

        title = QLabel("■  SPP Adatfeldolgozó")
        title.setObjectName("header_title")
        title.setStyleSheet(
            "color: white; font-size: 13px; font-weight: 600; background: transparent;"
        )
        layout.addWidget(title)
        layout.addStretch()

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
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(_SIDEBAR_WIDTH)
        sidebar.setStyleSheet(f"QWidget#sidebar {{ background: {_SIDEBAR_BG}; }}")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(2)

        def add(label: str, view: QWidget) -> None:
            btn = self._make_nav_button(label)
            btn.clicked.connect(lambda: self._navigate(view, btn))
            layout.addWidget(btn)
            self._nav_buttons.append(btn)

        # Kezdőlap
        add("  Kezdőlap", self.home_view)

        layout.addSpacing(8)

        # BANK
        layout.addWidget(self._make_section_label("BANK"))
        add("  Lekérdezés", self.bank_query_view)
        add("  Importálás", self.bank_import_view)

        layout.addSpacing(8)

        # SZÁLLÍTÓ
        layout.addWidget(self._make_section_label("SZÁLLÍTÓ"))
        add("  Lekérdezés", self.vendor_query_view)
        # add("  Importálás (.XLS)", self.vendor_import_view)
        add("  Importálás (.XLSX)", self.vendor_excel_import_view)

        layout.addSpacing(8)

        # VEVŐ
        layout.addWidget(self._make_section_label("VEVŐ"))
        add("  Lekérdezés", self.customer_query_view)
        # add("  Importálás (.XLS)", self.customer_import_view)
        add("  Importálás (.XLSX)", self.customer_excel_import_view)

        layout.addSpacing(8)

        # BEÁLLÍTÁSOK
        layout.addWidget(self._make_section_label("BEÁLLÍTÁSOK"))
        add("  Bankszámlaszám", self.bank_account_number_edit_view)
        add("  Bank belső kód", self.bank_internal_code_edit_view)
        add("  Partnerek", self.partner_edit_view)

        layout.addStretch()

        # Kilépés gomb
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
        label = QLabel(text)
        label.setObjectName("sidebar_section")
        label.setFixedHeight(24)
        label.setStyleSheet(
            f"color: {_SIDEBAR_SECTION}; font-size: 10px; font-weight: 600; "
            f"padding-left: 20px; background: transparent;"
        )
        return label

    def _make_nav_button(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(36)
        self._apply_inactive_style(btn)
        return btn

    def _apply_active_style(self, btn: QPushButton) -> None:
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
        self.stacked_widget.setCurrentWidget(view)
        if self._active_button and self._active_button is not button:
            self._apply_inactive_style(self._active_button)
        self._apply_active_style(button)
        self._active_button = button

    def _handle_home_navigate(self, action: str) -> None:
        """Kezdőlap kártyáiról érkező navigáció kezelése."""
        if action in self._action_map:
            view, btn = self._action_map[action]
            self._navigate(view, btn)

    def quit_app(self) -> None:
        """Kilépés az alkalmazásból."""
        self.app.quit()
