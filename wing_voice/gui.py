from __future__ import annotations
import copy, ipaddress, json, os, re, shutil, socket, subprocess, sys, time
from pathlib import Path
from PySide6.QtCore import Qt, QProcess, QTimer, QSettings
from PySide6.QtGui import QAction, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox,
    QTabWidget, QGroupBox, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QTextEdit, QFileDialog, QMessageBox, QSplitter, QFrame,
    QScrollArea, QPlainTextEdit, QProgressBar, QStackedWidget
)

APP_NAME = "WING Voice Assistant"
DEFAULT_APP = {
    "wakeModelPath": "assets/vosk-model-small-en-us-0.15", "inputDeviceContains": "Dante",
    "inputChannels": [0], "inputSampleRate": 48000, "outputDeviceContains": "Dante",
    "outputChannels": [0], "outputSampleRate": 48000, "mcpGatewayPath": "",
    "writesEnabled": False, "whisperModel": "assets/whisper-base.en", "recordingMaxSeconds": 8,
    "silenceEndSeconds": 1.0, "speechRmsThreshold": 0.008, "wakeSensitivity": 0.65,
    "confirmationTimeoutSeconds": 12, "maxRelativeStepDb": 2.0,
    "maxAbsoluteFaderDb": 6.0, "undoMaxAgeSeconds": 300,
    "meterMonitoringEnabled": False, "meterPollSeconds": 2.0,
    "meterThresholdsDbfs": {"clipAtOrAbove": -1.0, "noSignalAtOrBelow": -60.0, "lowSignalAtOrBelow": -50.0},
    "wingIpAddress": "", "wingOscPort": 2223, "wingDiscoveryPort": 2222,
    "wingMeterTcpPort": 2222, "wingMeterUdpPort": 14135
}
DEFAULT_PROFILES = {"profiles": [
    {"label":"Keys 1", "busIndex":None}, {"label":"Drums", "busIndex":None},
    {"label":"Acoustic", "busIndex":None}, {"label":"IEM 4", "busIndex":None},
    {"label":"IEM 5", "busIndex":None}, {"label":"IEM 6", "busIndex":None}]}
DEFAULT_POLICY = {"wakeWord":"Wing", "ignoreWakeWhileBusy":True, "queueCommands":False,
    "confirmEveryLiveWrite":True, "undoOnlyLastVerifiedChange":True, "undoMaxAgeSeconds":300,
    "meterAlertsReadOnly":True, "automaticCorrections":False}
DEFAULT_TOOL_MAP = {"statusRead":None,"meterRead":None,"busFaderRead":None,"busFaderSet":None,
    "busMuteRead":None,"busMuteSet":None,"notes":"Configure exact tool names and value paths from Inspect MCP Tools. Do not guess."}


def app_support_root() -> Path:
    return Path.home() / "Library" / "Application Support" / "WING Voice Assistant"


def template_root() -> Path | None:
    # PyInstaller build includes the starter project under Resources/assistant_project.
    candidates = []
    if getattr(sys, "_MEIPASS", None): candidates.append(Path(sys._MEIPASS) / "assistant_project")
    candidates.append(Path(__file__).resolve().parents[1])
    for p in candidates:
        if (p / "wing_voice" / "cli.py").exists() and (p / "config").exists(): return p
    return None


def ensure_project_copy() -> Path:
    root = app_support_root() / "project"
    if not (root / "wing_voice" / "cli.py").exists():
        src = template_root()
        if src is None: raise RuntimeError("Could not locate the assistant project files.")
        root.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, root, ignore=shutil.ignore_patterns(".venv", "__pycache__", "*.pyc", "logs", ".DS_Store"), dirs_exist_ok=True)
    (root / "config").mkdir(exist_ok=True)
    defaults = {
        "app.json": DEFAULT_APP,
        "iem-profiles.json": DEFAULT_PROFILES,
        "assistant-policy.json": DEFAULT_POLICY,
        "tool-map.json": DEFAULT_TOOL_MAP,
    }
    for name, data in defaults.items():
        path = root / "config" / name
        if not path.exists(): path.write_text(json.dumps(data, indent=2) + "\n")
    return root


