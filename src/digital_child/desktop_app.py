from __future__ import annotations

import multiprocessing
import os
import time
from dataclasses import replace
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import Any

from PySide6.QtCore import QByteArray, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QFont, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from digital_child.desktop_runtime import run_agent_session
from digital_child.face_state import FaceState
from digital_child.orb_widget import OrbWidget

_STYLE = """
QWidget { background: #0b1211; color: #dfe9e3; font-family: 'Segoe UI', 'Arial';
          font-size: 13px; }
QLabel { background: transparent; }
QMainWindow, QWidget#root { background: #080e0c; }
QFrame#header { background: #0e1713; border-bottom: 1px solid #233028; }
QLabel#brand { font-size: 17px; font-weight: 700; letter-spacing: 3px; }
QLabel#muted { color: #80978b; font-size: 12px; }
QLabel#eyebrow { color: #89a895; font-size: 11px; letter-spacing: 2px; }
QLabel#name { font-size: 26px; font-weight: 600; }
QLabel#process { color: #9ff0ba; font-size: 15px; }
QLabel#connection { color: #98b7a4; padding: 8px 12px; background: #17241b;
                    border: 1px solid #2a3e30; border-radius: 12px; }
QLabel#chatTitle { font-size: 20px; font-weight: 600; }
QFrame#message { background: #141f19; border: 1px solid #28372d; border-radius: 14px; }
QFrame#userMessage { background: #1e3225; border: 1px solid #33543c; border-radius: 14px; }
QFrame#notice { background: #101913; border: 1px solid #25372b; border-radius: 10px; }
QLabel#role { color: #9dcbb0; font-size: 11px; font-weight: 600; letter-spacing: 1px; }
QLabel#body { background: transparent; font-size: 14px; }
QLabel#metadata { color: #8ea294; background: transparent; font-size: 11px; }
QScrollArea { border: none; background: #0b1211; }
QScrollBar:vertical { width: 7px; background: transparent; margin: 0; }
QScrollBar::handle:vertical { background: #314739; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QPlainTextEdit { background: #121e17; border: 1px solid #314a38; border-radius: 12px;
                 padding: 12px; font-size: 14px; selection-background-color: #355b40; }
QPlainTextEdit:focus { border: 1px solid #76c78d; }
QPushButton { background: #16241b; border: 1px solid #304636; border-radius: 8px;
              padding: 8px 12px; color: #b4ccbc; }
QPushButton:hover { background: #22382a; border-color: #598969; }
QPushButton:disabled { color: #506858; border-color: #25382a; }
QPushButton#send { background: #a4e6b4; color: #102517; border: none; font-weight: 600; }
QPushButton#send:hover { background: #c1f5cd; }
QPushButton#send:disabled { background: #294535; color: #62846b; }
QProgressBar { border: none; background: #1e3025; border-radius: 2px; height: 4px;
               max-height: 4px; }
QProgressBar::chunk { background: #7cce99; border-radius: 2px; }
QTabWidget::pane { border: none; border-top: 1px solid #26382c; }
QTabBar::tab { color: #829a8b; padding: 10px 15px; background: transparent;
              border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #bdebc9; border-bottom: 2px solid #7cce99; }
QSplitter::handle { background: #233329; width: 1px; }
"""

_EMOTIONS = {
    "neutral": "Спокойствие",
    "happy": "Радость",
    "curious": "Любопытство",
    "skeptical": "Скепсис",
    "wary": "Настороженность",
    "confused": "Замешательство",
    "thinking": "Размышление",
    "listening": "Внимание",
    "speaking": "Общение",
    "sad": "Грусть",
    "frustrated": "Раздражение",
    "anxious": "Тревога",
    "proud": "Удовлетворение достижением",
    "affectionate": "Тёплое отношение",
    "bored": "Скука",
}
_STAGES = {
    "newborn": "Первое пробуждение",
    "early_childhood": "Раннее развитие",
    "explorer": "Исследователь",
    "adolescent": "Становление",
    "mature": "Зрелость",
    "experienced": "Накопленный опыт",
    "reflective": "Рефлексивная интеграция",
}
_NEEDS = {
    "curiosity": "Исследование",
    "coherence": "Согласованность",
    "social_connection": "Общение",
    "competence": "Компетентность",
    "autonomy": "Самостоятельность",
    "predictability": "Предсказуемость",
    "rest": "Отдых",
    "self_preservation": "Непрерывность личности",
}


