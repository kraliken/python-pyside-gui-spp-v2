# ui/icons.py
#
# Közös SVG ikon helper — Feather Icons stílusú outline ikonok.
# Használat: set_button_icon(btn, ICON_SEARCH, CLR_PRIMARY, CLR_PRIMARY_DIS)

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

# ------------------------------------------------------------------ #
#  Gomb ikon színek — QSS-sel szinkronban
# ------------------------------------------------------------------ #

CLR_PRIMARY      = "white"     # kék (primary) gomb — normál
CLR_PRIMARY_DIS  = "#e9ecef"   # kék (primary) gomb — disabled

CLR_SECONDARY     = "#495057"  # szürke keret (secondary) gomb — normál
CLR_SECONDARY_DIS = "#adb5bd"  # szürke keret (secondary) gomb — disabled

CLR_DANGER      = "#e03131"    # piros keret (delete/clear) gomb — normál
CLR_DANGER_DIS  = "#ffa8a8"    # piros keret (delete/clear) gomb — disabled

# ------------------------------------------------------------------ #
#  SVG stringek
# ------------------------------------------------------------------ #

ICON_UPLOAD = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
     fill="none" stroke="{c}" stroke-width="2"
     stroke-linecap="round" stroke-linejoin="round">
  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
  <polyline points="17 8 12 3 7 8"/>
  <line x1="12" y1="3" x2="12" y2="15"/>
</svg>
"""

ICON_SEARCH = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
     fill="none" stroke="{c}" stroke-width="2"
     stroke-linecap="round" stroke-linejoin="round">
  <circle cx="11" cy="11" r="8"/>
  <line x1="21" y1="21" x2="16.65" y2="16.65"/>
</svg>
"""

ICON_HISTORY = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
     fill="none" stroke="{c}" stroke-width="2"
     stroke-linecap="round" stroke-linejoin="round">
  <polyline points="1 4 1 10 7 10"/>
  <path d="M3.51 15a9 9 0 1 0 .49-4.95"/>
  <polyline points="12 7 12 12 15 14"/>
</svg>
"""

ICON_TRASH = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
     fill="none" stroke="{c}" stroke-width="2"
     stroke-linecap="round" stroke-linejoin="round">
  <polyline points="3 6 5 6 21 6"/>
  <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
  <path d="M10 11v6"/>
  <path d="M14 11v6"/>
  <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
</svg>
"""

ICON_SAVE = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
     fill="none" stroke="{c}" stroke-width="2"
     stroke-linecap="round" stroke-linejoin="round">
  <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
  <polyline points="17 21 17 13 7 13 7 21"/>
  <polyline points="7 3 7 8 15 8"/>
</svg>
"""

ICON_CHECK_CIRCLE = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
     fill="none" stroke="{c}" stroke-width="2"
     stroke-linecap="round" stroke-linejoin="round">
  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
  <polyline points="22 4 12 14.01 9 11.01"/>
</svg>
"""

ICON_DOWNLOAD = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
     fill="none" stroke="{c}" stroke-width="2"
     stroke-linecap="round" stroke-linejoin="round">
  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
  <polyline points="7 10 12 15 17 10"/>
  <line x1="12" y1="15" x2="12" y2="3"/>
</svg>
"""

ICON_PLUS = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
     fill="none" stroke="{c}" stroke-width="2"
     stroke-linecap="round" stroke-linejoin="round">
  <line x1="12" y1="5" x2="12" y2="19"/>
  <line x1="5" y1="12" x2="19" y2="12"/>
</svg>
"""

ICON_EDIT = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
     fill="none" stroke="{c}" stroke-width="2"
     stroke-linecap="round" stroke-linejoin="round">
  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
</svg>
"""

# ------------------------------------------------------------------ #
#  Helper
# ------------------------------------------------------------------ #

def _make_pixmap(svg_template: str, size: int, color: str) -> QPixmap:
    data = QByteArray(svg_template.replace("{c}", color).encode("utf-8"))
    renderer = QSvgRenderer(data)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def make_icon(
    svg_template: str,
    size: int,
    color: str,
    disabled_color: str | None = None,
) -> QIcon:
    """SVG string → multi-state QIcon.

    Ha disabled_color meg van adva, a QIcon.Mode.Disabled állapothoz
    külön pixmap kerül — így a disabled gomb ikonja illeszkedik a
    szöveg halfaded színéhez.
    """
    icon = QIcon()
    icon.addPixmap(_make_pixmap(svg_template, size, color), QIcon.Mode.Normal)
    if disabled_color:
        icon.addPixmap(
            _make_pixmap(svg_template, size, disabled_color), QIcon.Mode.Disabled
        )
    return icon


def set_button_icon(
    button,
    svg_template: str,
    color: str,
    disabled_color: str | None = None,
    size: int = 16,
) -> None:
    """Ikont és szóközt állít be egy QPushButton-ra.

    color          — normál állapot ikon színe
    disabled_color — disabled állapot ikon színe (None → Qt auto-fade)
    """
    button.setIcon(make_icon(svg_template, size, color, disabled_color))
    button.setIconSize(QSize(size, size))
    if not button.text().startswith("  "):
        button.setText("  " + button.text())
