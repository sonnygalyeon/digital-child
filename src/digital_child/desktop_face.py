from __future__ import annotations

from multiprocessing.connection import Connection


def run_face_window(connection: Connection, *, title: str, fps: int = 60) -> None:
    """Keep the terminal's optional companion window, using the shared sphere."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from digital_child.face_state import FaceState
    from digital_child.orb_widget import OrbWidget

    app = QApplication.instance() or QApplication([])
    widget = OrbWidget(fps=fps)
    widget.setWindowTitle(title)
    widget.resize(560, 560)

    def receive() -> None:
        try:
            for _ in range(200):
                if not connection.poll():
                    break
                message = connection.recv()
                if message.get("type") == "close":
                    widget.close()
                    return
                if message.get("type") == "state":
                    widget.set_state(FaceState.from_payload(message.get("payload", {})))
        except (EOFError, OSError):
            widget.close()

    timer = QTimer(widget)
    timer.timeout.connect(receive)
    timer.start(25)
    widget.show()
    app.exec()
    connection.close()
