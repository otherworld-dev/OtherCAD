# SPDX-License-Identifier: LGPL-2.1-or-later

"""Gwyn, the Otherworld mascot, as the AI chat panel's sign that a reply is on its way.

The drawing and the motion follow the brand's Gwyn and its "loading" mood: he climbs up
through the portal and takes hold of its rim, then glances side to side while his antenna
bobs and its light pulses. Coordinates are the brand sheet's, in a 270 x 280 box centred
on the portal; times are in ms.
"""

from PySide import QtCore, QtGui, QtWidgets

FRAME_MS = 33
VIEW = QtCore.QRectF(-135, -140, 270, 280)

INK = QtGui.QColor("#0A1118")
STAR = QtGui.QColor("#33465C")
BONE = QtGui.QColor("#F2EFE6")
TEAL = QtGui.QColor("#5EEAD4")


def cubic_bezier(x1, y1, x2, y2):
    """A CSS timing function: maps progress in [0, 1] to eased progress."""

    def coordinate(t, a, b):
        return 3 * a * (1 - t) ** 2 * t + 3 * b * (1 - t) * t**2 + t**3

    def ease(x):
        if x <= 0 or x >= 1:
            return min(max(x, 0.0), 1.0)
        t = x
        for _ in range(8):
            error = coordinate(t, x1, x2) - x
            slope = 3 * x1 * (1 - t) ** 2 + 6 * (x2 - x1) * (1 - t) * t + 3 * (1 - x2) * t**2
            if abs(error) < 1e-5 or slope == 0:
                break
            t = min(max(t - error / slope, 0.0), 1.0)
        return coordinate(t, y1, y2)

    return ease


EASE_IN_OUT = cubic_bezier(0.42, 0, 0.58, 1)
EASE_OUT = cubic_bezier(0, 0, 0.58, 1)
RISE = cubic_bezier(0.2, 0.8, 0.3, 1.15)


def keyframes(frames, progress):
    """The value at progress in [0, 1] through (offset, value) stops, eased in and out."""

    for (start, a), (end, b) in zip(frames, frames[1:]):
        if progress <= end:
            span = end - start
            return a + (b - a) * EASE_IN_OUT((progress - start) / span if span else 1.0)
    return frames[-1][1]


GLANCE = [(0, 0), (0.12, 0), (0.22, -7), (0.42, -7), (0.58, 7), (0.78, 7), (0.88, 0), (1, 0)]
PULSE_OPACITY = [(0, 0.2), (0.5, 0.7), (1, 0.2)]
PULSE_SCALE = [(0, 1.0), (0.5, 1.5), (1, 1.0)]


def pose(ms):
    """Where everything is ms after he starts to climb out."""

    rise = 1.0 - RISE(min(ms / 700.0, 1.0))
    grab = EASE_OUT(min(max((ms - 520) / 260.0, 0.0), 1.0))
    glance = 0.0
    if ms >= 900:
        glance = keyframes(GLANCE, ((ms - 900) % 2800) / 2800.0)
    bob = 0.0
    if ms >= 700:
        cycle = (ms - 700) / 1600.0
        swing = cycle % 1.0 if int(cycle) % 2 == 0 else 1.0 - cycle % 1.0
        bob = -5 + 10 * EASE_IN_OUT(swing)
    pulse = (ms % 1200) / 1200.0
    return {
        "rise": 92 * rise,
        "handsOpacity": grab,
        "handsDrop": 10 * (1 - grab),
        "glance": glance,
        "bob": bob,
        "glowOpacity": keyframes(PULSE_OPACITY, pulse),
        "glowScale": keyframes(PULSE_SCALE, pulse),
    }


