"""Small reusable widgets."""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QSlider, QVBoxLayout, QWidget)

from . import theme


def label(text: str, role: str | None = None, wrap: bool = False) -> QLabel:
    w = QLabel(text)
    if role:
        w.setProperty("role", role)
    w.setWordWrap(wrap)
    return w


def card(*, margins: int = 16, spacing: int = 12) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setProperty("role", "card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(margins, margins, margins, margins)
    layout.setSpacing(spacing)
    return frame, layout


def chip(text: str, tip: str = "") -> QPushButton:
    button = QPushButton(text)
    button.setProperty("role", "chip")
    button.setCursor(Qt.PointingHandCursor)
    if tip:
        button.setToolTip(tip)
    return button


class Switch(QAbstractButton):
    """An on/off toggle."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(120)
        self._anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.toggled.connect(self._slide)

    def sizeHint(self) -> QSize:
        return QSize(42, 24)

    def _slide(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def setChecked(self, on: bool) -> None:  # no animation for programmatic changes
        blocked = self.signalsBlocked()
        super().setChecked(on)
        if blocked:
            self._pos = 1.0 if on else 0.0
            self.update()

    def _get_knob(self) -> float:
        return self._pos

    def _set_knob(self, value: float) -> None:
        self._pos = value
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        off, on = QColor(theme.BORDER), QColor(theme.ACCENT)
        mix = QColor(
            round(off.red() + (on.red() - off.red()) * self._pos),
            round(off.green() + (on.green() - off.green()) * self._pos),
            round(off.blue() + (on.blue() - off.blue()) * self._pos))
        if not self.isEnabled():
            mix = QColor("#2a2e38")
        p.setPen(Qt.NoPen)
        p.setBrush(mix)
        p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        d = rect.height() - 6
        x = rect.left() + 3 + (rect.width() - d - 6) * self._pos
        p.setBrush(QColor(theme.TEXT if self.isEnabled() else "#6b7180"))
        p.drawEllipse(QRectF(x, rect.top() + 3, d, d))


class Segmented(QWidget):
    """A row of mutually exclusive buttons."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._group = QButtonGroup(self)
        self._buttons: dict[str, QPushButton] = {}
        for i, (value, text) in enumerate(options):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setProperty("role", "segment")
            if i == 0:
                button.setProperty("seg", "first")
            elif i == len(options) - 1:
                button.setProperty("seg", "last")
            self._group.addButton(button)
            self._buttons[value] = button
            layout.addWidget(button)
            button.clicked.connect(lambda _=False, v=value: self.changed.emit(v))
        layout.addStretch(1)

    def set_value(self, value: str) -> None:
        if value in self._buttons:
            self._buttons[value].setChecked(True)

    def value(self) -> str:
        for value, button in self._buttons.items():
            if button.isChecked():
                return value
        return ""


class LabeledSlider(QWidget):
    """Caption, slider and a formatted value on one row."""

    changed = Signal(int)

    def __init__(self, caption: str, lo: int, hi: int, fmt=lambda v: str(v),
                 ends: tuple[str, str] | None = None, parent=None):
        super().__init__(parent)
        self._fmt = fmt
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.caption = label(caption)
        self.caption.setMinimumWidth(110)
        layout.addWidget(self.caption)
        if ends:
            layout.addWidget(label(ends[0], "caption"))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(lo, hi)
        self.slider.setPageStep(max(1, (hi - lo) // 10))
        layout.addWidget(self.slider, 1)
        if ends:
            layout.addWidget(label(ends[1], "caption"))
        self.value_label = label("", "muted")
        self.value_label.setMinimumWidth(52)
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.value_label)
        self.slider.valueChanged.connect(self._on_change)
        self._on_change(self.slider.value(), emit=False)

    def _on_change(self, value: int, emit: bool = True) -> None:
        self.value_label.setText(self._fmt(value))
        if emit:
            self.changed.emit(value)

    def set_value(self, value: int) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(int(value))
        self.slider.blockSignals(False)
        self.value_label.setText(self._fmt(self.slider.value()))

    def value(self) -> int:
        return self.slider.value()
