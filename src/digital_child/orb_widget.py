from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from digital_child.face_state import FaceState
from digital_child.orb_state import OrbDynamics


class OrbWidget(QWidget):
    """Projected, translucent shells rendered without a GPU or external assets."""

    def __init__(self, parent: QWidget | None = None, *, fps: int = 60) -> None:
        super().__init__(parent)
        self.setMinimumSize(280, 260)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setAccessibleName("Эмоциональная сфера Digital Child")
        self.state = FaceState()
        self.dynamics = OrbDynamics.from_face(self.state)
        self.target = self.dynamics
        self.phase = 0.0
        self.elapsed = 0.0
        self.last_frame = time.monotonic()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(round(1000 / max(24, min(120, fps))))

    def set_state(self, state: FaceState) -> None:
        self.state = state
        self.target = OrbDynamics.from_face(state)

    def _tick(self) -> None:
        now = time.monotonic()
        dt = min(0.1, now - self.last_frame)
        self.last_frame = now
        self.dynamics = self.dynamics.approach(self.target, dt)
        self.phase += dt * self.dynamics.speed
        self.elapsed += dt
        if self.isVisible():
            self.update()

    def _color(self, alpha: int = 255, *, light: float = 1.0) -> QColor:
        d = self.dynamics
        return QColor(
            min(255, max(0, round(d.red * light))),
            min(255, max(0, round(d.green * light))),
            min(255, max(0, round(d.blue * light))),
            min(255, max(0, alpha)),
        )

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0b1211"))
        w, h = float(self.width()), float(self.height())
        radius = min(w * 0.39, h * 0.43)
        t, d = self.elapsed, self.dynamics
        breath = 1 + d.pulse * math.sin(t * (1.25 + d.speech * 5))
        painter.translate(w / 2, h / 2 - 8 + 3 * math.sin(t * 0.65))

        # Ambient halo and contact shadow give the sphere depth without a hard frame.
        halo = QRadialGradient(QPointF(0, 0), radius * 1.65)
        halo.setColorAt(0, self._color(20))
        halo.setColorAt(0.57, self._color(16))
        halo.setColorAt(1, self._color(0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(QPointF(0, 0), radius * 1.65, radius * 1.65)
        shadow = QRadialGradient(QPointF(0, 0), radius * 0.85)
        shadow.setColorAt(0, self._color(27))
        shadow.setColorAt(1, self._color(0))
        painter.save()
        painter.translate(0, radius * 1.36)
        painter.scale(1, 0.14)
        painter.setBrush(shadow)
        painter.drawEllipse(QPointF(0, 0), radius, radius)
        painter.restore()
        painter.scale(breath, breath)

        glass = QRadialGradient(QPointF(-radius * 0.35, -radius * 0.4), radius * 1.6)
        glass.setColorAt(0, self._color(16, light=1.2))
        glass.setColorAt(0.6, self._color(5))
        glass.setColorAt(0.84, self._color(31))
        glass.setColorAt(1, self._color(2))
        painter.setBrush(glass)
        painter.setPen(QPen(self._color(55), 0.8))
        painter.drawEllipse(QPointF(0, 0), radius, radius)

        # Each nested shell has its own axis, velocity and response to the state.
        for layer in range(7):
            fraction = 0.43 + layer * (0.069 + d.openness * 0.009)
            shell_radius = radius * fraction
            rotation = self.phase * (0.55 + layer * 0.14) * (-1 if layer % 2 else 1)
            tilt = 0.48 + layer * 0.38 + d.curiosity * 0.22 * math.sin(rotation)
            for band in range(3):
                latitude = (band - 1) * 0.52
                self._shell(painter, shell_radius, rotation, tilt, latitude, layer)

        core = QRadialGradient(QPointF(-radius * 0.08, -radius * 0.1), radius * 0.46)
        core.setColorAt(0, QColor(221, 255, 233, round(210 * d.brightness)))
        core.setColorAt(0.14, self._color(round(174 * d.brightness), light=1.15))
        core.setColorAt(0.45, self._color(55))
        core.setColorAt(1, self._color(0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(core)
        painter.drawEllipse(QPointF(0, 0), radius * 0.46, radius * 0.46)

        # A stable inner nucleus is distinct from the agitated outer layers.
        painter.setBrush(self._color(14))
        painter.setPen(QPen(self._color(105), 0.9))
        painter.drawEllipse(QPointF(0, 0), radius * 0.21, radius * 0.21)
        self._particles(painter, radius)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        for offset, alpha in ((1.0, 42), (1.045, 17), (1.11, 10)):
            painter.setPen(QPen(self._color(alpha), 0.75))
            painter.drawEllipse(QPointF(0, 0), radius * offset, radius * offset)
        painter.end()

    def _shell(
        self,
        painter: QPainter,
        radius: float,
        rotation: float,
        tilt: float,
        latitude: float,
        layer: int,
    ) -> None:
        d = self.dynamics
        front, back = QPainterPath(), QPainterPath()
        front_active = back_active = False
        ct, st = math.cos(tilt), math.sin(tilt)
        cr, sr = math.cos(rotation), math.sin(rotation)
        sections: list[tuple[bool, list[QPointF], list[QPointF]]] = []
        previous_front: bool | None = None
        for index in range(97):
            angle = index * math.tau / 96
            wave = d.turbulence * math.sin(angle * 5 + self.elapsed * 1.5 + layer)
            wave += d.speech * 0.025 * math.sin(angle * 9 - self.elapsed * 8)
            ring = radius * (math.cos(latitude) + wave)
            x, y, z = ring * math.cos(angle), radius * math.sin(latitude), ring * math.sin(angle)
            y, z = y * ct - z * st, y * st + z * ct
            x, y = x * cr - y * sr, x * sr + y * cr
            perspective = 1 + z / max(1, radius) * 0.055
            point = QPointF(x * perspective, y * perspective)
            visible = z >= 0
            if visible != previous_front:
                sections.append((visible, [], []))
                previous_front = visible
            # Project both edges of a broad translucent ribbon onto this shell.
            # The surfaces make the globe read as nested volumes, rather than wires.
            for edge, edge_points in ((-1, sections[-1][1]), (1, sections[-1][2])):
                lat = latitude + edge * (0.07 + d.openness * 0.035)
                edge_ring = radius * (math.cos(lat) + wave)
                ex = edge_ring * math.cos(angle)
                ey, ez = radius * math.sin(lat), edge_ring * math.sin(angle)
                ey, ez = ey * ct - ez * st, ey * st + ez * ct
                ex, ey = ex * cr - ey * sr, ex * sr + ey * cr
                factor = 1 + ez / max(1, radius) * 0.055
                edge_points.append(QPointF(ex * factor, ey * factor))
            if z >= 0:
                if front_active:
                    front.lineTo(point)
                else:
                    front.moveTo(point)
                front_active, back_active = True, False
            else:
                if back_active:
                    back.lineTo(point)
                else:
                    back.moveTo(point)
                back_active, front_active = True, False
        painter.setPen(Qt.PenStyle.NoPen)
        for visible, upper, lower in sorted(sections, key=lambda section: section[0]):
            if len(upper) < 2:
                continue
            surface = QPainterPath(upper[0])
            for vertex in upper[1:] + list(reversed(lower)):
                surface.lineTo(vertex)
            surface.closeSubpath()
            tint = QLinearGradient(-radius, -radius, radius, radius)
            strength = round((32 if visible else 8) * d.brightness)
            tint.setColorAt(0, self._color(strength, light=1.2))
            tint.setColorAt(0.38, self._color(strength * 2, light=1.08))
            tint.setColorAt(0.7, self._color(strength // 2))
            tint.setColorAt(1, self._color(strength))
            painter.setBrush(tint)
            painter.drawPath(surface)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(self._color(20), 0.9))
        painter.drawPath(back)
        painter.setPen(QPen(self._color(round(13 * d.brightness)), 6.0))
        painter.drawPath(front)
        painter.setPen(QPen(self._color(round((84 + d.coherence * 60) * d.brightness)), 1.1))
        painter.drawPath(front)
        painter.setPen(QPen(self._color(29, light=1.3), 0.4))
        painter.drawPath(front)

    def _particles(self, painter: QPainter, radius: float) -> None:
        d = self.dynamics
        painter.setPen(Qt.PenStyle.NoPen)
        for index in range(84):
            y = 1 - 2 * (index + 0.5) / 84
            ring = math.sqrt(1 - y * y)
            angle = index * 2.399963 + self.phase * (0.7 + d.curiosity)
            x, z = ring * math.cos(angle), ring * math.sin(angle)
            offset = 1.015 + d.openness * 0.12
            point = QPointF(x * radius * offset, y * radius * offset)
            alpha = round((35 + 115 * max(0, z)) * d.brightness)
            painter.setBrush(self._color(alpha, light=1.15))
            size = 0.7 + max(0, z) * 0.8
            painter.drawEllipse(point, size, size)
        # Orbiting sparks follow curiosity; their phase stays continuous on state changes.
        for index in range(5):
            angle = self.phase * (1.0 + index * 0.12) + index * math.tau / 5
            r = radius * (0.5 + index * 0.095)
            painter.setBrush(self._color(190, light=1.2))
            painter.drawEllipse(
                QRectF(
                    math.cos(angle) * r - 1.5,
                    math.sin(angle) * r * 0.62 - 1.5,
                    3,
                    3,
                )
            )
