from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

from PyQt5.QtCore import (
    QObject,
    QRunnable,
    Qt,
    QThread,
    QThreadPool,
    pyqtSignal,
    pyqtSlot,
)
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.comms.esp32_udp_client import ESP32UdpClient
from app.comms.sequence_executor import SequenceExecutor
from app.comms.telemetry_receiver import TelemetryReceiver
from app.core.command_schema import get_mvp9_manual_commands
from app.core.experience import ExperienceRecord, ExperienceSituation
from app.core.experience_store import ExperienceStore
from app.core.movement_sequence import MovementSequence
from app.core.safety_validator import validate_command
from app.core.sequence_feedback import adjust_sequence_from_feedback
from app.core.sequence_validator import (
    movement_sequence_warnings,
    validate_movement_sequence,
)
from app.core.situation_builder import build_situation_from_telemetry
from app.llm.movement_prompt_builder import build_mvp9_movement_prompt
from app.llm.ollama_client import OllamaClient
from app.llm.sequence_extractor import extract_sequence


class WorkerSignals(QObject):
    log = pyqtSignal(str)
    status = pyqtSignal(str)
    field = pyqtSignal(str, str)
    sequence = pyqtSignal(object)
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
        self.telemetry_thread: QThread | None = None
        self.telemetry_receiver: TelemetryReceiver | None = None
        self.telemetry_running = False
        self.busy = False
        self.sequence_running = False
        self.latest_telemetry: dict | None = None
        self.last_validated_sequence: MovementSequence | None = None
        self.last_executed_sequence: MovementSequence | None = None
        self.last_validated_situation: ExperienceSituation | None = None
        self.last_executed_situation: ExperienceSituation | None = None
        self.last_movement_user_instruction = ""
        self.last_trial_feedback = ""
        self.last_trial_outcome = ""
        self.last_trial_feedback_sequence: MovementSequence | None = None
        self.current_sequence_executor: SequenceExecutor | None = None
        self.experience_store = ExperienceStore(str(self._resolve_experience_path()))
        self.experience_matches: list[tuple[ExperienceRecord, float]] = []

        configured_commands = config.get("movement", {}).get(
            "manual_commands",
            config.get("safety", {}).get("allowed_commands"),
        )
        self.allowed_commands = (
            list(configured_commands)
            if configured_commands
            else get_mvp9_manual_commands()
        )
        self.manual_buttons: list[QPushButton] = []

        self.setWindowTitle("Geo Ground Control Station")
        self.resize(1220, 760)
        self._build_ui()
        self._apply_dark_theme()
        self._set_status("Ready")
        self.log_message("Geo Ground Control Station started")

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        workspace_layout = QHBoxLayout()
        workspace_layout.setSpacing(12)

        left_column = QWidget()
        left_column.setObjectName("columnPanel")
        left_column.setMinimumWidth(360)
        left_layout = QVBoxLayout(left_column)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        left_layout.addWidget(self._build_connection_section())
        left_layout.addWidget(self._build_telemetry_section())
        left_layout.addWidget(self._build_manual_section())
        left_layout.addWidget(self._build_log_section(), stretch=1)

        right_column = QWidget()
        right_column.setObjectName("columnPanel")
        right_column.setMinimumWidth(620)
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)
        right_layout.addWidget(self._build_workflow_tabs(), stretch=1)

        workspace_layout.addWidget(left_column, stretch=1)
        workspace_layout.addWidget(right_column, stretch=2)
        root_layout.addLayout(workspace_layout, stretch=1)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_area.setWidget(root)
        self.setCentralWidget(scroll_area)

    def _build_workflow_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.setObjectName("workflowTabs")
        tabs.tabBar().setExpanding(False)
        tabs.addTab(self._build_movement_sequence_section(), "Movement Sequence")
        tabs.addTab(self._build_experience_memory_section(), "Experience Memory")
        return tabs

    def _apply_dark_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #121212;
                color: #E5E7EB;
            }

            QWidget#appRoot {
                background: #121212;
                color: #E5E7EB;
                font-size: 13px;
            }

            QGroupBox {
                background: #1E1E1E;
                border: 1px solid #2a2a2a;
                border-radius: 8px;
                color: #E5E7EB;
                font-weight: 600;
                margin-top: 10px;
                padding: 12px 10px 10px 10px;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 0 6px;
                color: #b9b9b9;
            }

            QTabWidget#workflowTabs::pane {
                background: #1E1E1E;
                border: 1px solid #2a2a2a;
                border-radius: 8px;
                top: -1px;
            }

            QTabWidget#workflowTabs::tab-bar {
                alignment: left;
                left: 0px;
            }

            QTabWidget#workflowTabs QTabBar::tab {
                background: #181818;
                border: 1px solid #2a2a2a;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                color: #9CA3AF;
                font-weight: 700;
                min-width: 160px;
                padding: 8px 16px;
            }

            QTabWidget#workflowTabs QTabBar::tab:selected {
                background: #1E1E1E;
                color: #E5E7EB;
            }

            QTabWidget#workflowTabs QTabBar::tab:hover {
                color: #E5E7EB;
            }

            QWidget#tabPage {
                background: #1E1E1E;
            }

            QLabel {
                color: #dddddd;
            }

            QPushButton {
                background: #1F2937;
                border-radius: 6px;
                color: #E5E7EB;
                font-weight: 600;
                min-height: 30px;
                padding: 5px 10px;
            }

            QPushButton:hover {
                background: #2B3648;
            }

            QPushButton:pressed {
                background: #334155;
            }

            QPushButton:disabled {
                background: #242424;
                color: #6B7280;
            }

            QPushButton#stopButton {
                background: #8f2d2d;
                color: #fff1f2;
            }

            QPushButton#stopButton:hover {
                background: #a63737;
            }

            QPushButton#stopButton:disabled {
                background: #2e2024;
                color: #8f8588;
            }

            QPushButton#dangerButton {
                background: #4a2328;
                color: #fee2e2;
            }

            QPushButton#dangerButton:hover {
                background: #5b2a30;
            }

            QPushButton#dangerButton:disabled {
                background: #2c2022;
                color: #8f8588;
            }

            QPushButton#telemetryButton {
                background: #1f3a36;
                color: #d6f5ef;
            }

            QPushButton#telemetryButton:hover {
                background: #284943;
            }

            QLineEdit,
            QComboBox,
            QListWidget,
            QTextEdit {
                background: #181818;
                border: 1px solid #303030;
                border-radius: 6px;
                color: #f0f0f0;
                padding: 7px;
                selection-background-color: #2563eb;
                selection-color: #ffffff;
            }

            QLineEdit:focus,
            QComboBox:focus,
            QListWidget:focus,
            QTextEdit:focus {
                border-color: #60a5fa;
            }

            QComboBox QAbstractItemView {
                background: #181818;
                border: 1px solid #303030;
                color: #E5E7EB;
                outline: 0px;
                selection-background-color: #2563eb;
                selection-color: #ffffff;
            }

            QComboBox QAbstractItemView::item {
                min-height: 28px;
                padding: 6px 8px;
            }

            QComboBox QAbstractItemView::item:hover {
                background: #243244;
                color: #ffffff;
            }

            QLineEdit::placeholder {
                color: #6f7f91;
            }

            QTextEdit {
                font-family: Consolas, "Courier New", monospace;
            }

            QLabel#stateBadge {
                border-radius: 6px;
                font-weight: 700;
                padding: 6px 8px;
            }

            QLabel#sectionTitle,
            QLabel#sensorName {
                color: #9CA3AF;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0px;
                text-transform: uppercase;
            }

            QLabel#sensorValue {
                background: #181818;
                border: 1px solid #303030;
                border-radius: 6px;
                color: #E5E7EB;
                font-size: 14px;
                font-weight: 700;
                min-height: 26px;
                padding: 4px 6px;
            }
            """
        )

    def _build_connection_section(self) -> QGroupBox:
        esp32_config = self.config.get("esp32", {})
        ollama_config = self.config.get("ollama", {})

        group = QGroupBox("Connection / Status")
        layout = QFormLayout(group)
        layout.setVerticalSpacing(8)
        layout.setHorizontalSpacing(10)

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

    def _build_movement_sequence_section(self) -> QWidget:
        page = QWidget()
        page.setObjectName("tabPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignTop)

        prompt_row = QHBoxLayout()
        self.movement_prompt_input = QLineEdit()
        self.movement_prompt_input.setPlaceholderText(
            "Dodge the obstacle by moving left first, then move forward."
        )
        self.movement_prompt_input.returnPressed.connect(
            self.generate_movement_sequence
        )
        prompt_row.addWidget(self.movement_prompt_input, stretch=1)
        layout.addLayout(prompt_row)

        action_row = QHBoxLayout()
        self.generate_sequence_button = QPushButton("Generate Movement Sequence")
        self.generate_sequence_button.clicked.connect(self.generate_movement_sequence)
        self.execute_sequence_button = QPushButton("Execute Validated Sequence")
        self.execute_sequence_button.clicked.connect(self.execute_validated_sequence)
        self.movement_stop_button = QPushButton("Stop")
        self.movement_stop_button.setObjectName("stopButton")
        self.movement_stop_button.clicked.connect(self.stop_movement_sequence)
        action_row.addWidget(self.generate_sequence_button)
        action_row.addWidget(self.execute_sequence_button)
        action_row.addWidget(self.movement_stop_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.movement_raw_output = QTextEdit()
        self.movement_raw_output.setReadOnly(True)
        self.movement_raw_output.setFixedHeight(72)
        layout.addWidget(QLabel("Raw LLM Output:"))
        layout.addWidget(self.movement_raw_output)

        self.parsed_sequence_output = QTextEdit()
        self.parsed_sequence_output.setReadOnly(True)
        self.parsed_sequence_output.setFixedHeight(78)
        layout.addWidget(QLabel("Parsed Sequence:"))
        layout.addWidget(self.parsed_sequence_output)

        self.sequence_validation_label = QLabel("-")
        self.sequence_validation_label.setWordWrap(True)
        self.sequence_validation_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(QLabel("Validation Result:"))
        layout.addWidget(self.sequence_validation_label)

        self.sequence_execution_log = QTextEdit()
        self.sequence_execution_log.setReadOnly(True)
        self.sequence_execution_log.setFixedHeight(96)
        layout.addWidget(QLabel("Execution Log:"))
        layout.addWidget(self.sequence_execution_log)

        self._update_movement_buttons()
        return page

    def _build_experience_memory_section(self) -> QWidget:
        page = QWidget()
        page.setObjectName("tabPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        self.experience_instruction_input = QLineEdit()
        self.experience_instruction_input.setPlaceholderText(
            "Prompt used for the movement sequence"
        )
        self.experience_outcome_combo = QComboBox()
        self.experience_outcome_combo.addItems(["success", "partial", "failure"])
        self.experience_notes_input = QTextEdit()
        self.experience_notes_input.setFixedHeight(70)
        self.experience_notes_input.setPlaceholderText(
            "Optional notes, e.g. LEFT was enough but SAFE_FWD was not enough"
        )
        self.experience_snapshot_label = QLabel("No pre-action snapshot captured")
        self.experience_snapshot_label.setWordWrap(True)
        self.experience_snapshot_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.feedback_status_label = QLabel("No trial feedback queued")
        self.feedback_status_label.setWordWrap(True)
        self.feedback_status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        form.addRow("User Instruction:", self.experience_instruction_input)
        form.addRow("Outcome:", self.experience_outcome_combo)
        form.addRow("Notes:", self.experience_notes_input)
        form.addRow("Saved Situation:", self.experience_snapshot_label)
        form.addRow("Next Generation Feedback:", self.feedback_status_label)
        layout.addLayout(form)

        button_row = QGridLayout()
        self.save_experience_button = QPushButton("Save Experience")
        self.save_experience_button.clicked.connect(self.save_current_experience)
        self.find_experience_button = QPushButton("Find Similar Experience")
        self.find_experience_button.clicked.connect(self.find_similar_experiences)
        self.load_experience_button = QPushButton("Load Selected Experience Sequence")
        self.load_experience_button.clicked.connect(
            self.load_selected_experience_sequence
        )
        self.find_load_best_button = QPushButton("Find & Load Best Experience")
        self.find_load_best_button.clicked.connect(self.find_and_load_best_experience)
        self.use_feedback_button = QPushButton("Use Notes As Feedback")
        self.use_feedback_button.clicked.connect(self.capture_trial_feedback)
        self.clear_feedback_button = QPushButton("Clear Feedback")
        self.clear_feedback_button.clicked.connect(self.clear_trial_feedback)
        self.delete_experiences_button = QPushButton("Delete All Experiences")
        self.delete_experiences_button.setObjectName("dangerButton")
        self.delete_experiences_button.clicked.connect(self.delete_all_experiences)

        button_row.addWidget(self.save_experience_button, 0, 0)
        button_row.addWidget(self.find_experience_button, 0, 1)
        button_row.addWidget(self.load_experience_button, 1, 0)
        button_row.addWidget(self.find_load_best_button, 1, 1)
        button_row.addWidget(self.use_feedback_button, 2, 0)
        button_row.addWidget(self.clear_feedback_button, 2, 1)
        button_row.addWidget(self.delete_experiences_button, 3, 0, 1, 2)
        layout.addLayout(button_row)

        self.experience_matches_list = QListWidget()
        self.experience_matches_list.setMinimumHeight(150)
        layout.addWidget(QLabel("Similar Experiences:"))
        layout.addWidget(self.experience_matches_list, stretch=1)

        self.experience_status_label = QLabel("-")
        self.experience_status_label.setWordWrap(True)
        self.experience_status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.experience_status_label)

        self._update_experience_buttons()
        return page

    def _build_telemetry_section(self) -> QGroupBox:
        group = QGroupBox("Telemetry")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        button_row = QHBoxLayout()
        self.start_telemetry_button = QPushButton("Start Telemetry")
        self.start_telemetry_button.setObjectName("telemetryButton")
        self.start_telemetry_button.clicked.connect(self.start_telemetry)
        self.stop_telemetry_button = QPushButton("Stop Telemetry")
        self.stop_telemetry_button.clicked.connect(self.stop_telemetry)
        button_row.addWidget(self.start_telemetry_button)
        button_row.addWidget(self.stop_telemetry_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.fl_distance_label = self._make_value_label("-")
        self.fc_distance_label = self._make_value_label("-")
        self.fr_distance_label = self._make_value_label("-")
        self.left_distance_label = self._make_value_label("-")
        self.right_distance_label = self._make_value_label("-")
        self.robot_state_label = self._make_value_label("FRONT_UNKNOWN - unknown")
        self.robot_state_label.setObjectName("stateBadge")
        self.uptime_label = self._make_value_label("-")
        self.firmware_label = self._make_value_label("-")
        self.last_telemetry_label = self._make_value_label("Never")
        self.telemetry_status_label = self._make_value_label("Disconnected")

        sensor_grid = QGridLayout()
        sensor_grid.setHorizontalSpacing(8)
        sensor_grid.setVerticalSpacing(4)
        self._add_sensor_readout(sensor_grid, 0, 0, "Front Left", self.fl_distance_label)
        self._add_sensor_readout(sensor_grid, 0, 1, "Front Center", self.fc_distance_label)
        self._add_sensor_readout(sensor_grid, 0, 2, "Front Right", self.fr_distance_label)
        self._add_sensor_readout(sensor_grid, 1, 0, "Left", self.left_distance_label)
        self._add_sensor_readout(sensor_grid, 1, 1, "Right", self.right_distance_label)
        layout.addLayout(sensor_grid)

        status_grid = QGridLayout()
        status_grid.setHorizontalSpacing(8)
        status_grid.setVerticalSpacing(4)
        status_grid.addWidget(QLabel("Robot State:"), 0, 0, Qt.AlignRight)
        status_grid.addWidget(self.robot_state_label, 0, 1, 1, 3)
        status_grid.addWidget(QLabel("Uptime:"), 1, 0, Qt.AlignRight)
        status_grid.addWidget(self.uptime_label, 1, 1)
        status_grid.addWidget(QLabel("Firmware:"), 1, 2, Qt.AlignRight)
        status_grid.addWidget(self.firmware_label, 1, 3)
        status_grid.addWidget(QLabel("Last:"), 2, 0, Qt.AlignRight)
        status_grid.addWidget(self.last_telemetry_label, 2, 1)
        status_grid.addWidget(QLabel("Stream:"), 2, 2, Qt.AlignRight)
        status_grid.addWidget(self.telemetry_status_label, 2, 3)
        layout.addLayout(status_grid)

        self._apply_state_style("FRONT_UNKNOWN")
        self._update_telemetry_buttons()
        return group

    def _make_value_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return label

    def _add_sensor_readout(
        self,
        layout: QGridLayout,
        row: int,
        column: int,
        title: str,
        value_label: QLabel,
    ) -> None:
        title_label = QLabel(title)
        title_label.setObjectName("sensorName")
        title_label.setAlignment(Qt.AlignCenter)
        value_label.setObjectName("sensorValue")
        value_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label, row * 2, column)
        layout.addWidget(value_label, row * 2 + 1, column)

    def _build_manual_section(self) -> QGroupBox:
        group = QGroupBox("Manual Command")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        command_groups = [
            ("System", ("PING", "STATUS", "DIST"), 3),
            (
                "Motion / Test",
                ("FWD", "SAFE_FWD", "BACK", "LEFT", "RIGHT", "CW", "CCW", "STOP"),
                4,
            ),
        ]
        hidden_manual_commands = {"STREAM_ON", "STREAM_OFF"}
        grouped_commands = {
            command
            for _title, commands, _columns in command_groups
            for command in commands
        }

        for title, commands, columns in command_groups:
            available = [command for command in commands if command in self.allowed_commands]
            if available:
                self._add_manual_command_group(layout, title, available, columns)

        other_commands = [
            command
            for command in self.allowed_commands
            if command not in grouped_commands
            and command not in hidden_manual_commands
        ]
        if other_commands:
            self._add_manual_command_group(layout, "Other", other_commands, 3)

        return group

    def _add_manual_command_group(
        self,
        parent_layout: QVBoxLayout,
        title: str,
        commands: list[str],
        columns: int,
    ) -> None:
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        parent_layout.addWidget(title_label)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)

        for index, command in enumerate(commands):
            button_label = "FWD TEST" if command == "FWD" else command
            button = QPushButton(button_label)
            if command == "FWD":
                button.setToolTip("Manual/test raw forward command")
            if command == "STOP":
                button.setObjectName("stopButton")
            button.clicked.connect(
                lambda _checked=False, value=command: self.send_manual_command(value)
            )
            self.manual_buttons.append(button)
            grid.addWidget(button, index // columns, index % columns)

        parent_layout.addLayout(grid)

    def _build_log_section(self) -> QGroupBox:
        group = QGroupBox("Log")
        layout = QVBoxLayout(group)

        self.log_panel = QTextEdit()
        self.log_panel.setReadOnly(True)
        self.log_panel.setMinimumHeight(120)
        layout.addWidget(self.log_panel)

        return group

    def _resolve_experience_path(self) -> Path:
        experience_config = self.config.get("experience", {})
        configured_path = Path(
            str(experience_config.get("path", "data/experiences.jsonl"))
        ).expanduser()
        if configured_path.is_absolute():
            return configured_path

        repo_root = Path(__file__).resolve().parents[2]
        return repo_root / configured_path

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
        self._send_command_async(command, source="Manual command")

    def _send_command_async(self, command: str, source: str) -> None:
        def task(signals: WorkerSignals) -> None:
            signals.status.emit(f"Sending {command}")
            signals.log.emit(f"{source}: {command}")

            validated = validate_command(command, self.allowed_commands)
            signals.log.emit(f"Validated command: {validated}")

            reply = self._make_udp_client().send_message(
                validated,
                ignore_prefixes=("TEL",),
            )
            signals.log.emit(f"ESP32 reply: {reply}")
            signals.status.emit("Ready")

        self._run_task(task)

    def start_telemetry(self) -> None:
        if not self.telemetry_running:
            self._start_telemetry_receiver()
        self._send_command_async("STREAM_ON", source="Telemetry control")

    def stop_telemetry(self) -> None:
        self._send_command_async("STREAM_OFF", source="Telemetry control")
        self._stop_telemetry_receiver()

    def _start_telemetry_receiver(self) -> None:
        telemetry_config = self.config.get("telemetry", {})
        listen_host = str(telemetry_config.get("listen_host", "0.0.0.0"))
        listen_port = int(telemetry_config.get("listen_port", 4210))
        expected_prefix = str(telemetry_config.get("expected_prefix", "TEL"))
        stale_timeout_s = float(telemetry_config.get("stale_timeout_s", 2.0))

        self.telemetry_thread = QThread(self)
        self.telemetry_receiver = TelemetryReceiver(
            listen_host=listen_host,
            listen_port=listen_port,
            expected_prefix=expected_prefix,
            stale_timeout_s=stale_timeout_s,
        )
        self.telemetry_receiver.moveToThread(self.telemetry_thread)
        self.telemetry_thread.started.connect(self.telemetry_receiver.run)
        self.telemetry_receiver.telemetry_received.connect(self._handle_telemetry)
        self.telemetry_receiver.status_changed.connect(self._set_telemetry_status)
        self.telemetry_receiver.error_occurred.connect(self._handle_telemetry_error)
        self.telemetry_receiver.stale.connect(self._handle_telemetry_stale)
        self.telemetry_receiver.stopped.connect(self._handle_telemetry_stopped)
        self.telemetry_receiver.stopped.connect(self.telemetry_thread.quit)
        self.telemetry_receiver.stopped.connect(self.telemetry_receiver.deleteLater)
        self.telemetry_thread.finished.connect(self.telemetry_thread.deleteLater)

        self.telemetry_running = True
        self._set_telemetry_status("Starting listener")
        self._update_telemetry_buttons()
        self.telemetry_thread.start()
        self.log_message(
            f"Telemetry listener starting on {listen_host}:{listen_port}"
        )

    def _stop_telemetry_receiver(self) -> None:
        if self.telemetry_receiver is None:
            self.telemetry_running = False
            self._set_telemetry_status("Disconnected")
            self._update_telemetry_buttons()
            return

        self._set_telemetry_status("Stopping listener")
        self.telemetry_receiver.request_stop()

    def generate_movement_sequence(self) -> None:
        user_prompt = self.movement_prompt_input.text().strip()
        if not user_prompt:
            self.log_message("Enter a movement prompt before generating a sequence")
            return

        self.last_movement_user_instruction = user_prompt
        if hasattr(self, "experience_instruction_input"):
            self.experience_instruction_input.setText(user_prompt)
        telemetry_snapshot = (
            dict(self.latest_telemetry)
            if self.latest_telemetry is not None
            else None
        )
        situation_snapshot = (
            build_situation_from_telemetry(telemetry_snapshot)
            if telemetry_snapshot is not None
            else None
        )
        self.last_validated_sequence = None
        self.last_executed_sequence = None
        self.last_validated_situation = None
        self.last_executed_situation = None
        self._update_movement_buttons()
        self._update_experience_buttons()
        self._set_field("experience_snapshot", "No pre-action snapshot captured")
        self._set_field("movement_raw_output", "")
        self._set_field("parsed_sequence", "")
        self._set_field("sequence_validation", "-")
        self._set_field("movement_execution_log", "")

        def task(signals: WorkerSignals) -> None:
            signals.status.emit("Generating movement sequence")
            signals.log.emit(f"Movement prompt: {user_prompt}")

            prompt = build_mvp9_movement_prompt(
                user_prompt,
                telemetry_snapshot,
                previous_sequence=self.last_trial_feedback_sequence,
                trial_feedback=self.last_trial_feedback,
                trial_outcome=self.last_trial_outcome,
            )
            ollama_client = self._make_ollama_client()
            if not ollama_client.check_connection():
                raise ConnectionError(
                    "Ollama is not reachable. Start it with 'ollama serve' "
                    "and confirm config/default.yaml points to the right base_url."
                )

            raw_output = ollama_client.generate(prompt)
            signals.field.emit("movement_raw_output", raw_output)
            signals.log.emit(f"Movement raw LLM output: {raw_output!r}")

            try:
                parsed = extract_sequence(raw_output)
            except ValueError as exc:
                signals.field.emit("sequence_validation", f"Rejected: {exc}")
                raise

            signals.field.emit("parsed_sequence", json.dumps(parsed, indent=2))
            signals.log.emit("Movement JSON extracted")

            try:
                sequence = validate_movement_sequence(
                    parsed,
                    self.config,
                    latest_telemetry=telemetry_snapshot,
                )
            except ValueError as exc:
                signals.field.emit("sequence_validation", f"Rejected: {exc}")
                raise

            sequence, feedback_messages = adjust_sequence_from_feedback(
                sequence,
                feedback=self.last_trial_feedback,
                config=self.config,
                previous_sequence=self.last_trial_feedback_sequence,
            )
            for message in feedback_messages:
                signals.log.emit(message)
            warning_messages = movement_sequence_warnings(
                sequence,
                latest_telemetry=telemetry_snapshot,
                config=self.config,
            )
            for message in warning_messages:
                signals.log.emit(f"Validation warning: {message}")

            signals.sequence.emit((sequence, situation_snapshot))
            signals.field.emit(
                "sequence_validation",
                self._format_sequence_validation(
                    sequence,
                    feedback_messages,
                    warning_messages,
                ),
            )
            signals.field.emit("parsed_sequence", self._format_sequence(sequence))
            signals.log.emit("Movement sequence validated")
            signals.status.emit("Ready")

        self._run_task(task)

    def execute_validated_sequence(self) -> None:
        if self.last_validated_sequence is None:
            self.log_message("No validated movement sequence to execute")
            return

        sequence = self.last_validated_sequence
        situation_snapshot = (
            build_situation_from_telemetry(self.latest_telemetry)
            if self.latest_telemetry is not None
            else self.last_validated_situation
        )
        movement_config = self.config.get("movement", {})
        inter_step_delay_ms = int(movement_config.get("inter_step_delay_ms", 150))

        executor = SequenceExecutor(
            udp_client=self._make_udp_client(),
            inter_step_delay_ms=inter_step_delay_ms,
        )
        self.current_sequence_executor = executor
        self.sequence_running = True
        self.last_executed_sequence = sequence
        self.last_executed_situation = situation_snapshot
        self._set_field(
            "experience_snapshot",
            self._format_situation_snapshot(situation_snapshot),
        )
        self._set_field("movement_execution_log", "")
        self._update_movement_buttons()

        def task(signals: WorkerSignals) -> None:
            def log_execution(message: str) -> None:
                signals.field.emit("movement_execution_log", message)
                signals.log.emit(f"Sequence: {message}")

            executor.log_callback = log_execution
            signals.status.emit("Executing movement sequence")
            executor.execute_sequence(sequence)
            signals.status.emit("Ready")

        self._run_task(task, on_finished=self._sequence_execution_finished)

    def stop_movement_sequence(self) -> None:
        if self.current_sequence_executor is not None:
            self.current_sequence_executor.cancel()

        def task(signals: WorkerSignals) -> None:
            signals.status.emit("Sending STOP")
            signals.log.emit("Movement Stop requested")
            signals.field.emit("movement_execution_log", "Stop requested; sending STOP")
            reply = self._make_udp_client().send_message(
                "STOP",
                ignore_prefixes=("TEL",),
            )
            signals.log.emit(f"STOP reply: {reply}")
            signals.field.emit("movement_execution_log", f"STOP reply: {reply}")
            signals.status.emit("Ready")

        worker = TaskWorker(task)
        worker.signals.log.connect(self.log_message)
        worker.signals.status.connect(self._set_status)
        worker.signals.field.connect(self._set_field)
        self.thread_pool.start(worker)

    def capture_trial_feedback(self) -> None:
        sequence = self._latest_sequence_for_experience()
        if sequence is None:
            self._set_field(
                "experience_status",
                "Cannot capture feedback until a movement sequence exists",
            )
            return

        self._capture_trial_feedback_from_fields(sequence)

    def clear_trial_feedback(self) -> None:
        self.last_trial_feedback = ""
        self.last_trial_outcome = ""
        self.last_trial_feedback_sequence = None
        self._set_field("feedback_status", "No trial feedback queued")
        self._update_experience_buttons()
        self.log_message("Cleared trial feedback for next generation")

    def _capture_trial_feedback_from_fields(
        self,
        sequence: MovementSequence,
        log_to_panel: bool = True,
    ) -> None:
        feedback = self.experience_notes_input.toPlainText().strip()
        outcome = self.experience_outcome_combo.currentText().strip()

        if not feedback and outcome == "success":
            self.last_trial_feedback = ""
            self.last_trial_outcome = ""
            self.last_trial_feedback_sequence = None
            self._set_field(
                "feedback_status",
                "No feedback queued; success with no notes",
            )
            self._update_experience_buttons()
            return

        self.last_trial_feedback = feedback
        self.last_trial_outcome = outcome
        self.last_trial_feedback_sequence = sequence

        status = f"Queued outcome={outcome}"
        if feedback:
            status += f": {feedback}"
        self._set_field("feedback_status", status)
        self._update_experience_buttons()

        if log_to_panel:
            self.log_message(
                "Queued trial feedback for next movement generation: "
                f"{status}"
            )

    def save_current_experience(self) -> None:
        situation = self._latest_situation_for_experience()
        if situation is None:
            self._set_field(
                "experience_status",
                "Cannot save experience without a pre-action telemetry snapshot",
            )
            return

        sequence = self._latest_sequence_for_experience()
        if sequence is None:
            self._set_field(
                "experience_status",
                "Cannot save experience until a movement sequence exists",
            )
            return

        user_instruction = self.experience_instruction_input.text().strip()
        if not user_instruction:
            user_instruction = self.last_movement_user_instruction.strip()
        if not user_instruction:
            self._set_field(
                "experience_status",
                "Cannot save experience without a user instruction",
            )
            return

        record = ExperienceRecord(
            id=str(uuid4()),
            timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
            situation=situation,
            user_instruction=user_instruction,
            sequence=list(sequence.steps),
            outcome=self.experience_outcome_combo.currentText(),
            notes=self.experience_notes_input.toPlainText().strip(),
        )

        try:
            self.experience_store.append(record)
        except Exception as exc:  # noqa: BLE001 - keep UI alive.
            self.log_message(f"ERROR: Failed to save experience: {exc}")
            return

        self._set_field(
            "experience_status",
            f"Saved experience {record.id} to {self.experience_store.path}",
        )
        self.log_message(
            f"Saved experience {record.id}: {situation.state}, "
            f"front={situation.front_bucket}, left={situation.left_bucket}, "
            f"right={situation.right_bucket}, outcome={record.outcome}"
        )
        self._capture_trial_feedback_from_fields(sequence, log_to_panel=False)

    def find_similar_experiences(self) -> None:
        matches = self._find_similar_experience_matches(success_only=False)
        self._show_experience_matches(matches)

    def delete_all_experiences(self) -> None:
        reply = QMessageBox.question(
            self,
            "Delete All Experiences",
            (
                "Delete all saved experiences from local memory?\n\n"
                f"{self.experience_store.path}\n\n"
                "This cannot be undone."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self.log_message("Delete all experiences cancelled")
            return

        try:
            deleted_count = self.experience_store.delete_all()
        except Exception as exc:  # noqa: BLE001 - keep UI alive.
            self.log_message(f"ERROR: Failed to delete experiences: {exc}")
            return

        self.experience_matches = []
        self.experience_matches_list.clear()
        self._set_field(
            "experience_status",
            f"Deleted {deleted_count} saved experience(s)",
        )
        self.log_message(
            f"Deleted {deleted_count} saved experience(s) from "
            f"{self.experience_store.path}"
        )
        self._update_experience_buttons()

    def load_selected_experience_sequence(self) -> None:
        if not self.experience_matches:
            self.log_message("No similar experience selected")
            return

        row = self.experience_matches_list.currentRow()
        if row < 0:
            row = 0
        if row >= len(self.experience_matches):
            self.log_message("No similar experience selected")
            return

        record, score = self.experience_matches[row]
        self._load_experience_sequence(record, score)

    def find_and_load_best_experience(self) -> None:
        matches = self._find_similar_experience_matches(success_only=True)
        self._show_experience_matches(matches)

        if not matches:
            self.log_message("No similar successful experience found")
            return

        record, score = matches[0]
        self._load_experience_sequence(record, score)
        self.log_message("Loaded remembered sequence. User must approve execution.")

    def _find_similar_experience_matches(
        self,
        success_only: bool,
    ) -> list[tuple[ExperienceRecord, float]]:
        if self.latest_telemetry is None:
            self._set_field(
                "experience_status",
                "Cannot search experiences until telemetry has been received",
            )
            return []

        experience_config = self.config.get("experience", {})
        min_score = float(experience_config.get("min_similarity_score", 0.6))
        max_results = int(experience_config.get("max_results", 3))
        situation = build_situation_from_telemetry(self.latest_telemetry)

        try:
            matches = self.experience_store.find_similar(
                situation,
                limit=max_results,
            )
        except Exception as exc:  # noqa: BLE001 - keep UI alive.
            self.log_message(f"ERROR: Failed to search experiences: {exc}")
            return []

        filtered = [
            (record, score)
            for record, score in matches
            if score >= min_score
            and (not success_only or record.outcome == "success")
        ]

        self.log_message(
            f"Found {len(filtered)} similar experience(s) for "
            f"{situation.state}/front={situation.front_bucket}/"
            f"left={situation.left_bucket}/right={situation.right_bucket}"
        )
        return filtered

    def _show_experience_matches(
        self,
        matches: list[tuple[ExperienceRecord, float]],
    ) -> None:
        self.experience_matches = matches
        self.experience_matches_list.clear()

        for record, score in matches:
            self.experience_matches_list.addItem(
                self._format_experience_match(record, score)
            )

        if matches:
            self.experience_matches_list.setCurrentRow(0)
            self._set_field(
                "experience_status",
                f"Showing {len(matches)} similar experience(s)",
            )
        else:
            self._set_field("experience_status", "No similar experiences found")

        self._update_experience_buttons()

    def _load_experience_sequence(
        self,
        record: ExperienceRecord,
        score: float,
    ) -> None:
        sequence = MovementSequence(steps=list(record.sequence))
        self.last_validated_sequence = sequence
        self.last_validated_situation = (
            build_situation_from_telemetry(self.latest_telemetry)
            if self.latest_telemetry is not None
            else None
        )
        self.last_executed_situation = None
        self.last_movement_user_instruction = record.user_instruction
        self.movement_prompt_input.setText(record.user_instruction)
        self.experience_instruction_input.setText(record.user_instruction)
        self.experience_notes_input.setPlainText(record.notes)
        self.experience_outcome_combo.setCurrentText(record.outcome)
        self._capture_trial_feedback_from_fields(sequence, log_to_panel=False)
        self._set_field("parsed_sequence", self._format_sequence(sequence))
        self._set_field(
            "experience_snapshot",
            self._format_situation_snapshot(self.last_validated_situation),
        )
        self._set_field(
            "sequence_validation",
            f"Loaded remembered sequence from experience {record.id}",
        )
        self._set_field(
            "experience_status",
            f"Loaded {record.id} with score {score:.2f}; notes queued for "
            "regeneration; execute only on approval",
        )
        self._update_movement_buttons()

    def _latest_sequence_for_experience(self) -> MovementSequence | None:
        return self.last_validated_sequence or self.last_executed_sequence

    def _latest_situation_for_experience(self) -> ExperienceSituation | None:
        return self.last_executed_situation or self.last_validated_situation

    def _format_experience_match(
        self,
        record: ExperienceRecord,
        score: float,
    ) -> str:
        sequence_text = " -> ".join(step.command for step in record.sequence)
        notes_text = f" | notes: {record.notes}" if record.notes else ""
        return (
            f"score={score:.2f} | {record.situation.state} | "
            f"front={record.situation.front_bucket} "
            f"left={record.situation.left_bucket} "
            f"right={record.situation.right_bucket} | "
            f"FL={self._format_distance(record.situation.fl_cm)} "
            f"FC={self._format_distance(record.situation.fc_cm)} "
            f"FR={self._format_distance(record.situation.fr_cm)} "
            f"L={self._format_distance(record.situation.l_cm)} "
            f"R={self._format_distance(record.situation.r_cm)} | "
            f"{sequence_text} | "
            f"{record.outcome} | {record.timestamp} | {record.user_instruction}"
            f"{notes_text}"
        )

    def _run_task(
        self,
        task: Callable[[WorkerSignals], None],
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        self._set_busy(True)
        worker = TaskWorker(task)
        worker.signals.log.connect(self.log_message)
        worker.signals.status.connect(self._set_status)
        worker.signals.field.connect(self._set_field)
        worker.signals.sequence.connect(self._store_validated_sequence)
        worker.signals.finished.connect(lambda: self._set_busy(False))
        if on_finished is not None:
            worker.signals.finished.connect(on_finished)
        self.thread_pool.start(worker)

    def _handle_telemetry(self, telemetry: dict) -> None:
        received_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.latest_telemetry = dict(telemetry)
        self.latest_telemetry["last_received_time"] = received_at
        self._update_experience_buttons()

        self.fl_distance_label.setText(self._format_distance(telemetry.get("fl_cm")))
        self.fc_distance_label.setText(
            self._format_distance(telemetry.get("fc_cm", telemetry.get("front_cm")))
        )
        self.fr_distance_label.setText(self._format_distance(telemetry.get("fr_cm")))
        self.left_distance_label.setText(self._format_distance(telemetry.get("l_cm")))
        self.right_distance_label.setText(self._format_distance(telemetry.get("r_cm")))
        state = str(telemetry.get("state", "FRONT_UNKNOWN"))
        self._apply_state_style(state)
        self.uptime_label.setText(self._format_uptime(telemetry.get("uptime_ms")))
        self.firmware_label.setText(str(telemetry.get("fw", "-")))
        self.last_telemetry_label.setText(received_at)
        self._set_telemetry_status("Live")

    def _handle_telemetry_error(self, message: str) -> None:
        self._set_telemetry_status("Error")
        self.log_message(f"ERROR: {message}")

    def _handle_telemetry_stale(self) -> None:
        stale_timeout_s = self.config.get("telemetry", {}).get("stale_timeout_s", 2.0)
        self._set_telemetry_status(f"Stale: no telemetry for {stale_timeout_s}s")
        self.log_message(f"No telemetry received for {stale_timeout_s}s")

    def _handle_telemetry_stopped(self) -> None:
        self.telemetry_running = False
        self.telemetry_receiver = None
        self.telemetry_thread = None
        self._set_telemetry_status("Disconnected")
        self._update_telemetry_buttons()
        self.log_message("Telemetry listener stopped")

    def _format_uptime(self, uptime_ms: object) -> str:
        if not isinstance(uptime_ms, int):
            return "-"
        seconds = uptime_ms / 1000
        return f"{seconds:.1f} s ({uptime_ms} ms)"

    def _format_distance(self, distance_cm: object) -> str:
        if not isinstance(distance_cm, (int, float)):
            return "-"
        if float(distance_cm) == -1:
            return "-1.0 cm (unavailable)"
        return f"{float(distance_cm):.1f} cm"

    def _apply_state_style(self, state: str) -> None:
        state = state.upper()
        if state == "FRONT_CLEAR":
            state = "CLEAR"

        if state == "CLEAR":
            text = "CLEAR - clear/safe"
            style = (
                "background: #12342c; border: 1px solid #00C896; "
                "color: #d8f3dc;"
            )
        elif state in {"BLOCKED_FRONT", "BLOCKED_LEFT", "BLOCKED_RIGHT"}:
            text = f"{state} - blocked/warning"
            style = (
                "background: #49351f; border: 1px solid #FFB020; "
                "color: #ffe8b6;"
            )
        elif state in {"FRONT_UNKNOWN", "SENSOR_ERROR"}:
            text = f"{state} - caution"
            style = (
                "background: #35312a; border: 1px solid #9f7a2e; "
                "color: #f5e6bf;"
            )
        else:
            text = f"{state} - unknown"
            style = (
                "background: #292d33; border: 1px solid #4b5563; "
                "color: #e5e7eb;"
            )

        self.robot_state_label.setText(text)
        self.robot_state_label.setStyleSheet(style)

    def _store_validated_sequence(self, payload: object) -> None:
        if isinstance(payload, tuple):
            sequence, situation = payload
        else:
            sequence = payload
            situation = None

        if not isinstance(sequence, MovementSequence):
            self.log_message("ERROR: Invalid movement sequence payload")
            return

        self.last_validated_sequence = sequence
        self.last_validated_situation = situation
        self._set_field(
            "experience_snapshot",
            self._format_situation_snapshot(situation),
        )
        self._update_movement_buttons()
        self._update_experience_buttons()

    def _sequence_execution_finished(self) -> None:
        self.sequence_running = False
        self.current_sequence_executor = None
        self._update_movement_buttons()
        self._update_experience_buttons()

    def _format_sequence(self, sequence: MovementSequence) -> str:
        lines = []
        for index, step in enumerate(sequence.steps, start=1):
            lines.append(f"{index}. {step.command} for {step.duration_ms} ms")
        return "\n".join(lines)

    def _format_sequence_validation(
        self,
        sequence: MovementSequence,
        feedback_messages: list[str],
        warning_messages: list[str],
    ) -> str:
        result = f"Accepted: {len(sequence.steps)} validated step(s)"
        if feedback_messages:
            result += f"; applied {len(feedback_messages)} feedback adjustment(s)"
        if warning_messages:
            result += "\nWarnings:\n" + "\n".join(f"- {item}" for item in warning_messages)
        return result

    def _format_situation_snapshot(
        self,
        situation: ExperienceSituation | None,
    ) -> str:
        if situation is None:
            return "No pre-action snapshot captured"

        return (
            f"{situation.state}; "
            f"FL={self._format_distance(situation.fl_cm)}, "
            f"FC={self._format_distance(situation.fc_cm)}, "
            f"FR={self._format_distance(situation.fr_cm)}, "
            f"L={self._format_distance(situation.l_cm)}, "
            f"R={self._format_distance(situation.r_cm)}; "
            f"buckets: front={situation.front_bucket}, "
            f"left={situation.left_bucket}, right={situation.right_bucket}"
        )

    def _set_field(self, field_name: str, value: str) -> None:
        if field_name == "movement_raw_output":
            self.movement_raw_output.setPlainText(value)
        elif field_name == "parsed_sequence":
            self.parsed_sequence_output.setPlainText(value)
        elif field_name == "sequence_validation":
            self.sequence_validation_label.setText(value)
        elif field_name == "movement_execution_log":
            if value:
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.sequence_execution_log.append(f"[{timestamp}] {value}")
            else:
                self.sequence_execution_log.setPlainText("")
        elif field_name == "experience_status":
            self.experience_status_label.setText(value)
        elif field_name == "experience_snapshot":
            self.experience_snapshot_label.setText(value)
        elif field_name == "feedback_status":
            self.feedback_status_label.setText(value)

    def _set_status(self, value: str) -> None:
        self.status_label.setText(value)

    def _set_telemetry_status(self, value: str) -> None:
        self.telemetry_status_label.setText(value)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        for button in self.manual_buttons:
            button.setEnabled(not busy)
        self._update_telemetry_buttons()
        self._update_movement_buttons()
        self._update_experience_buttons()

        if busy:
            QApplication.setOverrideCursor(Qt.WaitCursor)
        elif QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()

    def _update_telemetry_buttons(self) -> None:
        if not hasattr(self, "start_telemetry_button"):
            return

        self.start_telemetry_button.setEnabled(
            not self.busy and not self.telemetry_running
        )
        self.stop_telemetry_button.setEnabled(
            not self.busy and self.telemetry_running
        )

    def _update_movement_buttons(self) -> None:
        if not hasattr(self, "generate_sequence_button"):
            return

        self.generate_sequence_button.setEnabled(
            not self.busy and not self.sequence_running
        )
        self.execute_sequence_button.setEnabled(
            not self.busy
            and not self.sequence_running
            and self.last_validated_sequence is not None
        )
        self.movement_stop_button.setEnabled(self.sequence_running)

    def _update_experience_buttons(self) -> None:
        if not hasattr(self, "save_experience_button"):
            return

        has_matches = bool(self.experience_matches)
        has_telemetry = self.latest_telemetry is not None
        has_sequence = self._latest_sequence_for_experience() is not None
        has_situation = self._latest_situation_for_experience() is not None
        has_feedback = bool(self.last_trial_feedback_sequence)

        self.save_experience_button.setEnabled(
            not self.busy and has_situation and has_sequence
        )
        self.find_experience_button.setEnabled(not self.busy and has_telemetry)
        self.find_load_best_button.setEnabled(not self.busy and has_telemetry)
        self.load_experience_button.setEnabled(not self.busy and has_matches)
        self.use_feedback_button.setEnabled(not self.busy and has_sequence)
        self.clear_feedback_button.setEnabled(not self.busy and has_feedback)
        self.delete_experiences_button.setEnabled(not self.busy)

    def log_message(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_panel.append(f"[{timestamp}] {message}")

        if message.startswith("ERROR:"):
            self.logger.error(message.removeprefix("ERROR:").strip())
        else:
            self.logger.info(message)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt method name.
        if self.telemetry_receiver is not None:
            self.telemetry_receiver.request_stop()
        if self.telemetry_thread is not None:
            self.telemetry_thread.quit()
            self.telemetry_thread.wait(1000)
        super().closeEvent(event)
