from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

from PyQt5.QtCore import QObject, QRunnable, Qt, QThreadPool, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import (
    QApplication,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.comms.esp32_udp_client import ESP32UdpClient
from app.core.command_schema import get_mvp3_allowed_commands
from app.core.safety_validator import validate_command
from app.llm.command_extractor import extract_command
from app.llm.ollama_client import OllamaClient
from app.llm.prompt_builder import build_mvp3_prompt


class WorkerSignals(QObject):
    log = pyqtSignal(str)
    status = pyqtSignal(str)
    field = pyqtSignal(str, str)
    finished = pyqtSignal()


class TaskWorker(QRunnable):
    def __init__(self, task: Callable[[WorkerSignals], None]):
        super().__init__()
        self.task = task
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self) -> None:
        try:
            self.task(self.signals)
        except Exception as exc:  # noqa: BLE001 - keep the GUI alive for MVP use.
            self.signals.log.emit(f"ERROR: {exc}")
            self.signals.status.emit("Error")
        finally:
            self.signals.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self, config: dict, logger: logging.Logger | None = None):
        super().__init__()
        self.config = config
        self.logger = logger or logging.getLogger("geo_gcs")
        self.thread_pool = QThreadPool.globalInstance()

        configured_commands = config.get("safety", {}).get("allowed_commands")
        self.allowed_commands = (
            list(configured_commands)
            if configured_commands
            else get_mvp3_allowed_commands()
        )

        self.manual_buttons: list[QPushButton] = []

        self.setWindowTitle("Geo Ground Control Station")
        self.resize(920, 720)
        self._build_ui()
        self._set_status("Ready")
        self.log_message("Geo Ground Control Station started")

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setSpacing(10)

        root_layout.addWidget(self._build_connection_section())
        root_layout.addWidget(self._build_manual_section())
        root_layout.addWidget(self._build_llm_section())
        root_layout.addWidget(self._build_log_section(), stretch=1)

        self.setCentralWidget(root)

    def _build_connection_section(self) -> QGroupBox:
        esp32_config = self.config.get("esp32", {})
        ollama_config = self.config.get("ollama", {})

        group = QGroupBox("Connection / Status")
        layout = QFormLayout(group)

        esp32_host = esp32_config.get("host", "192.168.4.1")
        esp32_port = esp32_config.get("port", 4210)
        ollama_base_url = ollama_config.get("base_url", "http://localhost:11434")
        ollama_model = ollama_config.get("model", "llama3.2")

        layout.addRow("ESP32:", QLabel(f"{esp32_host}:{esp32_port}"))
        layout.addRow("Ollama:", QLabel(f"{ollama_model} at {ollama_base_url}"))

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addRow("Status:", self.status_label)

        return group

    def _build_manual_section(self) -> QGroupBox:
        group = QGroupBox("Manual Command")
        layout = QGridLayout(group)

        for index, command in enumerate(self.allowed_commands):
            button = QPushButton(command)
            button.clicked.connect(
                lambda _checked=False, value=command: self.send_manual_command(value)
            )
            self.manual_buttons.append(button)
            layout.addWidget(button, index // 3, index % 3)

        return group

    def _build_llm_section(self) -> QGroupBox:
        group = QGroupBox("LLM Prompt")
        layout = QVBoxLayout(group)

        prompt_row = QHBoxLayout()
        self.prompt_input = QLineEdit()
        self.prompt_input.setPlaceholderText("light up the room")
        self.prompt_input.returnPressed.connect(self.ask_llm_and_send)
        self.ask_button = QPushButton("Ask LLM and Send")
        self.ask_button.clicked.connect(self.ask_llm_and_send)
        prompt_row.addWidget(self.prompt_input, stretch=1)
        prompt_row.addWidget(self.ask_button)
        layout.addLayout(prompt_row)

        self.raw_llm_output = QTextEdit()
        self.raw_llm_output.setReadOnly(True)
        self.raw_llm_output.setFixedHeight(90)
        layout.addWidget(QLabel("Raw LLM Output:"))
        layout.addWidget(self.raw_llm_output)

        form = QFormLayout()
        self.extracted_command_label = QLabel("-")
        self.validation_result_label = QLabel("-")
        self.esp32_reply_label = QLabel("-")
        for label in (
            self.extracted_command_label,
            self.validation_result_label,
            self.esp32_reply_label,
        ):
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        form.addRow("Extracted Command:", self.extracted_command_label)
        form.addRow("Validation Result:", self.validation_result_label)
        form.addRow("ESP32 Reply:", self.esp32_reply_label)
        layout.addLayout(form)

        return group

    def _build_log_section(self) -> QGroupBox:
        group = QGroupBox("Log")
        layout = QVBoxLayout(group)

        self.log_panel = QTextEdit()
        self.log_panel.setReadOnly(True)
        layout.addWidget(self.log_panel)

        return group

    def _make_udp_client(self) -> ESP32UdpClient:
        esp32_config = self.config.get("esp32", {})
        return ESP32UdpClient(
            host=str(esp32_config.get("host", "192.168.4.1")),
            port=int(esp32_config.get("port", 4210)),
            timeout_s=float(esp32_config.get("timeout_s", 2.0)),
        )

    def _make_ollama_client(self) -> OllamaClient:
        ollama_config = self.config.get("ollama", {})
        return OllamaClient(
            base_url=str(ollama_config.get("base_url", "http://localhost:11434")),
            model=str(ollama_config.get("model", "llama3.2")),
            timeout_s=float(ollama_config.get("timeout_s", 20)),
        )

    def send_manual_command(self, command: str) -> None:
        def task(signals: WorkerSignals) -> None:
            signals.status.emit(f"Sending {command}")
            signals.log.emit(f"Manual command selected: {command}")

            validated = validate_command(command, self.allowed_commands)
            signals.log.emit(f"Validated command: {validated}")

            reply = self._make_udp_client().send_message(validated)
            signals.log.emit(f"ESP32 reply: {reply}")
            signals.status.emit("Ready")

        self._run_task(task)

    def ask_llm_and_send(self) -> None:
        user_prompt = self.prompt_input.text().strip()
        if not user_prompt:
            self.log_message("Enter a prompt before asking the LLM")
            return

        self._set_field("raw_llm_output", "")
        self._set_field("extracted_command", "-")
        self._set_field("validation_result", "-")
        self._set_field("esp32_reply", "-")

        def task(signals: WorkerSignals) -> None:
            signals.status.emit("Calling Ollama")
            signals.log.emit(f"User prompt: {user_prompt}")

            prompt = build_mvp3_prompt(user_prompt)
            ollama_client = self._make_ollama_client()
            if not ollama_client.check_connection():
                raise ConnectionError(
                    "Ollama is not reachable. Start it with 'ollama serve' "
                    "and confirm config/default.yaml points to the right base_url."
                )

            raw_output = ollama_client.generate(prompt)
            signals.field.emit("raw_llm_output", raw_output)
            signals.log.emit(f"Raw LLM output: {raw_output!r}")

            try:
                extracted_command = extract_command(raw_output, self.allowed_commands)
            except ValueError as exc:
                signals.field.emit("validation_result", f"Rejected: {exc}")
                raise

            signals.field.emit("extracted_command", extracted_command)
            signals.log.emit(f"Extracted command: {extracted_command}")

            try:
                validated = validate_command(extracted_command, self.allowed_commands)
            except ValueError as exc:
                signals.field.emit("validation_result", f"Rejected: {exc}")
                raise

            signals.field.emit("validation_result", f"Accepted: {validated}")
            signals.log.emit(f"Validation result: accepted {validated}")

            signals.status.emit(f"Sending {validated}")
            reply = self._make_udp_client().send_message(validated)
            signals.field.emit("esp32_reply", reply)
            signals.log.emit(f"ESP32 reply: {reply}")
            signals.status.emit("Ready")

        self._run_task(task)

    def _run_task(self, task: Callable[[WorkerSignals], None]) -> None:
        self._set_busy(True)
        worker = TaskWorker(task)
        worker.signals.log.connect(self.log_message)
        worker.signals.status.connect(self._set_status)
        worker.signals.field.connect(self._set_field)
        worker.signals.finished.connect(lambda: self._set_busy(False))
        self.thread_pool.start(worker)

    def _set_field(self, field_name: str, value: str) -> None:
        if field_name == "raw_llm_output":
            self.raw_llm_output.setPlainText(value)
        elif field_name == "extracted_command":
            self.extracted_command_label.setText(value)
        elif field_name == "validation_result":
            self.validation_result_label.setText(value)
        elif field_name == "esp32_reply":
            self.esp32_reply_label.setText(value)

    def _set_status(self, value: str) -> None:
        self.status_label.setText(value)

    def _set_busy(self, busy: bool) -> None:
        for button in self.manual_buttons:
            button.setEnabled(not busy)
        self.ask_button.setEnabled(not busy)

        if busy:
            QApplication.setOverrideCursor(Qt.WaitCursor)
        elif QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()

    def log_message(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_panel.append(f"[{timestamp}] {message}")

        if message.startswith("ERROR:"):
            self.logger.error(message.removeprefix("ERROR:").strip())
        else:
            self.logger.info(message)
