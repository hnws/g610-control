"""The on-screen keyboard: shows live brightness and lets keys be picked."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from .. import keys as K
from . import theme

_PAD = 0.45  # chassis padding around the keys, in key units


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(round(a.red() + (b.red() - a.red()) * t),
                  round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t))


class KeyboardView(QWidget):
    selectionChanged = Signal()
    markedChanged = Signal()

    SELECT, TOGGLE, VIEW = "select", "toggle", "view"

    def __init__(self, mode: str = "select", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.keys: list[K.Key] = K.LAYOUTS["ansi"]
        self.levels: dict[str, int] = {}
        self.selected: set[str] = set()
        self.marked: set[str] = set()       # toggle mode: keys switched off in game mode
        self._hover: str | None = None
        self._press: QPointF | None = None
        self._press_key: str | None = None
        self._band: QRectF | None = None
        self._band_base: set[str] = set()
        self.setMouseTracking(True)
        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setMinimumSize(640, 240)
        self.setFocusPolicy(Qt.ClickFocus)

    def sizeHint(self) -> QSize:
        return QSize(980, 360)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return round(width * (K.HEIGHT + 2 * _PAD) / (K.WIDTH + 2 * _PAD))

    # -- data --------------------------------------------------------------

    def set_keys(self, keys: list[K.Key]) -> None:
        self.keys = keys
        names = {k.name for k in keys}
        self.selected &= names
        self.update()

    def set_levels(self, levels: dict[str, int]) -> None:
        self.levels = levels
        self.update()

    def set_selection(self, names) -> None:
        names = set(names) & {k.name for k in self.keys}
        if names != self.selected:
            self.selected = names
            self.selectionChanged.emit()
            self.update()

    def set_marked(self, names) -> None:
        self.marked = set(names)
        self.update()

    # -- geometry ----------------------------------------------------------

    def _unit(self) -> tuple[float, float, float]:
        u = min(self.width() / (K.WIDTH + 2 * _PAD), self.height() / (K.HEIGHT + 2 * _PAD))
        ox = (self.width() - K.WIDTH * u) / 2
        oy = (self.height() - K.HEIGHT * u) / 2 - K.TOP_Y * u
        return u, ox, oy

    def _rect(self, key: K.Key) -> QRectF:
        u, ox, oy = self._unit()
        gap = u * 0.055
        return QRectF(ox + key.x * u + gap, oy + key.y * u + gap,
                      key.w * u - 2 * gap, key.h * u - 2 * gap)

    def _key_at(self, pos: QPointF) -> str | None:
        for key in self.keys:
            if self._rect(key).contains(pos):
                return key.name
        return None

    # -- painting ----------------------------------------------------------

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        u, ox, oy = self._unit()

        body = QRectF(ox - _PAD * u, oy + (K.TOP_Y - _PAD) * u,
                      (K.WIDTH + 2 * _PAD) * u, (K.HEIGHT + 2 * _PAD) * u).adjusted(1, 1, -1, -1)
        grad = QLinearGradient(body.topLeft(), body.bottomLeft())
        grad.setColorAt(0, QColor("#1b1e26"))
        grad.setColorAt(1, QColor("#111318"))
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.setBrush(grad)
        p.drawRoundedRect(body, u * 0.35, u * 0.35)

        cap_off, cap_on = QColor("#20232b"), QColor("#454a57")
        ink_off, ink_on = QColor("#555b69"), QColor("#ffffff")
        accent, danger = QColor(theme.ACCENT), QColor(theme.DANGER)
        font = QFont(self.font())

        for key in self.keys:
            rect = self._rect(key)
            level = self.levels.get(key.name, 0) / 255
            marked = key.name in self.marked
            selected = key.name in self.selected
            radius = u * 0.13

            if key.shape == "led":
                dot = u * 0.26
                led = QRectF(rect.center().x() - dot / 2, rect.top() + u * 0.2, dot, dot)
                if level > 0.02:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(255, 255, 255, round(70 * level)))
                    p.drawEllipse(led.adjusted(-dot * 0.35, -dot * 0.35, dot * 0.35, dot * 0.35))
                p.setPen(QPen(accent, 2) if selected else Qt.NoPen)
                p.setBrush(_mix(QColor("#2a2e38"), ink_on, level))
                p.drawEllipse(led)
                font.setPixelSize(max(6, round(u * 0.2)))
                p.setFont(font)
                p.setPen(_mix(ink_off, QColor("#c9cdd6"), level))
                p.drawText(QRectF(rect.left() - u * 0.2, led.bottom() + u * 0.05, rect.width() + u * 0.4, u * 0.32),
                           Qt.AlignHCenter | Qt.AlignTop, key.label)
                continue

            if key.shape == "round":
                side = min(rect.width(), rect.height()) * 0.86
                rect = QRectF(rect.center().x() - side / 2, rect.center().y() - side / 2, side, side)
                radius = side / 2

            if level > 0.02:  # light spilling around the keycap
                p.setPen(Qt.NoPen)
                spill = u * 0.07
                p.setBrush(QColor(255, 255, 255, round(55 * level)))
                p.drawRoundedRect(rect.adjusted(-spill, -spill, spill, spill), radius + spill, radius + spill)

            fill = _mix(cap_off, cap_on, level)
            if marked:
                fill = _mix(fill, danger, 0.45)
            elif selected:
                fill = _mix(fill, accent, 0.28)
            if selected:
                pen = QPen(accent, max(1.5, u * 0.05))
            elif marked:
                pen = QPen(danger, max(1.2, u * 0.04))
            elif key.name == self._hover and self.mode != self.VIEW:
                pen = QPen(QColor("#7d8596"), 1.2)
            else:
                pen = QPen(QColor("#0b0c10"), 1)
            p.setPen(pen)
            p.setBrush(fill)
            p.drawRoundedRect(rect, radius, radius)

            if key.label:
                long_label = len(key.label) > 1
                size = u * (0.2 if len(key.label) > 5 else 0.23 if long_label else 0.34)
                font.setPixelSize(max(6, round(size)))
                font.setBold(not long_label)
                p.setFont(font)
                p.setPen(_mix(ink_off, ink_on, level) if not marked else QColor("#ffd9de"))
                p.drawText(rect, Qt.AlignCenter, key.label)
            if marked:
                p.setPen(QPen(danger, max(1.5, u * 0.05)))
                inset = min(rect.width(), rect.height()) * 0.22
                p.drawLine(rect.bottomLeft() + QPointF(inset, -inset), rect.topRight() + QPointF(-inset, inset))

        if self._band is not None:
            p.setPen(QPen(accent, 1))
            p.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 40))
            p.drawRect(self._band)

    # -- interaction -------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self.mode == self.VIEW:
            return
        pos = event.position()
        name = self._key_at(pos)
        if self.mode == self.TOGGLE:
            if name and K.ALL_KEYS[name].usage is not None:
                self.marked ^= {name}
                self.markedChanged.emit()
                self.update()
            return
        additive = bool(event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier))
        self._press, self._press_key = pos, name
        self._band_base = set(self.selected) if additive else set()
        if name and additive:
            self.set_selection(self.selected ^ {name})
            self._band_base = set(self.selected)
        elif name:
            self.set_selection({name})
        elif not additive:
            self.set_selection(set())

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        if self._press is not None and self.mode == self.SELECT:
            if self._band is None and (pos - self._press).manhattanLength() < 6:
                return
            self._band = QRectF(self._press, pos).normalized()
            hit = {k.name for k in self.keys if self._rect(k).intersects(self._band)}
            self.set_selection(self._band_base | hit)
            self.update()
            return
        name = self._key_at(pos)
        if name != self._hover:
            self._hover = name
            self.update()
            if name and self.mode != self.VIEW:
                key = K.ALL_KEYS[name]
                tip = f"{name.replace('_', ' ')}  •  {round(self.levels.get(name, 0) / 2.55)}%"
                if self.mode == self.TOGGLE and key.usage is None:
                    tip = "This control cannot be disabled"
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
            else:
                QToolTip.hideText()

    def mouseReleaseEvent(self, _event) -> None:
        self._press = None
        if self._band is not None:
            self._band = None
            self.update()

    def mouseDoubleClickEvent(self, event) -> None:
        if self.mode != self.SELECT:
            return
        name = self._key_at(event.position())
        if name:
            zone = K.ALL_KEYS[name].zone
            self.set_selection({k.name for k in self.keys if k.zone == zone})

    def leaveEvent(self, _event) -> None:
        if self._hover is not None:
            self._hover = None
            self.update()
