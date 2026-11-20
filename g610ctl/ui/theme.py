"""Colours and the application style sheet."""

BG = "#0e1014"
PANEL = "#161920"
PANEL_HI = "#1d212a"
BORDER = "#272c37"
TEXT = "#e7e9ee"
MUTED = "#8b93a5"
ACCENT = "#19b8f5"
ACCENT_DIM = "#0f4f6b"
DANGER = "#f0566a"
OK = "#3ddc84"

STYLE = f"""
* {{ font-size: 10pt; }}
QWidget {{ background: {BG}; color: {TEXT}; }}
QToolTip {{ background: {PANEL_HI}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px 6px; }}
QLabel {{ background: transparent; }}
QLabel[role="title"] {{ font-size: 15pt; font-weight: 600; }}
QLabel[role="heading"] {{ font-size: 11pt; font-weight: 600; }}
QLabel[role="muted"] {{ color: {MUTED}; }}
QLabel[role="caption"] {{ color: {MUTED}; font-size: 9pt; }}

#sidebar {{ background: {PANEL}; border-right: 1px solid {BORDER}; }}
#sidebar QLabel {{ background: transparent; }}
#header {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
#header QLabel {{ background: transparent; }}
QFrame[role="card"] {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame[role="card"] QWidget {{ background: transparent; }}

QPushButton {{
    background: {PANEL_HI}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 6px 12px; color: {TEXT};
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {ACCENT_DIM}; }}
QPushButton:disabled {{ color: #565c6b; border-color: {BORDER}; }}
QPushButton[role="chip"] {{ padding: 4px 10px; border-radius: 12px; font-size: 9pt; }}
QPushButton[role="nav"] {{
    text-align: left; padding: 10px 14px; border: none; border-radius: 8px;
    background: transparent; color: {MUTED}; font-size: 11pt;
}}
QPushButton[role="nav"]:hover {{ background: {PANEL_HI}; color: {TEXT}; }}
QPushButton[role="nav"]:checked {{ background: {ACCENT_DIM}; color: {TEXT}; font-weight: 600; }}
QPushButton[role="segment"] {{ border-radius: 0; padding: 7px 18px; border-right-width: 0; }}
QPushButton[role="segment"][seg="first"] {{ border-top-left-radius: 7px; border-bottom-left-radius: 7px; }}
QPushButton[role="segment"][seg="last"] {{
    border-top-right-radius: 7px; border-bottom-right-radius: 7px; border-right-width: 1px;
}}
QPushButton[role="segment"]:checked {{ background: {ACCENT}; color: #04121a; font-weight: 600; border-color: {ACCENT}; }}
QPushButton[role="effect"] {{
    padding: 12px 10px; border-radius: 9px; min-width: 96px; font-weight: 600;
}}
QPushButton[role="effect"]:checked {{ border: 2px solid {ACCENT}; background: {ACCENT_DIM}; padding: 11px 9px; }}

QComboBox {{
    background: {PANEL_HI}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 5px 10px; min-width: 110px;
}}
QComboBox:hover {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {PANEL_HI}; border: 1px solid {BORDER}; selection-background-color: {ACCENT_DIM};
    outline: none;
}}
QMenu {{ background: {PANEL_HI}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ACCENT_DIM}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}

QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; background: {TEXT};
}}
QSlider::handle:horizontal:hover {{ background: {ACCENT}; }}
QSlider::sub-page:horizontal:disabled {{ background: #3a4050; }}
QSlider::handle:horizontal:disabled {{ background: #565c6b; }}

QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QLineEdit {{
    background: {PANEL_HI}; border: 1px solid {BORDER}; border-radius: 6px; padding: 5px 8px;
    selection-background-color: {ACCENT_DIM};
}}
"""
