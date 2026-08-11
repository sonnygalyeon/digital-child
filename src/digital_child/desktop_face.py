from __future__ import annotations

import math
import random
import sys
import time
from multiprocessing.connection import Connection

from digital_child.face_state import FaceState


def run_face_window(connection: Connection, *, title: str, fps: int = 60) -> None:
    from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
    from PySide6.QtGui import (
        QColor,
        QFont,
        QLinearGradient,
        QPainter,
        QPainterPath,
        QPen,
        QRadialGradient,
    )
    from PySide6.QtWidgets import QApplication, QWidget

    class HumanFaceWidget(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle(title)
            self.resize(620, 760)
            self.setMinimumSize(420, 520)
            self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
            self.state = FaceState()
            self.started = time.monotonic()
            self.last_frame = self.started
            self.blink_amount = 0.0
            self.next_blink = self.started + random.uniform(2.0, 5.0)
            self.blink_started: float | None = None
            self.gaze_x = 0.0
            self.gaze_y = 0.0
            self.target_gaze_x = 0.0
            self.target_gaze_y = 0.0
            self.next_gaze = self.started + random.uniform(1.0, 3.0)
            self.mouth_phase = 0.0
            self.particles = [
                [random.random(), random.random(), random.uniform(0.08, 0.32)]
                for _ in range(44)
            ]
            self.timer = QTimer(self)
            self.timer.timeout.connect(self._tick)
            self.timer.start(max(8, round(1000 / fps)))

        def closeEvent(self, event) -> None:  # noqa: N802
            try:
                connection.send({"type": "closed"})
            except (BrokenPipeError, EOFError, OSError):
                pass
            event.accept()

        def _read_messages(self) -> None:
            try:
                while connection.poll():
                    message = connection.recv()
                    message_type = message.get("type")
                    if message_type == "close":
                        self.close()
                        return
                    if message_type == "state":
                        self.state = FaceState.from_payload(message.get("payload", {}))
            except (EOFError, OSError):
                self.close()

        def _tick(self) -> None:
            self._read_messages()
            now = time.monotonic()
            dt = min(0.05, max(0.001, now - self.last_frame))
            self.last_frame = now

            if self.blink_started is None and now >= self.next_blink:
                self.blink_started = now
            if self.blink_started is not None:
                phase = (now - self.blink_started) / 0.18
                if phase >= 1.0:
                    self.blink_amount = 0.0
                    self.blink_started = None
                    fatigue = max(0.0, min(1.0, self.state.fatigue))
                    self.next_blink = now + random.uniform(1.8, 4.8) * (1.0 - 0.45 * fatigue)
                else:
                    self.blink_amount = math.sin(math.pi * phase)

            if now >= self.next_gaze:
                span = 0.42 if self.state.process == "idle" else 0.25
                self.target_gaze_x = random.uniform(-span, span)
                self.target_gaze_y = random.uniform(-span * 0.55, span * 0.35)
                self.next_gaze = now + random.uniform(1.1, 3.4)
            smoothing = 1.0 - math.exp(-dt * 4.0)
            self.gaze_x += (self.target_gaze_x - self.gaze_x) * smoothing
            self.gaze_y += (self.target_gaze_y - self.gaze_y) * smoothing
            self.mouth_phase += dt * (8.0 + 10.0 * self.state.speaking_level)
            self.update()

        def paintEvent(self, event) -> None:  # noqa: N802
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            width = float(self.width())
            height = float(self.height())
            t = time.monotonic() - self.started

            background = QLinearGradient(0, 0, 0, height)
            background.setColorAt(0.0, QColor(5, 11, 18))
            background.setColorAt(0.55, QColor(9, 20, 29))
            background.setColorAt(1.0, QColor(2, 7, 12))
            painter.fillRect(self.rect(), background)

            accent = self._accent_color()
            for index, particle in enumerate(self.particles):
                px = (particle[0] + 0.018 * math.sin(t * particle[2] + index)) % 1.0
                py = (particle[1] - t * particle[2] * 0.006) % 1.0
                alpha = 20 + int(38 * (0.5 + 0.5 * math.sin(t * 0.7 + index)))
                color = QColor(accent)
                color.setAlpha(alpha)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                radius = 0.8 + particle[2] * 2.2
                painter.drawEllipse(QPointF(px * width, py * height), radius, radius)

            breathing = 1.0 + 0.004 * math.sin(t * 1.35)
            head_bob = 2.4 * math.sin(t * 0.72)
            head_tilt = 0.65 * math.sin(t * 0.31)
            painter.save()
            painter.translate(width / 2.0, height * 0.48 + head_bob)
            painter.rotate(head_tilt)
            painter.scale(breathing, breathing)
            scale = min(width / 620.0, height / 760.0)
            painter.scale(scale, scale)
            self._draw_shoulders(painter, accent)
            self._draw_head(painter, accent, t)
            painter.restore()
            self._draw_hud(painter, accent)

        def _accent_color(self) -> QColor:
            expression = self.state.expression
            palette = {
                "happy": QColor(91, 225, 180),
                "curious": QColor(64, 214, 231),
                "skeptical": QColor(247, 186, 76),
                "wary": QColor(247, 129, 93),
                "confused": QColor(185, 140, 255),
                "thinking": QColor(80, 166, 255),
                "speaking": QColor(75, 225, 220),
                "listening": QColor(95, 195, 255),
            }
            return palette.get(expression, QColor(76, 210, 221))

        def _draw_shoulders(self, painter: QPainter, accent: QColor) -> None:
            path = QPainterPath()
            path.moveTo(-245, 305)
            path.cubicTo(-210, 250, -128, 230, -82, 220)
            path.cubicTo(-30, 244, 30, 244, 82, 220)
            path.cubicTo(128, 230, 210, 250, 245, 305)
            path.lineTo(245, 380)
            path.lineTo(-245, 380)
            path.closeSubpath()
            gradient = QLinearGradient(0, 210, 0, 380)
            gradient.setColorAt(0.0, QColor(19, 48, 59))
            gradient.setColorAt(1.0, QColor(5, 17, 24))
            painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 85), 1.2))
            painter.setBrush(gradient)
            painter.drawPath(path)

        def _draw_head(self, painter: QPainter, accent: QColor, t: float) -> None:
            face = QPainterPath()
            face.moveTo(0, -292)
            face.cubicTo(-118, -295, -186, -205, -190, -72)
            face.cubicTo(-194, 70, -140, 198, -47, 257)
            face.cubicTo(-19, 276, 19, 276, 47, 257)
            face.cubicTo(140, 198, 194, 70, 190, -72)
            face.cubicTo(186, -205, 118, -295, 0, -292)
            face.closeSubpath()

            skin = QRadialGradient(QPointF(-42, -80), 350)
            warm = max(-1.0, min(1.0, self.state.valence))
            skin.setColorAt(0.0, QColor(112 + int(8 * warm), 144 + int(5 * warm), 151))
            skin.setColorAt(0.48, QColor(61, 94, 105))
            skin.setColorAt(1.0, QColor(23, 48, 60))
            painter.setBrush(skin)
            painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 130), 1.5))
            painter.drawPath(face)

            # Soft cybernetic contour lines preserve the digital identity without looking like ASCII.
            painter.setBrush(Qt.BrushStyle.NoBrush)
            contour = QColor(accent)
            contour.setAlpha(42)
            painter.setPen(QPen(contour, 1.0))
            for offset in (-1, 1):
                cheek = QPainterPath()
                cheek.moveTo(28 * offset, 82)
                cheek.cubicTo(82 * offset, 105, 121 * offset, 90, 150 * offset, 42)
                painter.drawPath(cheek)

            self._draw_brows(painter, accent)
            self._draw_eye(painter, -73, -75, accent, left=True)
            self._draw_eye(painter, 73, -75, accent, left=False)
            self._draw_nose(painter, accent)
            self._draw_mouth(painter, accent, t)
            self._draw_cheek_light(painter, accent)

        def _draw_brows(self, painter: QPainter, accent: QColor) -> None:
            expression = self.state.expression
            left_inner = 0.0
            right_inner = 0.0
            if expression == "curious":
                left_inner = right_inner = -9.0
            elif expression in {"skeptical", "wary"}:
                left_inner, right_inner = 10.0, -7.0
            elif expression == "confused":
                left_inner = right_inner = 8.0
            elif expression == "thinking":
                left_inner = right_inner = 5.0
            pen = QPen(QColor(18, 35, 42, 220), 10.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            for side in (-1, 1):
                path = QPainterPath()
                outer_x = 126 * side
                inner_x = 24 * side
                inner_delta = left_inner if side < 0 else right_inner
                path.moveTo(outer_x, -126)
                path.cubicTo(92 * side, -140, 55 * side, -143 + inner_delta, inner_x, -131 + inner_delta)
                painter.drawPath(path)

        def _draw_eye(self, painter: QPainter, x: float, y: float, accent: QColor, *, left: bool) -> None:
            expression = self.state.expression
            narrow = 0.0
            if expression in {"skeptical", "wary"}:
                narrow = 0.26
            if expression == "happy":
                narrow = 0.18
            open_height = 27.0 * (1.0 - self.blink_amount) * (1.0 - narrow)
            open_height = max(1.0, open_height)
            eye = QPainterPath()
            eye.moveTo(x - 58, y)
            eye.cubicTo(x - 28, y - open_height, x + 28, y - open_height, x + 58, y)
            eye.cubicTo(x + 28, y + open_height, x - 28, y + open_height, x - 58, y)
            eye.closeSubpath()
            painter.setBrush(QColor(210, 229, 228, 235))
            painter.setPen(QPen(QColor(17, 37, 44), 2.2))
            painter.drawPath(eye)

            if self.blink_amount < 0.90:
                gaze_scale = 18.0
                iris_x = x + self.gaze_x * gaze_scale
                iris_y = y + self.gaze_y * 10.0
                iris_radius = 17.0
                iris_gradient = QRadialGradient(QPointF(iris_x - 4, iris_y - 5), iris_radius * 1.2)
                iris_gradient.setColorAt(0.0, QColor(155, 244, 238))
                iris_gradient.setColorAt(0.45, QColor(accent))
                iris_gradient.setColorAt(1.0, QColor(15, 75, 83))
                painter.setBrush(iris_gradient)
                painter.setPen(QPen(QColor(18, 71, 77), 1.0))
                painter.drawEllipse(QPointF(iris_x, iris_y), iris_radius, iris_radius)
                pupil = 7.0 + 2.0 * self.state.arousal
                painter.setBrush(QColor(2, 10, 13))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPointF(iris_x, iris_y), pupil, pupil)
                painter.setBrush(QColor(245, 255, 255, 210))
                painter.drawEllipse(QPointF(iris_x - 5, iris_y - 6), 3.0, 3.0)

            lid = QPainterPath()
            lid.moveTo(x - 58, y)
            lid.cubicTo(x - 28, y - open_height, x + 28, y - open_height, x + 58, y)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(15, 35, 42), 3.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawPath(lid)

        def _draw_nose(self, painter: QPainter, accent: QColor) -> None:
            path = QPainterPath()
            path.moveTo(-4, -40)
            path.cubicTo(-10, 10, -18, 45, -27, 69)
            path.cubicTo(-15, 79, -3, 83, 0, 83)
            path.cubicTo(3, 83, 15, 79, 27, 69)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(21, 52, 61, 170), 2.0))
            painter.drawPath(path)
            highlight = QColor(accent)
            highlight.setAlpha(38)
            painter.setPen(QPen(highlight, 1.2))
            painter.drawLine(QPointF(5, -35), QPointF(12, 47))

        def _draw_mouth(self, painter: QPainter, accent: QColor, t: float) -> None:
            expression = self.state.expression
            smile = 0.0
            if expression == "happy":
                smile = 15.0
            elif expression in {"skeptical", "wary"}:
                smile = -6.0
            elif expression == "confused":
                smile = -2.0
            speaking = self.state.process == "speaking" or expression == "speaking"
            opening = 2.0
            if speaking:
                opening = 6.0 + 15.0 * self.state.speaking_level * (0.45 + 0.55 * abs(math.sin(self.mouth_phase)))
            elif expression == "curious":
                opening = 5.0
            upper = QPainterPath()
            upper.moveTo(-72, 142)
            upper.cubicTo(-34, 130 - smile * 0.25, -15, 132, 0, 138 - smile * 0.18)
            upper.cubicTo(15, 132, 34, 130 - smile * 0.25, 72, 142)
            lower = QPainterPath()
            lower.moveTo(-72, 142)
            lower.cubicTo(-35, 151 + opening - smile, 35, 151 + opening - smile, 72, 142)
            mouth = QPainterPath(upper)
            mouth.connectPath(lower.toReversed())
            mouth.closeSubpath()
            painter.setBrush(QColor(36, 19, 27, 230))
            painter.setPen(QPen(QColor(24, 34, 39), 2.0))
            painter.drawPath(mouth)
            if opening > 5:
                painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 85), 1.0))
                painter.drawPath(lower)

        def _draw_cheek_light(self, painter: QPainter, accent: QColor) -> None:
            color = QColor(accent)
            color.setAlpha(28 + int(30 * self.state.arousal))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(-160, 76, 52, 18))
            painter.drawEllipse(QRectF(108, 76, 52, 18))

        def _draw_hud(self, painter: QPainter, accent: QColor) -> None:
            painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 150), 1.0))
            painter.setBrush(QColor(4, 13, 19, 205))
            rect = QRectF(22, self.height() - 78, self.width() - 44, 50)
            painter.drawRoundedRect(rect, 14, 14)
            painter.setFont(QFont("Sans Serif", 10, QFont.Weight.DemiBold))
            painter.setPen(QColor(220, 245, 246))
            painter.drawText(
                rect.adjusted(16, 5, -16, -23),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self.state.status_text,
            )
            painter.setFont(QFont("Sans Serif", 8))
            painter.setPen(QColor(125, 182, 188))
            details = (
                f"эмоция: {self.state.expression}   "
                f"доверие: {self.state.trust:.2f}   "
                f"любопытство: {self.state.curiosity:.2f}"
            )
            painter.drawText(
                rect.adjusted(16, 24, -16, -4),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                details,
            )

    app = QApplication.instance() or QApplication(sys.argv)
    widget = HumanFaceWidget()
    widget.show()
    app.exec()