def _label(text: str = "", name: str = "", *, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(wrap)
    if name:
        label.setObjectName(name)
    return label


class MessageInput(QPlainTextEdit):
    submitted = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            if not event.isAutoRepeat():
                self.submitted.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class MessageCard(QFrame):
    def __init__(self, role: str, text: str = "") -> None:
        super().__init__()
        self.setObjectName("userMessage" if role == "user" else "message")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(8)
        layout.addWidget(_label("ВЫ" if role == "user" else "DIGITAL CHILD", "role"))
        self.body = _label(text, "body", wrap=True)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.body)
        self.metadata = _label("", "metadata", wrap=True)
        self.metadata.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.metadata)
        self.metadata.hide()
        self.text = text

    def append(self, token: str) -> None:
        self.text += token
        self.body.setText(self.text)


class DesktopWindow(QMainWindow):
    def __init__(
        self,
        database_path: Path,
        *,
        auto_research: bool = True,
        cognitive_loop: bool = True,
        start_backend: bool = True,
    ) -> None:
        super().__init__()
        self.database_path = database_path
        self.auto_research = auto_research
        self.cognitive_loop = cognitive_loop
        self.process: BaseProcess | None = None
        self.connection: Any = None
        self.ready = False
        self.backend_failed = False
        self.busy = False
        self.closing = False
        self.close_deadline = 0.0
        self.face = FaceState()
        self.reply: MessageCard | None = None
        self.loop_running = False
        self.loop_paused = False
        self.settings = QSettings("DigitalChild", "Desktop")
        self.setWindowTitle("Digital Child — эмоциональный агент")
        self.resize(1220, 860)
        self.setMinimumSize(880, 740)
        self.setStyleSheet(_STYLE)
        self._build_ui()
        geometry = self.settings.value("geometry")
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)
        splitter = self.settings.value("splitter")
        if isinstance(splitter, QByteArray):
            self.splitter.restoreState(splitter)
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll)
        self.poll_timer.start(25)
        self.input.textChanged.connect(self._update_controls)
        self._update_controls()
        if start_backend:
            QTimer.singleShot(0, self._start_backend)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QFrame()
        header.setObjectName("header")
        top = QHBoxLayout(header)
        top.setContentsMargins(27, 19, 27, 19)
        top.addWidget(_label("◉  DIGITAL CHILD", "brand"))
        top.addWidget(_label("Личность · память · самостоятельность", "muted"))
        top.addStretch()
        self.connection_label = _label("Запускаю ядро…", "connection")
        top.addWidget(self.connection_label)
        layout.addWidget(header)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self._build_identity_panel())
        self.splitter.addWidget(self._build_chat_panel())
        self.splitter.setSizes([440, 760])
        layout.addWidget(self.splitter, 1)

    def _build_identity_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(320)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 25, 24, 21)
        layout.setSpacing(7)
        layout.addWidget(_label("ВНУТРЕННИЙ МИР", "eyebrow"))
        self.name_label = _label("Digital Child", "name")
        layout.addWidget(self.name_label)
        self.stage_label = _label("Восстанавливаю личность…", "muted", wrap=True)
        layout.addWidget(self.stage_label)
        self.orb = OrbWidget()
        layout.addWidget(self.orb, 1)
        self.process_label = _label("Пробуждение", "process")
        self.process_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.process_label)
        self.emotion_label = _label("Слои отражают внутреннее состояние", "muted")
        self.emotion_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.emotion_label)
        tabs = QTabWidget()
        self.emotion_bars: dict[str, tuple[QProgressBar, QLabel]] = {}
        self.need_bars: dict[str, tuple[QProgressBar, QLabel]] = {}
        self.personality_bars: dict[str, tuple[QProgressBar, QLabel]] = {}
        tabs.addTab(
            self._meters(
                [
                    ("curiosity", "Любопытство"),
                    ("confidence", "Уверенность"),
                    ("confusion", "Растерянность"),
                    ("trust", "Доверие"),
                    ("arousal", "Возбуждение"),
                    ("fatigue", "Усталость"),
                ],
                self.emotion_bars,
            ),
            "Состояние",
        )
        tabs.addTab(self._meters(list(_NEEDS.items()), self.need_bars), "Потребности")
        personality_panel = self._meters(
            [
                ("openness", "Открытость опыту"),
                ("persistence", "Настойчивость"),
                ("flexibility", "Гибкость"),
                ("empathy", "Эмпатия"),
                ("assertiveness", "Самостоятельность"),
                ("uncertainty_tolerance", "Терпимость к неопределённости"),
                ("regulation", "Саморегуляция"),
                ("efficacy", "Оценка своей эффективности"),
            ],
            self.personality_bars,
        )
        tabs.addTab(personality_panel, "Личность")
        layout.addWidget(tabs)
        self.goal_label = _label("Текущая цель появится после загрузки", "muted", wrap=True)
        self.goal_label.setMaximumHeight(54)
        layout.addWidget(self.goal_label)
        bottom = QHBoxLayout()
        self.loop_label = _label("Фоновый цикл…", "muted")
        bottom.addWidget(self.loop_label, 1)
        self.pause_button = QPushButton("Пауза")
        self.pause_button.clicked.connect(self._toggle_pause)
        bottom.addWidget(self.pause_button)
        rest_button = QPushButton("Отдых")
        rest_button.setToolTip("Восстановить энергию агента")
        rest_button.clicked.connect(lambda: self._submit("/rest"))
        self.action_buttons = [rest_button]
        bottom.addWidget(rest_button)
        layout.addLayout(bottom)
        return panel

    def _meters(
        self,
        fields: list[tuple[str, str]],
        destination: dict[str, tuple[QProgressBar, QLabel]],
    ) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 13, 0, 12)
        layout.setSpacing(5)
        for key, title in fields:
            row = QHBoxLayout()
            row.addWidget(_label(title, "muted"))
            value = _label("—", "muted")
            row.addWidget(value, alignment=Qt.AlignmentFlag.AlignRight)
            layout.addLayout(row)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setAccessibleName(title)
            layout.addWidget(bar)
            destination[key] = (bar, value)
        return widget

    def _build_chat_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(25, 25, 25, 20)
        layout.setSpacing(12)
        heading = QHBoxLayout()
        heading.addWidget(_label("Диалог", "chatTitle"))
        heading.addStretch()
        heading.addWidget(_label("Каждый разговор становится опытом", "muted"))
        layout.addLayout(heading)
        tools = QHBoxLayout()
        for title, command in (
            ("Память", "/memory"),
            ("Убеждения", "/beliefs"),
            ("Цели", "/goals"),
            ("Справка", "/help"),
        ):
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, cmd=command: self._submit(cmd))
            self.action_buttons.append(button)
            tools.addWidget(button)
        tools.addStretch()
        layout.addLayout(tools)
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        content = QWidget()
        self.messages = QVBoxLayout(content)
        self.messages.setContentsMargins(0, 5, 9, 5)
        self.messages.setSpacing(12)
        self.messages.addStretch()
        self.chat_scroll.setWidget(content)
        layout.addWidget(self.chat_scroll, 1)
        self.activity_label = _label("Загружаю память и состояние агента…", "muted")
        layout.addWidget(self.activity_label)
        composer = QHBoxLayout()
        self.input = MessageInput()
        self.input.setPlaceholderText("Напишите сообщение…")
        self.input.setAccessibleName("Сообщение агенту")
        self.input.setFixedHeight(88)
        self.input.submitted.connect(self._submit)
        composer.addWidget(self.input, 1)
        self.send_button = QPushButton("Отправить  ↗")
        self.send_button.setObjectName("send")
        self.send_button.setFixedHeight(88)
        self.send_button.clicked.connect(lambda: self._submit())
        composer.addWidget(self.send_button)
        layout.addLayout(composer)
        layout.addWidget(_label("Enter — отправить · Shift+Enter — новая строка", "muted"))
        return panel

    def _start_backend(self) -> None:
        if not self.isVisible():
            return
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe()
        self.connection = parent
        process = context.Process(
            target=run_agent_session,
            args=(child, str(self.database_path), self.auto_research, self.cognitive_loop),
            name="digital-child-core",
            daemon=True,
        )
        self.process = process
        try:
            process.start()
        except Exception as exc:
            self.process = None
            parent.close()
            self.connection = None
            self._handle_message({"type": "fatal", "text": f"Ошибка запуска ядра: {exc}"})
        finally:
            child.close()

    def _submit(self, text: str | None = None) -> None:
        if not self.ready or self.busy or self.closing:
            return
        text = (self.input.toPlainText() if text is None else text).strip()
        if not text:
            return
        if text == "/quit":
            self.close()
            return
        if not self._send({"type": "input", "text": text}):
            return
        if text == self.input.toPlainText().strip():
            self.input.clear()
        self._add_card(MessageCard("user", text), force_scroll=True)
        self.reply = MessageCard("agent", "Размышляю…")
        self.reply.text = ""
        self._add_card(self.reply, force_scroll=True)
        self.busy = True
        self._set_process("thinking")
        self.activity_label.setText("Агент обдумывает сообщение…")
        self._update_controls()

    def _send(self, message: dict[str, Any]) -> bool:
        try:
            if self.connection is None:
                return False
            self.connection.send(message)
            return True
        except (BrokenPipeError, EOFError, OSError):
            self._handle_message({"type": "fatal", "text": "Связь с ядром прервана."})
            return False

    def _poll(self) -> None:
        if self.closing:
            self._finish_close()
            return
        if self.connection is not None:
            try:
                for _ in range(200):
                    if not self.connection.poll():
                        break
                    self._handle_message(self.connection.recv())
            except (EOFError, OSError):
                self.connection.close()
                self.connection = None
                if not self.backend_failed:
                    self._handle_message({"type": "fatal", "text": "Когнитивное ядро завершилось."})
        if self.process is not None and not self.process.is_alive() and not self.backend_failed:
            self._handle_message({"type": "fatal", "text": "Когнитивное ядро завершилось."})

    def _handle_message(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == "ready":
            self.ready = True
            for item in message.get("history", []):
                self._add_card(MessageCard(item["role"], item["content"]))
            for line in message.get("opening", []):
                self._notice(line)
            self._apply_snapshot(message["snapshot"])
            self.connection_label.setText("Проверяю LLM…")
            self.activity_label.setText("Можно начать разговор")
            self._scroll_bottom()
            self._update_controls()
            self.input.setFocus()
        elif kind == "health":
            health = message["health"]
            if health["enabled"] and health["healthy"]:
                self.connection_label.setText(f"●  {health['model']}")
            else:
                self.connection_label.setText("●  Режим без LLM")
                self._notice(
                    "LLM недоступна или отключена. Ответы формирует встроенный набор правил. "
                    "Проверьте настройки .env и подключение к модели командой /llm."
                )
            self.connection_label.setToolTip(health.get("detail", ""))
        elif kind == "snapshot":
            self._apply_snapshot(message["snapshot"])
        elif kind == "token":
            follow = self._near_bottom()
            if self.reply is not None:
                self.reply.append(message["text"])
            self.face = FaceState.from_payload(message["face"])
            self._set_process("speaking")
            self.activity_label.setText("Агент отвечает…")
            if follow:
                self._scroll_bottom()
        elif kind == "complete":
            if self.reply is not None:
                if message.get("text"):
                    self.reply.text = message["text"]
                    self.reply.body.setText(self.reply.text)
                details = message.get("metadata", "")
                self.reply.metadata.setText(f"{details}\n{message.get('elapsed', 0):.1f} с".strip())
                self.reply.metadata.show()
            self._end_reply()
        elif kind in {"error", "fatal"}:
            self._notice(message.get("text", "Неизвестная ошибка"))
            if self.reply is not None and not self.reply.text:
                self.reply.body.setText("Ответ не получен.")
            self._end_reply()
            if kind == "fatal":
                self.backend_failed = True
                self.ready = False
                self.connection_label.setText("Ядро остановлено")
                self.activity_label.setText("Перезапустите приложение")
                self._update_controls()
        elif kind == "notice":
            self._notice(message["text"])

    def _apply_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.face = FaceState.from_payload(snapshot["face"])
        self.name_label.setText(snapshot["name"])
        self.stage_label.setText(
            f"{_STAGES.get(snapshot['stage'], snapshot['stage'])} · "
            f"{snapshot['deu']:.1f} единиц опыта"
        )
        self.stage_label.setToolTip(f"Условный индекс возраста: {snapshot['age']:.2f}")
        psychology = snapshot.get("psychology", {})
        personality = dict(psychology.get("character", {}))
        personality["regulation"] = psychology.get("regulation", 0.0)
        personality["efficacy"] = psychology.get("self_model", {}).get("efficacy", 0.0)
        for key, (bar, label) in self.personality_bars.items():
            value = round(personality.get(key, 0.0) * 100)
            bar.setValue(value)
            label.setText(f"{value}%")
        for need in snapshot.get("needs", []):
            if need["kind"] in self.need_bars:
                bar, label = self.need_bars[need["kind"]]
                value = round(need["level"] * 100)
                bar.setValue(value)
                label.setText(f"{value}%")
        loop = snapshot["loop"]
        self.loop_running, self.loop_paused = loop["running"], loop["paused"]
        self.loop_label.setText(
            "Цикл на паузе"
            if self.loop_paused
            else "Цикл активен"
            if self.loop_running
            else "Цикл выключен"
        )
        self.pause_button.setText(
            "Запустить" if not self.loop_running else "Продолжить" if self.loop_paused else "Пауза"
        )
        self.goal_label.setText(f"Цель: {snapshot.get('goal') or 'пока не выбрана'}")
        self.goal_label.setToolTip(self.goal_label.text())
        self._set_process(self.orb.state.process if self.busy else "idle")
        self._update_controls()

    def _set_process(self, process: str) -> None:
        # Process affects motion; the agent's underlying emotion still sets the hue.
        self.face = replace(self.face, process=process)
        self.orb.set_state(self.face)
        for key, (bar, label) in self.emotion_bars.items():
            value = round(getattr(self.face, key) * 100)
            bar.setValue(value)
            label.setText(f"{value}%")
        titles = {"idle": "Слушаю", "thinking": "Размышляю", "speaking": "Отвечаю"}
        self.process_label.setText(titles.get(process, "Слушаю"))
        self.emotion_label.setText(_EMOTIONS.get(self.face.expression, self.face.expression))

    def _end_reply(self) -> None:
        self.busy = False
        self.reply = None
        self._set_process("idle")
        self.activity_label.setText("Можно продолжить разговор")
        self._update_controls()

    def _update_controls(self) -> None:
        available = self.ready and not self.busy and not self.closing
        self.send_button.setEnabled(available and bool(self.input.toPlainText().strip()))
        for button in self.action_buttons:
            button.setEnabled(available)
        self.pause_button.setEnabled(available)

    def _toggle_pause(self) -> None:
        self._submit("/resume" if self.loop_paused or not self.loop_running else "/pause")

    def _near_bottom(self) -> bool:
        bar = self.chat_scroll.verticalScrollBar()
        return bar.maximum() - bar.value() < 80

    def _scroll_bottom(self) -> None:
        QTimer.singleShot(
            0,
            lambda: self.chat_scroll.verticalScrollBar().setValue(
                self.chat_scroll.verticalScrollBar().maximum()
            ),
        )

    def _add_card(self, card: QWidget, *, force_scroll: bool = False) -> None:
        follow = force_scroll or self._near_bottom()
        self.messages.insertWidget(self.messages.count() - 1, card)
        if follow:
            self._scroll_bottom()

    def _notice(self, text: str) -> None:
        frame = QFrame()
        frame.setObjectName("notice")
        layout = QVBoxLayout(frame)
        label = _label(text, "metadata", wrap=True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(label)
        self._add_card(frame)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitter", self.splitter.saveState())
        if self.process is None or not self.process.is_alive():
            self.poll_timer.stop()
            if self.connection is not None:
                self.connection.close()
                self.connection = None
            if self.process is not None:
                self.process.join(timeout=0)
            event.accept()
            return
        event.ignore()
        if not self.closing:
            self.closing = True
            self.close_deadline = time.monotonic() + 3
            self._send({"type": "close"})
            self.activity_label.setText("Завершаю работу ядра…")
            self._update_controls()

    def _finish_close(self) -> None:
        if self.process is not None and self.process.is_alive():
            if time.monotonic() < self.close_deadline:
                return
            self.process.terminate()
            return
        self.close()


def run_window(
    database_path: Path,
    *,
    auto_research: bool = True,
    cognitive_loop: bool = True,
) -> None:
    instance = QApplication.instance()
    app = instance if isinstance(instance, QApplication) else QApplication([])
    app.setFont(QFont("Segoe UI", 10))
    window = DesktopWindow(
        database_path, auto_research=auto_research, cognitive_loop=cognitive_loop
    )
    window.show()
    app.exec()


def main() -> None:
    # A GUI entry point for pythonw.exe and future packaged Windows builds.
    multiprocessing.freeze_support()
    from digital_child.config import env_bool, load_dotenv

    load_dotenv()
    run_window(
        Path(os.environ.get("DIGITAL_CHILD_DB", "data/digital_child.db")),
        auto_research=env_bool("DIGITAL_CHILD_AUTO_RESEARCH", True),
    )


if __name__ == "__main__":
    main()