class GwynWidget(QtWidgets.QWidget):
    """Gwyn climbing out of his portal, animated while start() is in effect."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.clock = QtCore.QElapsedTimer()
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(FRAME_MS)
        self.timer.timeout.connect(self.update)
        self.ms = None  # fixed time for tests and stills; None follows the clock

    def sizeHint(self):
        return QtCore.QSize(40, 42)

    def start(self):
        self.clock.start()
        self.timer.start()
        self.update()

    def stop(self):
        self.timer.stop()

    def isAnimating(self):
        return self.timer.isActive()

    def elapsed(self):
        if self.ms is not None:
            return self.ms
        return self.clock.elapsed() if self.clock.isValid() else 10000

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        scale = min(self.width() / VIEW.width(), self.height() / VIEW.height())
        painter.translate(self.width() / 2.0, self.height() / 2.0)
        painter.scale(scale, scale)
        paint(painter, pose(self.elapsed()))
        painter.end()


def _ellipse(painter, cx, cy, rx, ry):
    painter.drawEllipse(QtCore.QPointF(cx, cy), rx, ry)


def paint(painter, p):
    """Draw Gwyn in pose p, centred on the origin in brand units."""

    painter.setPen(QtCore.Qt.NoPen)

    # The portal and the stars beyond it
    painter.setBrush(INK)
    _ellipse(painter, 0, 0, 104, 122)
    painter.setBrush(STAR)
    _ellipse(painter, -30, -64, 2.4, 2.4)
    _ellipse(painter, 34, -30, 1.8, 1.8)
    _ellipse(painter, -12, -8, 1.5, 1.5)

    # Gwyn himself, clipped to the portal so he rises out of it
    painter.save()
    clip = QtGui.QPainterPath()
    clip.addEllipse(QtCore.QPointF(0, 0), 99, 117)
    painter.setClipPath(clip)
    painter.translate(0, p["rise"])

    # The antenna turns about its base
    painter.save()
    painter.translate(2, 16)
    painter.rotate(p["bob"])
    painter.translate(-2, -16)
    stalk = QtGui.QPainterPath(QtCore.QPointF(2, 16))
    stalk.quadTo(-2, -22, -30, -32)
    painter.setPen(QtGui.QPen(BONE, 6, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
    painter.setBrush(QtCore.Qt.NoBrush)
    painter.drawPath(stalk)
    painter.setPen(QtCore.Qt.NoPen)
    glow = QtGui.QColor(TEAL)
    glow.setAlphaF(p["glowOpacity"])
    painter.setBrush(glow)
    radius = 13 * p["glowScale"]
    _ellipse(painter, -34, -34, radius, radius)
    painter.setBrush(TEAL)
    _ellipse(painter, -34, -34, 9, 9)
    painter.restore()

    body = QtGui.QRadialGradient(QtCore.QPointF(4 - 88 + 0.4 * 176, 102 - 88 + 0.28 * 176), 176)
    body.setColorAt(0, QtGui.QColor("#FFFFFF"))
    body.setColorAt(0.62, BONE)
    body.setColorAt(1, QtGui.QColor("#CFD8D2"))
    painter.setBrush(body)
    _ellipse(painter, 4, 102, 88, 88)

    painter.save()
    painter.translate(p["glance"], 0)
    painter.setBrush(INK)
    _ellipse(painter, -18, 52, 11, 15.5)
    _ellipse(painter, 28, 52, 11, 15.5)
    painter.setBrush(QtGui.QColor("#FFFFFF"))
    _ellipse(painter, -14.3, 46, 3.7, 3.7)
    _ellipse(painter, 31.7, 46, 3.7, 3.7)
    painter.restore()

    mouth = QtGui.QPainterPath(QtCore.QPointF(-2, 76))
    mouth.quadTo(5, 83, 12, 76)
    painter.setPen(QtGui.QPen(INK, 5.2, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
    painter.setBrush(QtCore.Qt.NoBrush)
    painter.drawPath(mouth)
    painter.restore()

    # The portal ring
    painter.setBrush(QtCore.Qt.NoBrush)
    halo = QtGui.QColor(TEAL)
    halo.setAlphaF(0.16)
    painter.setPen(QtGui.QPen(halo, 24))
    _ellipse(painter, 0, 0, 104, 122)
    painter.setPen(QtGui.QPen(TEAL, 10))
    _ellipse(painter, 0, 0, 104, 122)

    # His hands on the rim
    if p["handsOpacity"] > 0:
        painter.save()
        painter.setOpacity(p["handsOpacity"])
        painter.translate(0, p["handsDrop"])
        painter.setPen(QtGui.QPen(INK, 2.5))
        painter.setBrush(BONE)
        for cx, cy, angle in ((-58, 96, 30), (66, 90, -32)):
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(angle)
            _ellipse(painter, 0, 0, 16.5, 12.5)
            painter.restore()
        painter.restore()


def still(size=128, ms=10000):
    """Gwyn ms into his climb, as a QImage."""

    image = QtGui.QImage(size, size, QtGui.QImage.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.transparent)
    widget = GwynWidget()
    widget.ms = ms
    widget.resize(size, size)
    widget.render(image, QtCore.QPoint(), QtGui.QRegion(), QtWidgets.QWidget.DrawChildren)
    widget.deleteLater()
    return image