class FieldRow(QWidget):
    def __init__(self, label, widget, help_text=""):
        super().__init__(); layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 8); layout.setSpacing(4)
        self.label = QLabel(label); self.label.setObjectName("fieldLabel"); layout.addWidget(self.label); layout.addWidget(widget)
        if help_text:
            hint = QLabel(help_text); hint.setObjectName("hint"); hint.setWordWrap(True); layout.addWidget(hint)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle(APP_NAME); self.resize(1360, 880); self.setMinimumSize(1080, 720)
        self.settings = QSettings("OpenAI", "WINGVoiceAssistant")
        try:
            self.root = Path(self.settings.value("projectRoot", "") or "") if self.settings.value("projectRoot", "") else ensure_project_copy()
            if not (self.root / "wing_voice" / "cli.py").exists(): self.root = ensure_project_copy()
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, str(e)); raise
        self.proc = QProcess(self); self.proc.setWorkingDirectory(str(self.root)); self.proc.readyReadStandardOutput.connect(self.read_stdout)
        self.proc.readyReadStandardError.connect(self.read_stderr); self.proc.finished.connect(self.process_finished)
        self.setup_proc = QProcess(self); self.setup_proc.setWorkingDirectory(str(self.root)); self.setup_proc.readyReadStandardOutput.connect(self.read_setup_stdout)
        self.setup_proc.readyReadStandardError.connect(self.read_setup_stderr); self.setup_proc.finished.connect(self.setup_finished)
        self.log_buffer = []; self.widgets = {}; self.app_cfg = {}; self.profiles_cfg = {}; self.policy_cfg = {}; self.tool_map_cfg = {}
        self.setStyleSheet(self.stylesheet()); self.build_ui(); self.load_configs(); self.refresh_status()
        self.status_timer = QTimer(self); self.status_timer.timeout.connect(self.refresh_status); self.status_timer.start(1500)

    def stylesheet(self):
        return """
        * { font-family: -apple-system, BlinkMacSystemFont, \"Helvetica Neue\", sans-serif; font-size: 13px; }
        QMainWindow, QWidget { background: #101319; color: #edf2f7; }
        QWidget#sidebar { background: #151a22; border-right: 1px solid #29313d; }
        QLabel#brandMark { background: #203441; color: #9df3dc; border: 1px solid #315565; border-radius: 13px; font-size: 23px; font-weight: 800; }
        QLabel#brandTitle { font-size: 15px; font-weight: 750; color: #f4f8fb; }
        QLabel#brandSubtitle { color: #8393a5; font-size: 10px; letter-spacing: 1px; }
        QLabel#navCaption { color: #68798c; font-size: 10px; font-weight: 800; letter-spacing: 1.5px; padding: 12px 9px 4px 9px; }
        QPushButton#navButton { text-align: left; background: transparent; color: #aab6c5; border: 1px solid transparent; border-radius: 9px; padding: 11px 12px; font-weight: 600; }
        QPushButton#navButton:hover { background: #202834; color: #f2f7fb; }
        QPushButton#navButton:checked { background: #223a3e; color: #a5f3d7; border: 1px solid #2d5657; }
        QFrame#topbar { background: #101319; border-bottom: 1px solid #252d38; }
        QLabel#title { font-size: 24px; font-weight: 750; color: #f5f8fb; }
        QLabel#subtitle { color: #8d9bac; font-size: 11px; }
        QLabel#pageEyebrow { color: #7fdac8; font-size: 10px; font-weight: 800; letter-spacing: 1.5px; }
        QLabel#fieldLabel { color: #dfe7ef; font-weight: 650; }
        QLabel#hint { color: #8795a5; font-size: 11px; }
        QLabel#metric { font-size: 20px; font-weight: 750; color: #f3f8fb; }
        QLabel#good { color: #8be4c3; font-weight: 700; }
        QLabel#warn { color: #f5c875; font-weight: 700; }
        QTabWidget::pane { border: 1px solid #30343c; border-radius: 9px; }
        QGroupBox { background: #171d26; border: 1px solid #2b3542; border-radius: 13px; margin-top: 13px; padding: 17px 14px 13px 14px; font-weight: 650; }
        QGroupBox::title { subcontrol-origin: margin; left: 13px; padding: 0 7px; color: #dce5ee; }
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit, QTableWidget { background: #0e1218; color: #edf2f7; border: 1px solid #303b49; border-radius: 8px; padding: 9px; selection-background-color: #285c58; }
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus { border: 1px solid #62cdb6; }
        QPushButton { background: #222a35; color: #e7eef6; border: 1px solid #364251; border-radius: 9px; padding: 10px 14px; font-weight: 650; }
        QPushButton:hover { background: #2a3542; border-color: #4a5a6c; }
        QPushButton:disabled { color: #687584; background: #1b2028; border-color: #2a3039; }
        QPushButton#primary { background: #9af0d4; color: #10211f; border: 1px solid #9af0d4; }
        QPushButton#primary:hover { background: #b8f8e5; }
        QPushButton#danger { background: #48272f; color: #ffdfe4; border: 1px solid #75404b; }
        QPushButton#quiet { background: transparent; border-color: #303b49; }
        QCheckBox { spacing: 9px; color: #d9e2eb; }
        QCheckBox::indicator { width: 17px; height: 17px; border-radius: 5px; border: 1px solid #485668; background: #0f141b; }
        QCheckBox::indicator:checked { background: #8de9ce; border-color: #8de9ce; }
        QHeaderView::section { background: #202833; padding: 9px; border: none; color: #cbd6e2; }
        QScrollArea { border: none; background: transparent; }
        QProgressBar { border: 1px solid #353b44; border-radius: 5px; background: #101216; text-align: center; }
        QProgressBar::chunk { background: #73d4bb; border-radius: 4px; }
        """

    def build_ui(self):
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1080, 720)
        icon_path = Path(__file__).resolve().parents[1] / "assets" / "AppIcon.svg"
        if icon_path.exists(): self.setWindowIcon(QIcon(str(icon_path)))
        central = QWidget(); self.setCentralWidget(central)
        root_layout = QHBoxLayout(central); root_layout.setContentsMargins(0, 0, 0, 0); root_layout.setSpacing(0)

        sidebar = QWidget(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(226)
        side = QVBoxLayout(sidebar); side.setContentsMargins(15, 20, 14, 16); side.setSpacing(7)
        brand_row = QHBoxLayout(); brand_row.setSpacing(10)
        mark = QLabel("〰"); mark.setObjectName("brandMark"); mark.setAlignment(Qt.AlignCenter); mark.setFixedSize(43, 43); brand_row.addWidget(mark)
        brand_text = QVBoxLayout(); brand_text.setSpacing(2)
        brand = QLabel("WING Voice"); brand.setObjectName("brandTitle"); brand_text.addWidget(brand)
        brand_sub = QLabel("LIVE AUDIO CONTROL"); brand_sub.setObjectName("brandSubtitle"); brand_text.addWidget(brand_sub)
        brand_row.addLayout(brand_text); brand_row.addStretch(); side.addLayout(brand_row)
        side.addSpacing(18)
        cap = QLabel("WORKSPACE"); cap.setObjectName("navCaption"); side.addWidget(cap)

        self.pages = QStackedWidget(); self.nav_buttons = []
        page_defs = [
            ("◫", "Overview", self.make_overview),
            ("⌁", "Audio & Dante", self.make_audio_tab),
            ("⌖", "WING Connection", self.make_wing_tab),
            ("◉", "IEM Profiles", self.make_profiles_tab),
            ("◌", "Voice & Safety", self.make_voice_tab),
            ("▥", "Meter Monitor", self.make_meter_tab),
            ("⌘", "MCP Tools", self.make_toolmap_tab),
            ("≡", "Logs & Diagnostics", self.make_logs_tab),
        ]
        self.page_names = []
        for idx, (symbol, name, builder) in enumerate(page_defs):
            btn = QPushButton(f"{symbol}     {name}"); btn.setObjectName("navButton"); btn.setCheckable(True); btn.setAutoExclusive(True)
            btn.clicked.connect(lambda checked=False, i=idx: self.pages.setCurrentIndex(i))
            side.addWidget(btn); self.nav_buttons.append(btn); self.page_names.append(name)
            self.pages.addWidget(builder())
        side.addStretch()
        safety_card = QFrame(); safety_card.setStyleSheet("QFrame { background:#1a252b; border:1px solid #2c4749; border-radius:11px; }")
        safety_layout = QVBoxLayout(safety_card); safety_layout.setContentsMargins(12, 12, 12, 12); safety_layout.setSpacing(5)
        safety_title = QLabel("●  SAFE BY DEFAULT"); safety_title.setStyleSheet("color:#9af0d4;font-size:10px;font-weight:800;letter-spacing:1px;border:none;background:transparent;"); safety_layout.addWidget(safety_title)
        safety_note = QLabel("Live writes start disabled. Commands are never queued."); safety_note.setWordWrap(True); safety_note.setStyleSheet("color:#a9bac7;font-size:11px;border:none;background:transparent;"); safety_layout.addWidget(safety_note)
        side.addWidget(safety_card)
        side.addSpacing(8)
        root_layout.addWidget(sidebar)

        content = QWidget(); content_layout = QVBoxLayout(content); content_layout.setContentsMargins(0, 0, 0, 0); content_layout.setSpacing(0)
        topbar = QFrame(); topbar.setObjectName("topbar"); top_layout = QHBoxLayout(topbar); top_layout.setContentsMargins(26, 18, 26, 18); top_layout.setSpacing(12)
        title_col = QVBoxLayout(); title_col.setSpacing(4)
        self.page_title = QLabel("Overview"); self.page_title.setObjectName("title"); title_col.addWidget(self.page_title)
        self.page_subtitle = QLabel("Your local voice-control workspace"); self.page_subtitle.setObjectName("subtitle"); title_col.addWidget(self.page_subtitle)
        top_layout.addLayout(title_col); top_layout.addStretch()
        self.status_badge = QLabel("● STOPPED"); self.status_badge.setObjectName("warn"); self.status_badge.setStyleSheet("padding:7px 10px;background:#30291d;border:1px solid #55462c;border-radius:8px;"); top_layout.addWidget(self.status_badge, 0, Qt.AlignVCenter)
        self.start_btn = QPushButton("Start listening"); self.start_btn.setObjectName("primary"); self.start_btn.clicked.connect(self.start_assistant); top_layout.addWidget(self.start_btn)
        self.stop_btn = QPushButton("Stop"); self.stop_btn.setObjectName("danger"); self.stop_btn.setEnabled(False); self.stop_btn.clicked.connect(self.stop_assistant); top_layout.addWidget(self.stop_btn)
        content_layout.addWidget(topbar)
        content_layout.addWidget(self.pages, 1)

        footer = QFrame(); footer.setObjectName("topbar"); footer_layout = QHBoxLayout(footer); footer_layout.setContentsMargins(22, 10, 22, 10); footer_layout.setSpacing(9)
        self.project_label = QLabel(f"PROJECT  ·  {self.root}"); self.project_label.setObjectName("subtitle"); footer_layout.addWidget(self.project_label, 1)
        validate_btn = QPushButton("Validate setup"); validate_btn.setObjectName("quiet"); validate_btn.clicked.connect(self.validate_setup); footer_layout.addWidget(validate_btn)
        self.save_btn = QPushButton("Save changes"); self.save_btn.setObjectName("primary"); self.save_btn.clicked.connect(self.save_configs); footer_layout.addWidget(self.save_btn)
        content_layout.addWidget(footer); root_layout.addWidget(content, 1)
        self.nav_buttons[0].setChecked(True)
        self.pages.currentChanged.connect(self.on_page_changed)

    def on_page_changed(self, index):
        if 0 <= index < len(self.page_names):
            self.page_title.setText(self.page_names[index])
            subtitles = ["Your local voice-control workspace", "Route talkback audio in and assistant audio out", "Connect safely to the WING Rack", "Map each performer to a verified bus", "Wake word, recognition and confirmation rules", "Read-only signal health checks", "Map verified MCP tools without guessing", "Runtime output and setup diagnostics"]
            self.page_subtitle.setText(subtitles[index])
            self.nav_buttons[index].setChecked(True)

    def scroll_page(self):
        scroll = QScrollArea(); scroll.setWidgetResizable(True); inner = QWidget(); layout = QVBoxLayout(inner); layout.setContentsMargins(16,16,16,16); layout.setSpacing(12); scroll.setWidget(inner); return scroll, layout

    def make_overview(self):
        page, layout = self.scroll_page()
        hero = QGroupBox("System overview"); h = QVBoxLayout(hero)
        intro = QLabel("Configure the WING network target, Dante channels, six IEM profiles and voice safety rules here. The assistant and WING MCP gateway remain separate processes."); intro.setWordWrap(True); intro.setObjectName("subtitle"); h.addWidget(intro)
        cards = QHBoxLayout()
        for title, key in [("Dante input", "overview_input"),("Dante output", "overview_output"),("WING IP", "overview_ip"),("Live writes", "overview_writes")]:
            box = QGroupBox(title); bl = QVBoxLayout(box); value = QLabel("Not configured"); value.setObjectName("metric"); value.setWordWrap(True); bl.addWidget(value); self.widgets[key] = value; cards.addWidget(box)
        h.addLayout(cards); layout.addWidget(hero)
        routing = QGroupBox("Signal flow — keep the return out of the wake bus"); rl = QHBoxLayout(routing)
        for text in ["6 talkback mics\nDante listening bus", "→", "Mac assistant\nWake · STT · TTS", "→", "WING MCP\nTyped controls", "→", "Dedicated WING input\nAll 6 IEMs"]:
            label = QLabel(text); label.setAlignment(Qt.AlignCenter); label.setWordWrap(True); label.setMinimumHeight(68)
            if text != "→": label.setStyleSheet("background:#22272e;border:1px solid #373e48;border-radius:8px;padding:8px;font-weight:600;")
            else: label.setStyleSheet("color:#81d9a4;font-size:20px;font-weight:bold;")
            rl.addWidget(label, 1 if text != "→" else 0)
        layout.addWidget(routing)
        safety = QGroupBox("Safety state"); sl = QVBoxLayout(safety)
        self.safety_summary = QLabel("Writes disabled by default. Every live write requires spoken confirmation. Commands are not queued while busy."); self.safety_summary.setWordWrap(True); sl.addWidget(self.safety_summary)
        actions = QHBoxLayout(); b = QPushButton("Install / repair runtime"); b.clicked.connect(self.install_runtime); actions.addWidget(b)
        b = QPushButton("Detect Dante devices"); b.clicked.connect(self.detect_devices); actions.addWidget(b)
        b = QPushButton("Inspect MCP tools"); b.clicked.connect(self.inspect_tools); actions.addWidget(b)
        b = QPushButton("Open project folder"); b.clicked.connect(lambda: self.open_path(self.root)); actions.addWidget(b); sl.addLayout(actions); layout.addWidget(safety)
        profile_box = QGroupBox("Configured IEM profiles"); pl = QHBoxLayout(profile_box); self.profile_summary = []
        for _ in range(6):
            lab = QLabel("Unconfigured\nBus —"); lab.setAlignment(Qt.AlignCenter); lab.setWordWrap(True); lab.setMinimumHeight(52); lab.setStyleSheet("background:#22272e;border:1px solid #373e48;border-radius:8px;padding:7px;"); self.profile_summary.append(lab); pl.addWidget(lab)
        layout.addWidget(profile_box); layout.addStretch(); return page

    def make_audio_tab(self):
        page, layout = self.scroll_page(); box = QGroupBox("Dante Virtual Soundcard / CoreAudio"); form = QFormLayout(box); form.setVerticalSpacing(12)
        self.widgets['inputDeviceContains'] = QLineEdit(); form.addRow("Input device name contains", self.widgets['inputDeviceContains'])
        self.widgets['inputChannels'] = QLineEdit(); form.addRow("Input channels (1-based)", self.widgets['inputChannels'])
        self.widgets['inputSampleRate'] = QComboBox(); self.widgets['inputSampleRate'].addItems(["44100","48000","96000"]); form.addRow("Input sample rate", self.widgets['inputSampleRate'])
        self.widgets['outputDeviceContains'] = QLineEdit(); form.addRow("Output device name contains", self.widgets['outputDeviceContains'])
        self.widgets['outputChannels'] = QLineEdit(); form.addRow("Output channels (1-based)", self.widgets['outputChannels'])
        self.widgets['outputSampleRate'] = QComboBox(); self.widgets['outputSampleRate'].addItems(["44100","48000","96000"]); form.addRow("Output sample rate", self.widgets['outputSampleRate'])
        layout.addWidget(box)
        note = QLabel("Channel numbers are shown 1-based for people; the app stores them 0-based. Select the combined talkback bus channels as input. Select the dedicated assistant-return channel as output. Actual channel count depends on your DVS license and settings."); note.setWordWrap(True); note.setObjectName("hint"); layout.addWidget(note)
        row = QHBoxLayout(); b = QPushButton("Detect available audio devices"); b.clicked.connect(self.detect_devices); row.addWidget(b); b = QPushButton("Show device list in Logs"); b.clicked.connect(self.detect_devices); row.addWidget(b); layout.addLayout(row); layout.addStretch(); return page

    def make_wing_tab(self):
        page, layout = self.scroll_page(); box = QGroupBox("WING Rack network target"); form = QFormLayout(box); form.setVerticalSpacing(11)
        self.widgets['wingIpAddress'] = QLineEdit(); self.widgets['wingIpAddress'].setPlaceholderText("e.g. 192.168.1.50"); form.addRow("WING IP address", self.widgets['wingIpAddress'])
        for key, label in [("wingOscPort","OSC port"),("wingDiscoveryPort","Discovery port"),("wingMeterTcpPort","Meter TCP port"),("wingMeterUdpPort","Meter UDP port")]:
            spin = QSpinBox(); spin.setRange(1,65535); self.widgets[key] = spin; form.addRow(label, spin)
        layout.addWidget(box)
        paths = QGroupBox("Connection paths"); pf = QFormLayout(paths)
        self.widgets['mcpGatewayPath'] = QLineEdit(); browse = QPushButton("Browse…"); browse.clicked.connect(lambda: self.browse_directory('mcpGatewayPath'))
        row = QHBoxLayout(); row.addWidget(self.widgets['mcpGatewayPath'],1); row.addWidget(browse); pf.addRow("Existing WING Rack plugin folder", row)
        self.widgets['serverPath'] = QLineEdit(); browse2 = QPushButton("Browse…"); browse2.clicked.connect(lambda: self.browse_directory('serverPath'))
        row2 = QHBoxLayout(); row2.addWidget(self.widgets['serverPath'],1); row2.addWidget(browse2); pf.addRow("Upstream wing-mcp-server folder", row2)
        self.widgets['configPath'] = QLineEdit(); browse3 = QPushButton("Browse…"); browse3.clicked.connect(lambda: self.browse_file('configPath'))
        row3 = QHBoxLayout(); row3.addWidget(self.widgets['configPath'],1); row3.addWidget(browse3); pf.addRow("Upstream data/config.json", row3)
        layout.addWidget(paths)
        gate = QGroupBox("Independent write safety gates"); gl = QVBoxLayout(gate)
        self.widgets['writesEnabled'] = QCheckBox("Allow voice assistant to request live mixer writes")
        self.widgets['gatewayWritesEnabled'] = QCheckBox("Allow the WING MCP gateway to pass approved writes")
        self.widgets['showMode'] = QCheckBox("Enable upstream show mode (extra confirmation required by upstream server)")
        gl.addWidget(self.widgets['writesEnabled']); gl.addWidget(self.widgets['gatewayWritesEnabled']); gl.addWidget(self.widgets['showMode'])
        warning = QLabel("Keep both write gates off during setup. Changing the IP edits the upstream server config at the selected configPath, under plugins.wing.host. Stop the assistant/server before saving connection changes."); warning.setWordWrap(True); warning.setObjectName("hint"); gl.addWidget(warning); layout.addWidget(gate); layout.addStretch(); return page

    def make_profiles_tab(self):
        page, layout = self.scroll_page(); box = QGroupBox("Six instrument-labelled IEM profiles"); bl = QVBoxLayout(box)
        self.profile_table = QTableWidget(6,2); self.profile_table.setHorizontalHeaderLabels(["IEM label", "Verified WING bus index"]); self.profile_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch); self.profile_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents); self.profile_table.verticalHeader().setVisible(False); self.profile_table.setMinimumHeight(300); bl.addWidget(self.profile_table)
        hint = QLabel("Bus indices are passed to the MCP tool mapping; verify each one against the live WING MCP server/console. Blank means unconfigured. No bus index is guessed."); hint.setObjectName("hint"); hint.setWordWrap(True); bl.addWidget(hint); layout.addWidget(box); layout.addStretch(); return page

    def make_voice_tab(self):
        page, layout = self.scroll_page(); access = QGroupBox("Wake word & speech recognition"); f = QFormLayout(access); f.setVerticalSpacing(11)
        self.widgets['wakeModelPath'] = QLineEdit(); b = QPushButton("Browse…"); b.clicked.connect(lambda: self.browse_directory('wakeModelPath')); row = QHBoxLayout(); row.addWidget(self.widgets['wakeModelPath'],1); row.addWidget(b); f.addRow("Open-source Vosk wake model folder", row)
        self.widgets['whisperModel'] = QComboBox(); self.widgets['whisperModel'].addItems(["assets/whisper-base.en", "tiny.en", "base.en", "small.en", "medium.en"]); f.addRow("Local speech model", self.widgets['whisperModel'])
        self.widgets['wakeSensitivity'] = self.double_field(0.1,0.99,0.05); f.addRow("Wake sensitivity", self.widgets['wakeSensitivity'])
        self.widgets['recordingMaxSeconds'] = self.int_field(2,20); f.addRow("Maximum utterance length (seconds)", self.widgets['recordingMaxSeconds'])
        self.widgets['silenceEndSeconds'] = self.double_field(0.2,3.0,0.1); f.addRow("End utterance after silence (seconds)", self.widgets['silenceEndSeconds'])
        self.widgets['speechRmsThreshold'] = self.double_field(0.0001,0.1,0.001,5); f.addRow("Speech RMS threshold", self.widgets['speechRmsThreshold'])
        layout.addWidget(access)
        safe = QGroupBox("Voice command safety"); sf = QFormLayout(safe); sf.setVerticalSpacing(10)
        self.widgets['confirmationTimeoutSeconds'] = self.int_field(3,60); sf.addRow("Confirmation timeout (seconds)", self.widgets['confirmationTimeoutSeconds'])
        self.widgets['maxRelativeStepDb'] = self.double_field(0.1,6.0,0.1); sf.addRow("Maximum relative change per command (dB)", self.widgets['maxRelativeStepDb'])
        self.widgets['maxAbsoluteFaderDb'] = self.double_field(-20,10,0.5); sf.addRow("Maximum absolute fader level (dB)", self.widgets['maxAbsoluteFaderDb'])
        self.widgets['undoMaxAgeSeconds'] = self.int_field(10,1800); sf.addRow("Undo window (seconds)", self.widgets['undoMaxAgeSeconds'])
        self.widgets['queueCommands'] = QCheckBox("Queue commands while assistant is busy (unsafe; must remain off)"); self.widgets['queueCommands'].setEnabled(False); self.widgets['queueCommands'].setChecked(False); sf.addRow("Command queue", self.widgets['queueCommands'])
        self.widgets['confirmEveryLiveWrite'] = QCheckBox("Require spoken confirmation for every live write"); self.widgets['confirmEveryLiveWrite'].setChecked(True); sf.addRow("Confirm writes", self.widgets['confirmEveryLiveWrite'])
        self.widgets['ignoreWakeWhileBusy'] = QCheckBox("Ignore wake word while recording, processing or speaking"); self.widgets['ignoreWakeWhileBusy'].setChecked(True); sf.addRow("Busy behaviour", self.widgets['ignoreWakeWhileBusy'])
        self.widgets['undoOnlyLastVerifiedChange'] = QCheckBox("Undo only last verified change, after re-reading current value"); self.widgets['undoOnlyLastVerifiedChange'].setChecked(True); sf.addRow("Undo policy", self.widgets['undoOnlyLastVerifiedChange'])
        layout.addWidget(safe); layout.addStretch(); return page

    def make_meter_tab(self):
        page, layout = self.scroll_page(); box = QGroupBox("Read-only meter alerts"); f = QFormLayout(box); f.setVerticalSpacing(12)
        self.widgets['meterMonitoringEnabled'] = QCheckBox("Enable meter monitoring (requires configured MCP meter tool)"); f.addRow("Monitoring", self.widgets['meterMonitoringEnabled'])
        self.widgets['meterPollSeconds'] = self.double_field(0.5,30,0.5); f.addRow("Poll interval (seconds)", self.widgets['meterPollSeconds'])
        self.widgets['clipAtOrAbove'] = self.double_field(-24,0,0.5); f.addRow("Clip warning at/above (dBFS)", self.widgets['clipAtOrAbove'])
        self.widgets['noSignalAtOrBelow'] = self.double_field(-100,-20,1); f.addRow("No signal at/below (dBFS)", self.widgets['noSignalAtOrBelow'])
        self.widgets['lowSignalAtOrBelow'] = self.double_field(-100,-20,1); f.addRow("Low signal at/below (dBFS)", self.widgets['lowSignalAtOrBelow'])
        layout.addWidget(box); note = QLabel("Meter values must be verified to be dBFS in the upstream MCP response. These thresholds do not change any mixer controls. Meter monitoring remains off until a compatible read-only meter mapping is configured."); note.setWordWrap(True); note.setObjectName("hint"); layout.addWidget(note); layout.addStretch(); return page

    def make_toolmap_tab(self):
        page, layout = self.scroll_page(); box = QGroupBox("Exact MCP tool mapping (JSON)"); bl = QVBoxLayout(box)
        self.toolmap_editor = QPlainTextEdit(); self.toolmap_editor.setMinimumHeight(370); self.toolmap_editor.setPlaceholderText("Configure only after inspecting the live MCP tools."); bl.addWidget(self.toolmap_editor)
        row = QHBoxLayout(); b = QPushButton("Load from config"); b.clicked.connect(self.load_toolmap_editor); row.addWidget(b); b = QPushButton("Validate JSON"); b.clicked.connect(self.validate_toolmap_json); row.addWidget(b); b = QPushButton("Inspect MCP tools"); b.clicked.connect(self.inspect_tools); row.addWidget(b); bl.addLayout(row)
        note = QLabel("Tool names and argument schemas vary by upstream server version. Inspect the live tools first; do not guess names or value paths. This editor writes config/tool-map.json used by the voice assistant."); note.setObjectName("hint"); note.setWordWrap(True); bl.addWidget(note); layout.addWidget(box); layout.addStretch(); return page

    def make_logs_tab(self):
        page, layout = self.scroll_page(); box = QGroupBox("Assistant output / diagnostics"); bl = QVBoxLayout(box)
        self.log_view = QPlainTextEdit(); self.log_view.setReadOnly(True); self.log_view.setMaximumBlockCount(3000); bl.addWidget(self.log_view)
        row = QHBoxLayout(); b = QPushButton("Clear log"); b.clicked.connect(self.log_view.clear); row.addWidget(b); b = QPushButton("Export log…"); b.clicked.connect(self.export_log); row.addWidget(b); layout.addWidget(box); layout.addStretch(); return page

    def int_field(self, lo, hi):
        w=QSpinBox(); w.setRange(lo,hi); return w
    def double_field(self, lo, hi, step, decimals=2):
        w=QDoubleSpinBox(); w.setRange(lo,hi); w.setSingleStep(step); w.setDecimals(decimals); return w

    def load_configs(self):
        self.app_cfg = self.read_json("config/app.json", DEFAULT_APP)
        self.profiles_cfg = self.read_json("config/iem-profiles.json", DEFAULT_PROFILES)
        self.policy_cfg = self.read_json("config/assistant-policy.json", DEFAULT_POLICY)
        self.tool_map_cfg = self.read_json("config/tool-map.json", DEFAULT_TOOL_MAP)
        a=self.app_cfg; self.set_text('inputDeviceContains',a.get('inputDeviceContains','Dante')); self.set_text('outputDeviceContains',a.get('outputDeviceContains','Dante'))
        self.set_text('inputChannels',self.channels_to_ui(a.get('inputChannels',[0]))); self.set_text('outputChannels',self.channels_to_ui(a.get('outputChannels',[0])))
        self.set_combo('inputSampleRate',a.get('inputSampleRate',48000)); self.set_combo('outputSampleRate',a.get('outputSampleRate',48000))
        self.set_text('wingIpAddress',a.get('wingIpAddress','')); self.set_text('mcpGatewayPath',a.get('mcpGatewayPath',''))
        for key, default in [('wingOscPort',2223),('wingDiscoveryPort',2222),('wingMeterTcpPort',2222),('wingMeterUdpPort',14135)]: self.widgets[key].setValue(int(a.get(key,default)))
        gateway=Path(a.get('mcpGatewayPath','')).expanduser() if a.get('mcpGatewayPath') else None
        local_cfg = self.read_external_json(gateway/'config'/'local.json') if gateway else {}
        self.set_text('serverPath',local_cfg.get('serverPath','')); self.set_text('configPath',local_cfg.get('configPath',''))
        self.widgets['writesEnabled'].setChecked(bool(a.get('writesEnabled',False)))
        self.widgets['gatewayWritesEnabled'].setChecked(bool(local_cfg.get('enableWrites',False)))
        upstream=self.read_external_json(Path(local_cfg['configPath'])) if local_cfg.get('configPath') else {}
        wing=upstream.get('plugins',{}).get('wing',{}) if isinstance(upstream,dict) else {}
        self.widgets['showMode'].setChecked(bool(wing.get('showMode',False)))
        for key in ['wakeModelPath','whisperModel']:
            value=a.get(key,DEFAULT_APP.get(key,'')); self.set_text(key,value) if key!='whisperModel' else self.set_combo(key,value)
        for key, default in [('wakeSensitivity',.65),('recordingMaxSeconds',8),('silenceEndSeconds',1.0),('speechRmsThreshold',.008),('confirmationTimeoutSeconds',12),('maxRelativeStepDb',2.0),('maxAbsoluteFaderDb',6.0),('undoMaxAgeSeconds',300),('meterPollSeconds',2.0)]: self.widgets[key].setValue(float(a.get(key,default)))
        self.widgets['meterMonitoringEnabled'].setChecked(bool(a.get('meterMonitoringEnabled',False)))
        thresholds=a.get('meterThresholdsDbfs',{}); self.widgets['clipAtOrAbove'].setValue(float(thresholds.get('clipAtOrAbove',-1))); self.widgets['noSignalAtOrBelow'].setValue(float(thresholds.get('noSignalAtOrBelow',-60))); self.widgets['lowSignalAtOrBelow'].setValue(float(thresholds.get('lowSignalAtOrBelow',-50)))
        for key in ['queueCommands','confirmEveryLiveWrite','ignoreWakeWhileBusy','undoOnlyLastVerifiedChange']:
            default=DEFAULT_POLICY.get(key,False); self.widgets[key].setChecked(bool(self.policy_cfg.get(key,default)))
        self.profile_table.setRowCount(6)
        profs=self.profiles_cfg.get('profiles',[])
        for i in range(6):
            p=profs[i] if i<len(profs) else {"label":f"IEM {i+1}","busIndex":None}
            self.profile_table.setItem(i,0,QTableWidgetItem(str(p.get('label',''))))
            self.profile_table.setItem(i,1,QTableWidgetItem('' if p.get('busIndex') is None else str(p.get('busIndex'))))
        self.toolmap_editor.setPlainText(json.dumps(self.tool_map_cfg,indent=2,ensure_ascii=False)); self.refresh_status()

    def set_text(self,key,value): self.widgets[key].setText(str(value or ''))
    def set_combo(self,key,value):
        idx=self.widgets[key].findText(str(value));
        if idx<0: self.widgets[key].addItem(str(value)); idx=self.widgets[key].findText(str(value))
        self.widgets[key].setCurrentIndex(idx)
    @staticmethod
    def channels_to_ui(values): return ', '.join(str(int(x)+1) for x in values)
    @staticmethod
    def parse_channels(value):
        parts=[p.strip() for p in value.split(',') if p.strip()]
        if not parts: raise ValueError('Enter at least one channel number (1-based).')
        vals=[]
        for p in parts:
            if not p.isdigit() or int(p)<1: raise ValueError(f'Invalid channel number: {p}')
            vals.append(int(p)-1)
        if len(set(vals))!=len(vals): raise ValueError('Channel list contains duplicates.')
        return vals

    def read_json(self, rel, default):
        path=self.root/rel
        if not path.exists(): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(default,indent=2)+'\n'); return copy.deepcopy(default)
        try: return json.loads(path.read_text())
        except Exception as e: QMessageBox.warning(self,'Invalid config',f'Could not read {path}: {e}'); return copy.deepcopy(default)
    def read_external_json(self,path):
        try: return json.loads(path.read_text()) if path and path.exists() else {}
        except Exception: return {}
    def write_json(self,path,data):
        path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n'); os.replace(tmp,path)

    def save_configs(self, silent=False):
        if self.proc.state()!=QProcess.NotRunning:
            if not silent: QMessageBox.warning(self,'Assistant is running','Stop the assistant before saving configuration.')
            return False
        try:
            a=self.app_cfg.copy()
            a.update({
                'inputDeviceContains':self.widgets['inputDeviceContains'].text().strip(), 'inputChannels':self.parse_channels(self.widgets['inputChannels'].text()),
                'inputSampleRate':int(self.widgets['inputSampleRate'].currentText()), 'outputDeviceContains':self.widgets['outputDeviceContains'].text().strip(),
                'outputChannels':self.parse_channels(self.widgets['outputChannels'].text()), 'outputSampleRate':int(self.widgets['outputSampleRate'].currentText()),
                'wingIpAddress':self.widgets['wingIpAddress'].text().strip(), 'mcpGatewayPath':self.widgets['mcpGatewayPath'].text().strip(),
                'wakeModelPath':self.widgets['wakeModelPath'].text().strip(),
                'whisperModel':self.widgets['whisperModel'].currentText(), 'wakeSensitivity':self.widgets['wakeSensitivity'].value(),
                'recordingMaxSeconds':self.widgets['recordingMaxSeconds'].value(), 'silenceEndSeconds':self.widgets['silenceEndSeconds'].value(),
                'speechRmsThreshold':self.widgets['speechRmsThreshold'].value(), 'confirmationTimeoutSeconds':self.widgets['confirmationTimeoutSeconds'].value(),
                'maxRelativeStepDb':self.widgets['maxRelativeStepDb'].value(), 'maxAbsoluteFaderDb':self.widgets['maxAbsoluteFaderDb'].value(),
                'undoMaxAgeSeconds':self.widgets['undoMaxAgeSeconds'].value(), 'writesEnabled':self.widgets['writesEnabled'].isChecked(),
                'meterMonitoringEnabled':self.widgets['meterMonitoringEnabled'].isChecked(), 'meterPollSeconds':self.widgets['meterPollSeconds'].value(),
                'meterThresholdsDbfs':{'clipAtOrAbove':self.widgets['clipAtOrAbove'].value(),'noSignalAtOrBelow':self.widgets['noSignalAtOrBelow'].value(),'lowSignalAtOrBelow':self.widgets['lowSignalAtOrBelow'].value()},
            })
            if not a['inputDeviceContains'] or not a['outputDeviceContains']: raise ValueError('Audio device name filters cannot be empty.')
            if a['wingIpAddress']:
                try: ipaddress.ip_address(a['wingIpAddress'])
                except ValueError: raise ValueError('Enter a valid IPv4 or IPv6 address for the WING IP.')
            profiles=[]
            for i in range(6):
                label=(self.profile_table.item(i,0).text() if self.profile_table.item(i,0) else '').strip()
                bus=(self.profile_table.item(i,1).text() if self.profile_table.item(i,1) else '').strip()
                if not label: raise ValueError(f'IEM profile {i+1} needs a label.')
                bus_index=None
                if bus:
                    if not re.fullmatch(r'\d+',bus): raise ValueError(f'Bus index for {label} must be a non-negative integer or blank.')
                    bus_index=int(bus)
                profiles.append({'label':label,'busIndex':bus_index})
            if len({p['label'].casefold() for p in profiles}) != 6: raise ValueError('IEM profile labels must be unique.')
            policy={**self.policy_cfg,'wakeWord':'Wing','ignoreWakeWhileBusy':self.widgets['ignoreWakeWhileBusy'].isChecked(),'queueCommands':False,
                    'confirmEveryLiveWrite':self.widgets['confirmEveryLiveWrite'].isChecked(),'undoOnlyLastVerifiedChange':self.widgets['undoOnlyLastVerifiedChange'].isChecked(),
                    'undoMaxAgeSeconds':a['undoMaxAgeSeconds'],'meterAlertsReadOnly':True,'automaticCorrections':False}
            if not policy['confirmEveryLiveWrite']: raise ValueError('Safety policy requires confirmation for every live write.')
            if not policy['ignoreWakeWhileBusy']: raise ValueError('Wake-word detection must remain disabled while the assistant is busy.')
            if not policy['undoOnlyLastVerifiedChange']: raise ValueError('Undo must only reverse the last verified change.')
            toolmap=json.loads(self.toolmap_editor.toPlainText())
            gateway=Path(a['mcpGatewayPath']).expanduser().resolve() if a['mcpGatewayPath'] else None
            server_path=self.widgets['serverPath'].text().strip(); config_path=self.widgets['configPath'].text().strip()
            local_cfg=None; upstream=None
            if gateway:
                if not gateway.is_dir(): raise ValueError('Existing WING MCP plugin folder does not exist.')
                if not server_path or not config_path: raise ValueError('Set the upstream server folder and its data/config.json path.')
                server_path=str(Path(server_path).expanduser().resolve()); config_path=str(Path(config_path).expanduser().resolve())
                if not Path(server_path,'dist','cli.js').is_file(): raise ValueError('Cannot find dist/cli.js in the upstream server folder. Build wing-mcp-server first.')
                if not Path(config_path).is_file(): raise ValueError('The selected upstream data/config.json does not exist yet. Start/configure the upstream server once, then select its config file.')
                local_cfg=self.read_external_json(gateway/'config'/'local.json') or {}
                local_cfg.update({'serverPath':server_path,'configPath':config_path,'enableWrites':self.widgets['gatewayWritesEnabled'].isChecked()})
                upstream=self.read_external_json(Path(config_path))
                if not isinstance(upstream,dict): raise ValueError('Upstream server config must be a JSON object.')
                upstream.setdefault('plugins',{}).setdefault('wing',{})
                wing=upstream['plugins']['wing']; wing['host']=a['wingIpAddress']; wing['oscPort']=self.widgets['wingOscPort'].value(); wing['discoveryPort']=self.widgets['wingDiscoveryPort'].value(); wing['meterTcpPort']=self.widgets['wingMeterTcpPort'].value(); wing['meterUdpPort']=self.widgets['wingMeterUdpPort'].value(); wing['showMode']=self.widgets['showMode'].isChecked()
            self.write_json(self.root/'config'/'app.json',a); self.write_json(self.root/'config'/'iem-profiles.json',{'profiles':profiles}); self.write_json(self.root/'config'/'assistant-policy.json',policy); self.write_json(self.root/'config'/'tool-map.json',toolmap)
            if local_cfg is not None:
                self.write_json(gateway/'config'/'local.json',local_cfg)
                upstream_path=Path(config_path)
                shutil.copy2(upstream_path, upstream_path.with_suffix(upstream_path.suffix + '.wing-assistant.bak'))
                self.write_json(upstream_path,upstream)
            self.app_cfg,self.profiles_cfg,self.policy_cfg,self.tool_map_cfg=a,{'profiles':profiles},policy,toolmap
            self.settings.setValue('projectRoot',str(self.root)); self.log(f'Configuration saved to {self.root / "config"}.')
            if not silent: QMessageBox.information(self,'Configuration saved','Settings saved. Both live-write gates remain independently controlled. If you changed the WING IP or ports, restart the upstream server before testing.')
            self.refresh_status(); return True
        except Exception as e:
            QMessageBox.critical(self,'Could not save configuration',str(e)); return False

    def refresh_status(self):
        running=self.proc.state()!=QProcess.NotRunning
        self.status_badge.setText('● LISTENING / ACTIVE' if running else '● STOPPED'); self.status_badge.setObjectName('good' if running else 'warn'); self.status_badge.style().unpolish(self.status_badge); self.status_badge.style().polish(self.status_badge)
        self.start_btn.setEnabled(not running); self.stop_btn.setEnabled(running)
        a=self.app_cfg or {}
        self.widgets['overview_input'].setText(f"{a.get('inputDeviceContains','Dante')} · {self.channels_to_ui(a.get('inputChannels',[0]))}")
        self.widgets['overview_output'].setText(f"{a.get('outputDeviceContains','Dante')} · {self.channels_to_ui(a.get('outputChannels',[0]))}")
        self.widgets['overview_ip'].setText(a.get('wingIpAddress') or 'Not set'); self.widgets['overview_writes'].setText('ENABLED' if a.get('writesEnabled') else 'DISABLED')
        profs=(self.profiles_cfg or {}).get('profiles',[])
        for i,lab in enumerate(self.profile_summary):
            p=profs[i] if i<len(profs) else {}; bus=p.get('busIndex'); lab.setText(f"{p.get('label','Unconfigured')}\nBus {bus if bus is not None else '—'}")
        if a.get('writesEnabled') and not (self.read_external_json(Path(a.get('mcpGatewayPath',''))/'config'/'local.json').get('enableWrites',False) if a.get('mcpGatewayPath') else False):
            self.safety_summary.setText('Assistant writes are enabled but gateway writes are disabled. No live writes will pass the gateway.')
        else: self.safety_summary.setText('Writes disabled by default. Every live write requires spoken confirmation. Commands are not queued while busy.')

    def start_assistant(self):
        try:
            if not self.save_configs(silent=True): return
            if self.proc.state()!=QProcess.NotRunning: return
            runtime = Path(getattr(sys, '_MEIPASS', '')) / 'bin' / 'wing-voice-runtime' if getattr(sys, 'frozen', False) else None
            py=self.root/'.venv'/'bin'/'python'
            if runtime and runtime.exists():
                self.proc.setProgram(str(runtime)); self.proc.setArguments(['run'])
            elif py.exists():
                self.proc.setProgram(str(py)); self.proc.setArguments(['-m','wing_voice.cli','run'])
            else:
                QMessageBox.warning(self,'Runtime missing','This build has no bundled voice runtime. Use the all-in-one PKG build on macOS.'); return
            self.proc.setProcessEnvironment(self.process_environment(self.root)); self.proc.start()
            if not self.proc.waitForStarted(3000): self.log('ERROR: could not start assistant process.')
        except Exception as e: QMessageBox.critical(self,'Start failed',str(e))
    def process_environment(self, root):
        from PySide6.QtCore import QProcessEnvironment
        env = QProcessEnvironment.systemEnvironment()
        env.insert("WING_ASSISTANT_ROOT", str(root))
        return env

    def stop_assistant(self):
        if self.proc.state()!=QProcess.NotRunning: self.proc.terminate();
        if not self.proc.waitForFinished(2500): self.proc.kill()
        self.log('Assistant stopped by operator.')
    def process_finished(self, code, status): self.log(f'Assistant process exited (code {code}).'); self.refresh_status()
    def read_stdout(self): self.log(self.proc.readAllStandardOutput().data().decode('utf-8','replace').rstrip())
    def read_stderr(self): self.log(self.proc.readAllStandardError().data().decode('utf-8','replace').rstrip())
    def log(self,text):
        if not text: return
        stamp=time.strftime('%H:%M:%S'); line=f'[{stamp}] {text}'; self.log_buffer.append(line)
        if hasattr(self,'log_view'): self.log_view.appendPlainText(line)

    def install_runtime(self):
        if self.proc.state()!=QProcess.NotRunning:
            QMessageBox.warning(self,'Assistant running','Stop the assistant before installing or repairing dependencies.'); return
        if self.setup_proc.state()!=QProcess.NotRunning:
            QMessageBox.information(self,'Installation running','Runtime installation is already in progress.'); return
        script=self.root/'install.command'
        if not script.exists(): QMessageBox.critical(self,'Missing installer',f'Could not find {script}'); return
        answer=QMessageBox.question(self,'Install runtime','This installs Python dependencies for audio, speech recognition and the GUI. It may take several minutes and may download packages. Continue?',QMessageBox.Yes|QMessageBox.No)
        if answer!=QMessageBox.Yes: return
        self.log('Starting runtime installer…')
        self.setup_proc.setProgram('/bin/bash'); self.setup_proc.setArguments([str(script)]); self.setup_proc.start()
        if not self.setup_proc.waitForStarted(3000): self.log('ERROR: could not start runtime installer.')

    def read_setup_stdout(self): self.log(self.setup_proc.readAllStandardOutput().data().decode('utf-8','replace').rstrip())
    def read_setup_stderr(self): self.log(self.setup_proc.readAllStandardError().data().decode('utf-8','replace').rstrip())
    def setup_finished(self, code, status):
        self.log(f'Runtime installer finished (exit code {code}).')
        if code==0: QMessageBox.information(self,'Runtime ready','Dependencies installed. Review the setup instructions in Logs/README, then configure the keyword model and WING MCP paths.')
        else: QMessageBox.warning(self,'Runtime installation failed','See Logs for the installer error.')

    def validate_setup(self):
        if not self.save_configs(silent=True): return
        py=self.root/'.venv'/'bin'/'python'
        if not py.exists(): QMessageBox.warning(self,'Environment missing','Run install.command before validating the runtime.'); return
        self.run_diagnostic([str(py),'-m','wing_voice.cli','validate'],'Validate setup')
    def inspect_tools(self):
        if not self.save_configs(silent=True): return
        py=self.root/'.venv'/'bin'/'python'
        if not py.exists(): QMessageBox.warning(self,'Environment missing','Run install.command before inspecting MCP tools.'); return
        self.pages.setCurrentIndex(7); self.run_diagnostic([str(py),'-m','wing_voice.cli','inspect-tools'],'Inspect MCP tools')
    def run_diagnostic(self,args,title):
        self.log(f'$ {" ".join(args)}')
        try:
            result=subprocess.run(args,cwd=self.root,capture_output=True,text=True,timeout=40)
            if result.stdout: self.log(result.stdout.rstrip())
            if result.stderr: self.log(result.stderr.rstrip())
            self.log(f'{title}: exit code {result.returncode}')
            if result.returncode==0: QMessageBox.information(self,title,'Completed. See Logs for details.')
            else: QMessageBox.warning(self,title,'The check reported a problem. See Logs for details.')
        except Exception as e: self.log(f'{title} failed: {e}'); QMessageBox.critical(self,title,str(e))
    def detect_devices(self):
        py=self.root/'.venv'/'bin'/'python'
        if not py.exists(): QMessageBox.warning(self,'Environment missing','Run install.command first so sounddevice is installed.'); return
        self.run_diagnostic([str(py),'-m','wing_voice.cli','devices'],'Detect audio devices')
    def validate_toolmap_json(self):
        try:
            data=json.loads(self.toolmap_editor.toPlainText())
            if not isinstance(data,dict): raise ValueError('Tool map must be a JSON object.')
            QMessageBox.information(self,'JSON valid','Tool map JSON syntax is valid. This does not verify tool names or schemas.')
        except Exception as e: QMessageBox.warning(self,'Invalid JSON',str(e))
    def load_toolmap_editor(self): self.toolmap_editor.setPlainText(json.dumps(self.read_json('config/tool-map.json',DEFAULT_TOOL_MAP),indent=2,ensure_ascii=False))
    def browse_directory(self,key):
        value=QFileDialog.getExistingDirectory(self,'Choose folder',self.widgets[key].text() or str(Path.home()))
        if value: self.widgets[key].setText(value)
    def browse_file(self,key):
        value=QFileDialog.getOpenFileName(self,'Choose file',self.widgets[key].text() or str(Path.home()),'All files (*)')[0]
        if value: self.widgets[key].setText(value)
    def open_path(self,path):
        try: subprocess.Popen(['open',str(path)])
        except Exception as e: QMessageBox.warning(self,'Open folder',str(e))
    def export_log(self):
        path=QFileDialog.getSaveFileName(self,'Export log',str(Path.home()/'wing-assistant.log'),'Log files (*.log);;Text files (*.txt)')[0]
        if path: Path(path).write_text('\n'.join(self.log_buffer)+'\n')


def main():
    app=QApplication(sys.argv); app.setApplicationName(APP_NAME); app.setOrganizationName('WING Voice Assistant')
    window=MainWindow(); window.show(); sys.exit(app.exec())

if __name__=='__main__': main()
