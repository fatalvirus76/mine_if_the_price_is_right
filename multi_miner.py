#!/usr/bin/env python3
import sys
import os
import time
import requests
import subprocess
import pytz # Make sure pytz is installed: pip install pytz
import json
import shlex
import traceback
import html
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any

# PyQt5 Imports
from PyQt5.QtCore import Qt, QTimer, QProcess, QSize, QSettings
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QTabWidget, QComboBox, QCheckBox,
    QSpinBox, QDoubleSpinBox, QMenuBar, QAction, QFileDialog, QMessageBox,
    QGroupBox, QScrollArea, QSizePolicy, QPlainTextEdit, QFrame, QActionGroup
)
from PyQt5.QtGui import QFont, QPalette, QColor

# --- Constants ---
BASE_API_URL = "https://www.elprisetjustnu.se/api/v1/prices/{year}/{month_day}_{region}.json"
# Default executable names (can be changed via GUI)
DEFAULT_GMINER_EXEC = "/home/anonymous/.local/bin/miner" # GMiner default name might vary
DEFAULT_LOLMINER_EXEC = "/home/anonymous/.local/bin/lolMiner"
DEFAULT_TREX_EXEC = "/home/anonymous/.local/bin/t-rex"
DEFAULT_XMRIG_EXEC = "/home/anonymous/.local/bin/xmrig"
DEFAULT_USER = "38bj4uu8uDsnC5NjoeGb8TMviBCEtMiaet" # Default NiceHash user

NICEHASH_POOLS = [
    "(Egen / Custom...)", # Option to enable custom input
    "stratum+tcp://kawpow.auto.nicehash.com:9200",
    "stratum+tcp://alephium.auto.nicehash.com:9200",
    "stratum+tcp://autolykos.auto.nicehash.com:9200",
    "stratum+tcp://beamv3.auto.nicehash.com:9200",
    "stratum+tcp://cuckoocycle.auto.nicehash.com:9200",
    "stratum+tcp://daggerhashimoto.auto.nicehash.com:9200",
    "stratum+tcp://eaglesong.auto.nicehash.com:9200",
    "stratum+tcp://equihash.auto.nicehash.com:9200",
    "stratum+tcp://etchash.auto.nicehash.com:9200",
    "stratum+tcp://fishhash.auto.nicehash.com:9200",
    "stratum+tcp://kadena.auto.nicehash.com:9200",
    "stratum+tcp://keccak.auto.nicehash.com:9200",
    "stratum+tcp://kheavyhash.auto.nicehash.com:9200",
    "stratum+tcp://lbry.auto.nicehash.com:9200",
    "stratum+tcp://neoscrypt.auto.nicehash.com:9200",
    "stratum+tcp://nexapow.auto.nicehash.com:9200",
    "stratum+tcp://octopus.auto.nicehash.com:9200",
    "stratum+tcp://pyrinhash.auto.nicehash.com:9200",
    "stratum+tcp://quark.auto.nicehash.com:9200",
    "stratum+tcp://qubit.auto.nicehash.com:9200",
    "stratum+tcp://randomxmonero.auto.nicehash.com:9200",
    "stratum+tcp://scrypt.auto.nicehash.com:9200",
    "stratum+tcp://sha256asicboost.auto.nicehash.com:9200",
    "stratum+tcp://sha256.auto.nicehash.com:9200",
    "stratum+tcp://verushash.auto.nicehash.com:9200",
    "stratum+tcp://x11.auto.nicehash.com:9200",
    "stratum+tcp://x16r.auto.nicehash.com:9200",
    "stratum+tcp://xelishashv2.auto.nicehash.com:9200",
    "stratum+tcp://zelhash.auto.nicehash.com:9200",
    "stratum+tcp://zhash.auto.nicehash.com:9200",
]


# --- Helper Functions ---
def strip_ansi_codes(text: str) -> str:
    """Removes ANSI escape codes from a string."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def check_executable(name: str) -> bool:
    """Checks if an executable exists in the system PATH or is an absolute path."""
    if not name:
        return False
    p = Path(name)
    if p.is_absolute():
        try:
            return p.is_file() and os.access(p, os.X_OK)
        except OSError:
            return False

    try:
        result = subprocess.run([name, "--version"], capture_output=True, text=True, check=False, timeout=5)
        return result.returncode in [0, 1, 255] or name.lower() in result.stdout.lower() or name.lower() in result.stderr.lower()
    except FileNotFoundError:
        return False
    except subprocess.TimeoutExpired:
         print(f"Timeout checking executable: {name}")
         return False
    except Exception as e:
        print(f"Error checking executable {name}: {e}")
        return False

def create_browse_button(line_edit: QLineEdit, parent: QWidget, title: str = "Välj fil"):
    """Helper to create a browse button linked to a QLineEdit."""
    button = QPushButton("...")
    button.setFixedWidth(30)
    def browse():
        start_dir = str(Path.home())
        if line_edit.text():
            p = Path(line_edit.text())
            try:
                if p.exists():
                     start_dir = str(p.parent if p.is_file() else p)
                elif p.parent.exists():
                     start_dir = str(p.parent)
            except Exception:
                 pass

        filename, _ = QFileDialog.getOpenFileName(parent, title, start_dir)
        if filename:
            line_edit.setText(filename)
    button.clicked.connect(browse)
    return button

# --- Main Application Window ---
class MinerHubGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Unified Miner Controller (PyQt5)")
        self.setGeometry(50, 50, 1100, 850)

        self.settings = QSettings()
        self.widgets_to_save = []
        self.current_theme = "Standard"

        self.miner_processes: Dict[str, Optional[QProcess]] = {
            "gminer": None,
            "lolminer": None,
            "trex": None,
            "xmrig": None,
        }
        self.active_miner_key: Optional[str] = None

        self.polling_active = False
        self.current_price: Optional[float] = None
        self.log_output = QTextEdit()

        self._create_menu()
        self._create_main_widget()

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll_prices)

        self.load_settings() # This will also apply the theme

        QTimer.singleShot(100, self.check_all_executables)
        QTimer.singleShot(150, lambda: self.update_active_miner(0))
        QTimer.singleShot(200, self.fetch_and_display_initial_price)


    def _create_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("Arkiv")

        reset_action = QAction("Återställ Inställningar", self)
        reset_action.triggered.connect(self.reset_settings)
        file_menu.addAction(reset_action)

        file_menu.addSeparator()

        exit_action = QAction("Avsluta", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        self._create_theme_menu(menubar)


    def _create_theme_menu(self, menubar):
        theme_menu = menubar.addMenu("Teman")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)

        themes = ["Standard", "Mörkt", "Ljust", "Nord", "Matrix", "Synthwave", "Dracula"]
        for theme_name in themes:
            action = QAction(theme_name, self, checkable=True)
            action.triggered.connect(lambda checked, name=theme_name: self.apply_theme(name))
            theme_menu.addAction(action)
            theme_group.addAction(action)

            # Store actions to check them later when loading settings
            setattr(self, f"theme_action_{theme_name.lower()}", action)


    def _create_main_widget(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        top_frame = QFrame()
        top_frame.setFrameShape(QFrame.Shape.StyledPanel)
        top_layout = QHBoxLayout(top_frame)

        price_group = QGroupBox("Elpris")
        price_layout = QVBoxLayout(price_group)
        self.current_price_label = QLabel("Aktuellt elpris: Väntar...")
        self.current_price_label.setFont(QFont("Arial", 14, QFont.Bold))
        self.current_price_label.setAutoFillBackground(True)
        self.current_price_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_price_label.setMinimumWidth(250)
        price_layout.addWidget(self.current_price_label)
        top_layout.addWidget(price_group)

        polling_group = QGroupBox("Elpriskontroll")
        polling_layout = QGridLayout(polling_group)
        
        polling_layout.addWidget(QLabel("Region:"), 0, 0)
        self.region_combo = QComboBox()
        self.region_combo.addItems(["SE1", "SE2", "SE3", "SE4"])
        self._register_widget(self.region_combo, "polling/region", "SE3")
        polling_layout.addWidget(self.region_combo, 0, 1)

        polling_layout.addWidget(QLabel("Starta < (SEK/kWh):"), 1, 0)
        self.start_mining_spin = QDoubleSpinBox()
        self.start_mining_spin.setRange(-9999, 9999)
        self.start_mining_spin.setDecimals(3)
        self._register_widget(self.start_mining_spin, "polling/start_threshold", 0.1)
        polling_layout.addWidget(self.start_mining_spin, 1, 1)

        polling_layout.addWidget(QLabel("Poll Intervall (sek):"), 2, 0)
        self.poll_interval_spin = QSpinBox()
        self.poll_interval_spin.setRange(30, 99999)
        self._register_widget(self.poll_interval_spin, "polling/interval", 300)
        polling_layout.addWidget(self.poll_interval_spin, 2, 1)

        self.start_polling_button = QPushButton("Starta Elpriskontroll")
        self.start_polling_button.clicked.connect(self.start_polling)
        polling_layout.addWidget(self.start_polling_button, 0, 2, 2, 1)

        self.stop_polling_button = QPushButton("Stoppa Elpriskontroll")
        self.stop_polling_button.setEnabled(False)
        self.stop_polling_button.clicked.connect(self.stop_polling)
        polling_layout.addWidget(self.stop_polling_button, 2, 2)

        top_layout.addWidget(polling_group)
        top_layout.addStretch(1)
        main_layout.addWidget(top_frame)

        log_group = QGroupBox("Logg")
        log_layout = QVBoxLayout(log_group)
        self.log_output.setReadOnly(True)
        self.log_output.document().setMaximumBlockCount(5000)
        log_layout.addWidget(self.log_output)

        self.miner_tabs = QTabWidget()
        self.miner_tabs.currentChanged.connect(self.update_active_miner)
        main_layout.addWidget(self.miner_tabs, stretch=1)

        self._create_gminer_tab()
        self._create_lolminer_tab()
        self._create_trex_tab()
        self._create_xmrig_tab()

        main_layout.addWidget(log_group, stretch=1)

    def log_message(self, message: str, error: bool = False, color: Optional[str] = None):
        if hasattr(self, 'log_output') and self.log_output:
            timestamp = time.strftime("%H:%M:%S")
            # Use current palette's text color if no color is specified
            default_color = self.palette().color(QPalette.ColorRole.Text).name()
            final_color = "red" if error else color if color else default_color
            
            safe_message = html.escape(str(message))
            # Use a span with a subtle color for the timestamp
            timestamp_color = self.palette().color(QPalette.ColorRole.Mid).name()
            html_log = (
                f'<span style="color: {timestamp_color};">[{timestamp}]</span> '
                f'<span style="color: {final_color}; white-space: pre;">{safe_message}</span>'
            )
            self.log_output.append(html_log)
            scrollbar = self.log_output.verticalScrollBar()
            if scrollbar.value() >= scrollbar.maximum() - 30:
                scrollbar.setValue(scrollbar.maximum())
        else:
            print(f"LOG (early): {message}")

    def check_all_executables(self):
        if not hasattr(self, 'gminer_path_edit'):
             QTimer.singleShot(200, self.check_all_executables)
             return False
        self.exec_paths = {
            "gminer": self.gminer_path_edit.text().strip(),
            "lolminer": self.lolminer_path_edit.text().strip(),
            "trex": self.trex_path_edit.text().strip(),
            "xmrig": self.xmrig_path_edit.text().strip(),
        }
        self.exec_status = {}
        all_ok = True
        self.log_message("Kontrollerar miner-program...")
        for name, path in self.exec_paths.items():
            ok = check_executable(path)
            self.exec_status[name] = ok
            if ok:
                self.log_message(f"✅ {name.capitalize()} hittades: {path}", color="lightgreen")
            else:
                self.log_message(f"❌ {name.capitalize()} hittades INTE: '{path}'. Kontrollera sökväg under fliken '{name.capitalize()}'.", error=True)
                all_ok = False
        self._update_manual_button_states()
        return all_ok

    def _update_manual_button_states(self):
         for miner_key in self.miner_processes.keys():
              start_button = getattr(self, f"{miner_key}_start_button", None)
              if start_button:
                   is_running = self.miner_processes.get(miner_key) and self.miner_processes[miner_key].state() != QProcess.ProcessState.NotRunning
                   start_button.setEnabled(self.exec_status.get(miner_key, False) and not is_running)

    def _register_widget(self, widget: QWidget, name: str, default_value: Any = None):
        widget.setObjectName(name)
        self.widgets_to_save.append((widget, default_value))

    # ======================================================================
    # === TAB CREATION METHODS (FULLY RESTORED) ===
    # ======================================================================

    def _create_pool_widget(self, miner_prefix: str) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0,0,0,0)

        pool_combo = QComboBox()
        pool_combo.addItems(NICEHASH_POOLS)
        pool_combo.setMinimumWidth(350)
        pool_combo.setToolTip("Välj en förinställd NiceHash-pool eller 'Egen' för att skriva in manuellt.")
        self._register_widget(pool_combo, f"{miner_prefix}/pool_combo", "stratum+tcp://kawpow.auto.nicehash.com:9200")

        custom_pool_edit = QLineEdit()
        custom_pool_edit.setPlaceholderText("Ange egen pool URL här...")
        custom_pool_edit.setEnabled(pool_combo.currentText() == NICEHASH_POOLS[0])
        custom_pool_edit.setToolTip("Aktiveras när du väljer '(Egen / Custom...)' i listan.")
        self._register_widget(custom_pool_edit, f"{miner_prefix}/custom_pool_edit", "")

        pool_combo.currentTextChanged.connect(
            lambda text, edit=custom_pool_edit: edit.setEnabled(text == NICEHASH_POOLS[0])
        )

        layout.addWidget(pool_combo)
        layout.addWidget(custom_pool_edit)
        layout.setStretch(1, 1)

        setattr(self, f"{miner_prefix}_pool_combo", pool_combo)
        setattr(self, f"{miner_prefix}_custom_pool_edit", custom_pool_edit)

        return widget

    def _get_selected_pool(self, miner_prefix: str) -> Optional[str]:
        pool_combo = getattr(self, f"{miner_prefix}_pool_combo", None)
        custom_pool_edit = getattr(self, f"{miner_prefix}_custom_pool_edit", None)

        if not pool_combo or not custom_pool_edit:
            self.log_message(f"Internt fel: Kunde inte hitta pool-widgets för {miner_prefix}", error=True)
            return None

        selected_text = pool_combo.currentText()
        if selected_text == NICEHASH_POOLS[0]:
            custom_url = custom_pool_edit.text().strip()
            if not custom_url:
                 self.log_message(f"Varning: '(Egen / Custom...)' valt för {miner_prefix} men inget URL angetts.", error=True)
                 return None
            return custom_url
        else:
            if "stratum+" in selected_text:
                 return selected_text
            else:
                 self.log_message(f"Varning: Ogiltigt val i pool-listan för {miner_prefix}: {selected_text}", error=True)
                 return None

    def _create_scrollable_tab(self, tab_name: str) -> Tuple[QWidget, QGridLayout]:
        tab_widget = QWidget()
        tab_layout = QVBoxLayout(tab_widget)
        tab_layout.setContentsMargins(5, 5, 5, 5)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        scroll_content = QWidget()
        grid_layout = QGridLayout(scroll_content)
        grid_layout.setSpacing(10)
        scroll.setWidget(scroll_content)
        tab_layout.addWidget(scroll)

        self.miner_tabs.addTab(tab_widget, tab_name)
        return scroll_content, grid_layout

    def _add_manual_start_stop(self, layout: QGridLayout, miner_key: str, start_row: int):
        button_group = QGroupBox(f"Manuell Kontroll ({miner_key.capitalize()})")
        button_layout = QHBoxLayout(button_group)

        start_button = QPushButton(f"Starta Manuellt")
        stop_button = QPushButton(f"Stoppa Manuellt")
        stop_button.setEnabled(False)

        start_button.clicked.connect(lambda state, mk=miner_key: self.start_miner_manual(mk))
        stop_button.clicked.connect(lambda state, mk=miner_key: self.stop_miner_manual(mk))

        button_layout.addWidget(start_button)
        button_layout.addWidget(stop_button)

        layout.addWidget(button_group, start_row, 0, 1, layout.columnCount() if layout.columnCount() > 0 else 1)

        setattr(self, f"{miner_key}_start_button", start_button)
        setattr(self, f"{miner_key}_stop_button", stop_button)
        return start_row + 1

    def _create_gminer_tab(self):
        tab_content, layout = self._create_scrollable_tab("GMiner")
        row, COLUMNS, prefix = 0, 4, "gminer"

        path_group = QGroupBox("Sökväg"); path_layout = QGridLayout(path_group)
        path_layout.addWidget(QLabel("GMiner Program:"), 0, 0)
        self.gminer_path_edit = QLineEdit()
        self._register_widget(self.gminer_path_edit, f"{prefix}/path", DEFAULT_GMINER_EXEC)
        path_layout.addWidget(self.gminer_path_edit, 0, 1)
        path_layout.addWidget(create_browse_button(self.gminer_path_edit, self, "Välj GMiner"), 0, 2)
        layout.addWidget(path_group, row, 0, 1, COLUMNS); row += 1

        net_group = QGroupBox("Nätverk"); net_layout = QGridLayout(net_group)
        r = 0
        net_layout.addWidget(QLabel("Algorithm (-a):"), r, 0)
        self.gminer_algo_combo = QComboBox()
        self.gminer_algo_combo.addItems(["ethash", "etchash", "kawpow", "autolykos2", "beamhash", "cuckatoo32", "kheavyhash", "sha512_256d", "ironfish", "octopus", "karlsenhash", "zil", "ethash+kheavyhash", "etchash+kheavyhash"])
        self._register_widget(self.gminer_algo_combo, f"{prefix}/algo", "kawpow")
        net_layout.addWidget(self.gminer_algo_combo, r, 1, 1, 2); r+=1
        net_layout.addWidget(QLabel("Pool (-s):"), r, 0)
        net_layout.addWidget(self._create_pool_widget(prefix), r, 1, 1, 3); r+=1
        net_layout.addWidget(QLabel("User (-u):"), r, 0)
        self.gminer_user_edit = QLineEdit()
        self._register_widget(self.gminer_user_edit, f"{prefix}/user", DEFAULT_USER)
        net_layout.addWidget(self.gminer_user_edit, r, 1, 1, 2); r+=1
        net_layout.addWidget(QLabel("Password (-p):"), r, 0)
        self.gminer_pass_edit = QLineEdit()
        self._register_widget(self.gminer_pass_edit, f"{prefix}/pass", "x")
        net_layout.addWidget(self.gminer_pass_edit, r, 1, 1, 2); r+=1
        net_layout.addWidget(QLabel("--ssl (on/off):"), r, 0)
        self.gminer_ssl_combo = QComboBox(); self.gminer_ssl_combo.addItems(["off", "on"])
        self._register_widget(self.gminer_ssl_combo, f"{prefix}/ssl", "off")
        net_layout.addWidget(self.gminer_ssl_combo, r, 1); r+=1
        net_layout.addWidget(QLabel("--proto:"), r, 0)
        self.gminer_proto_combo = QComboBox(); self.gminer_proto_combo.addItems(["stratum", "proxy"])
        self._register_widget(self.gminer_proto_combo, f"{prefix}/proto", "stratum")
        net_layout.addWidget(self.gminer_proto_combo, r, 1); r+=1
        net_layout.addWidget(QLabel("--proxy (socks5):"), r, 0)
        self.gminer_proxy_edit = QLineEdit()
        self._register_widget(self.gminer_proxy_edit, f"{prefix}/proxy", "")
        net_layout.addWidget(self.gminer_proxy_edit, r, 1, 1, 2); r+=1
        layout.addWidget(net_group, row, 0, 1, COLUMNS); row += 1

        gpu_group = QGroupBox("GPU"); gpu_layout = QGridLayout(gpu_group); r = 0
        gpu_layout.addWidget(QLabel("-d, --devices:"), r, 0)
        self.gminer_devices_edit = QLineEdit(); self._register_widget(self.gminer_devices_edit, f"{prefix}/devices", "")
        gpu_layout.addWidget(self.gminer_devices_edit, r, 1, 1, 2); r+=1
        gpu_layout.addWidget(QLabel("-i, --intensity:"), r, 0)
        self.gminer_intensity_edit = QLineEdit(); self._register_widget(self.gminer_intensity_edit, f"{prefix}/intensity", "")
        gpu_layout.addWidget(self.gminer_intensity_edit, r, 1, 1, 2); r+=1
        gpu_layout.addWidget(QLabel("-di, --dual_intensity:"), r, 0)
        self.gminer_dual_intensity_edit = QLineEdit(); self._register_widget(self.gminer_dual_intensity_edit, f"{prefix}/dual_intensity", "")
        gpu_layout.addWidget(self.gminer_dual_intensity_edit, r, 1, 1, 2); r+=1
        gpu_layout.addWidget(QLabel("--fan:"), r, 0)
        self.gminer_fan_edit = QLineEdit(); self._register_widget(self.gminer_fan_edit, f"{prefix}/fan", "")
        gpu_layout.addWidget(self.gminer_fan_edit, r, 1, 1, 2); r+=1
        gpu_layout.addWidget(QLabel("--pl (Power Limit %/W):"), r, 0)
        self.gminer_pl_edit = QLineEdit(); self._register_widget(self.gminer_pl_edit, f"{prefix}/pl", "")
        gpu_layout.addWidget(self.gminer_pl_edit, r, 1, 1, 2); r+=1
        layout.addWidget(gpu_group, row, 0, 1, COLUMNS); row += 1

        oc_group = QGroupBox("Överklockning"); oc_layout = QGridLayout(oc_group); r = 0
        oc_layout.addWidget(QLabel("--cclock:"), r, 0)
        self.gminer_cclock_edit = QLineEdit(); self._register_widget(self.gminer_cclock_edit, f"{prefix}/cclock", "")
        oc_layout.addWidget(self.gminer_cclock_edit, r, 1, 1, 2); r+=1
        oc_layout.addWidget(QLabel("--mclock:"), r, 0)
        self.gminer_mclock_edit = QLineEdit(); self._register_widget(self.gminer_mclock_edit, f"{prefix}/mclock", "")
        oc_layout.addWidget(self.gminer_mclock_edit, r, 1, 1, 2); r+=1
        oc_layout.addWidget(QLabel("--lock_cclock:"), r, 0)
        self.gminer_lock_cclock_edit = QLineEdit(); self._register_widget(self.gminer_lock_cclock_edit, f"{prefix}/lock_cclock", "")
        oc_layout.addWidget(self.gminer_lock_cclock_edit, r, 1, 1, 2); r+=1
        oc_layout.addWidget(QLabel("--lock_mclock:"), r, 0)
        self.gminer_lock_mclock_edit = QLineEdit(); self._register_widget(self.gminer_lock_mclock_edit, f"{prefix}/lock_mclock", "")
        oc_layout.addWidget(self.gminer_lock_mclock_edit, r, 1, 1, 2); r+=1
        oc_layout.addWidget(QLabel("--mt (Mem Tweak 0-6):"), r, 0)
        self.gminer_mt_edit = QLineEdit(); self._register_widget(self.gminer_mt_edit, f"{prefix}/mt", "")
        oc_layout.addWidget(self.gminer_mt_edit, r, 1, 1, 2); r+=1
        layout.addWidget(oc_group, row, 0, 1, COLUMNS); row += 1

        logmisc_group = QGroupBox("Loggning & Diverse"); logmisc_layout = QGridLayout(logmisc_group); r = 0
        logmisc_layout.addWidget(QLabel("-l, --logfile:"), r, 0)
        self.gminer_logfile_edit = QLineEdit(); self._register_widget(self.gminer_logfile_edit, f"{prefix}/logfile", "")
        logmisc_layout.addWidget(self.gminer_logfile_edit, r, 1)
        logmisc_layout.addWidget(create_browse_button(self.gminer_logfile_edit, self, "Välj loggfil"), r, 2); r+=1
        logmisc_layout.addWidget(QLabel("--log_date (0/1):"), r, 0)
        self.gminer_log_date_spin = QSpinBox(); self.gminer_log_date_spin.setRange(0, 1)
        self._register_widget(self.gminer_log_date_spin, f"{prefix}/log_date", 0)
        logmisc_layout.addWidget(self.gminer_log_date_spin, r, 1); r+=1
        logmisc_layout.addWidget(QLabel("--log_newjob (0/1):"), r, 0)
        self.gminer_log_newjob_spin = QSpinBox(); self.gminer_log_newjob_spin.setRange(0, 1)
        self._register_widget(self.gminer_log_newjob_spin, f"{prefix}/log_newjob", 1)
        logmisc_layout.addWidget(self.gminer_log_newjob_spin, r, 1); r+=1
        logmisc_layout.addWidget(QLabel("--api (port):"), r, 0)
        self.gminer_api_edit = QLineEdit(); self._register_widget(self.gminer_api_edit, f"{prefix}/api", "")
        logmisc_layout.addWidget(self.gminer_api_edit, r, 1); r+=1
        logmisc_layout.addWidget(QLabel("--config:"), r, 0)
        self.gminer_config_edit = QLineEdit(); self._register_widget(self.gminer_config_edit, f"{prefix}/config", "")
        logmisc_layout.addWidget(self.gminer_config_edit, r, 1)
        logmisc_layout.addWidget(create_browse_button(self.gminer_config_edit, self, "Välj configfil"), r, 2); r+=1
        self.gminer_color_cb = QCheckBox("-c, --color (Enable)"); self._register_widget(self.gminer_color_cb, f"{prefix}/color", False)
        logmisc_layout.addWidget(self.gminer_color_cb, r, 0)
        self.gminer_watchdog_cb = QCheckBox("-w, --watchdog (Enable)"); self._register_widget(self.gminer_watchdog_cb, f"{prefix}/watchdog", True)
        logmisc_layout.addWidget(self.gminer_watchdog_cb, r, 1); r+=1
        layout.addWidget(logmisc_group, row, 0, 1, COLUMNS); row += 1

        row = self._add_manual_start_stop(layout, prefix, row)
        layout.setRowStretch(row, 1)


    def _create_lolminer_tab(self):
        tab_content, layout = self._create_scrollable_tab("lolMiner")
        row, COLUMNS, prefix = 0, 4, "lolminer"

        path_group = QGroupBox("Sökväg"); path_layout = QGridLayout(path_group)
        path_layout.addWidget(QLabel("lolMiner Program:"), 0, 0)
        self.lolminer_path_edit = QLineEdit(); self._register_widget(self.lolminer_path_edit, f"{prefix}/path", DEFAULT_LOLMINER_EXEC)
        path_layout.addWidget(self.lolminer_path_edit, 0, 1)
        path_layout.addWidget(create_browse_button(self.lolminer_path_edit, self, "Välj lolMiner"), 0, 2)
        layout.addWidget(path_group, row, 0, 1, COLUMNS); row += 1

        gen_group = QGroupBox("General & Mining"); gen_layout = QGridLayout(gen_group); r = 0
        gen_layout.addWidget(QLabel("--algo (-a):"), r, 0); self.lolminer_algo_edit = QLineEdit(); self._register_widget(self.lolminer_algo_edit, f"{prefix}/algo", "ETCHASH")
        gen_layout.addWidget(self.lolminer_algo_edit, r, 1, 1, 2); r+=1
        gen_layout.addWidget(QLabel("Pool (-p):"), r, 0)
        gen_layout.addWidget(self._create_pool_widget(prefix), r, 1, 1, 3); r+=1
        gen_layout.addWidget(QLabel("--user (-u):"), r, 0); self.lolminer_user_edit = QLineEdit(); self._register_widget(self.lolminer_user_edit, f"{prefix}/user", DEFAULT_USER)
        gen_layout.addWidget(self.lolminer_user_edit, r, 1, 1, 2); r+=1
        gen_layout.addWidget(QLabel("--pass:"), r, 0); self.lolminer_pass_edit = QLineEdit(); self._register_widget(self.lolminer_pass_edit, f"{prefix}/pass", "x")
        gen_layout.addWidget(self.lolminer_pass_edit, r, 1, 1, 2); r+=1
        gen_layout.addWidget(QLabel("--devices:"), r, 0); self.lolminer_devices_edit = QLineEdit(); self._register_widget(self.lolminer_devices_edit, f"{prefix}/devices", "ALL")
        gen_layout.addWidget(self.lolminer_devices_edit, r, 1, 1, 2); r+=1
        gen_layout.addWidget(QLabel("--tls (on/off):"), r, 0); self.lolminer_tls_combo = QComboBox(); self.lolminer_tls_combo.addItems(["off", "on"]); self._register_widget(self.lolminer_tls_combo, f"{prefix}/tls", "off")
        gen_layout.addWidget(self.lolminer_tls_combo, r, 1); r+=1
        gen_layout.addWidget(QLabel("--socks5:"), r, 0); self.lolminer_socks5_edit = QLineEdit(); self._register_widget(self.lolminer_socks5_edit, f"{prefix}/socks5", "")
        gen_layout.addWidget(self.lolminer_socks5_edit, r, 1, 1, 2); r+=1
        gen_layout.addWidget(QLabel("--dns-over-https (0/1/2):"), r, 0); self.lolminer_doh_spin = QSpinBox(); self.lolminer_doh_spin.setRange(0,2); self._register_widget(self.lolminer_doh_spin, f"{prefix}/doh", 1)
        gen_layout.addWidget(self.lolminer_doh_spin, r, 1)
        gen_layout.addWidget(QLabel("--benchmark:"), r, 2); self.lolminer_benchmark_edit = QLineEdit(); self.lolminer_benchmark_edit.setToolTip("Ex: KAWPOW"); self._register_widget(self.lolminer_benchmark_edit, f"{prefix}/benchmark", "")
        gen_layout.addWidget(self.lolminer_benchmark_edit, r, 3); r+=1
        self.lolminer_devicesbypcie_cb = QCheckBox("--devicesbypcie"); self._register_widget(self.lolminer_devicesbypcie_cb, f"{prefix}/devicesbypcie", False)
        gen_layout.addWidget(self.lolminer_devicesbypcie_cb, r, 0)
        self.lolminer_nocolor_cb = QCheckBox("--nocolor"); self._register_widget(self.lolminer_nocolor_cb, f"{prefix}/nocolor", False)
        gen_layout.addWidget(self.lolminer_nocolor_cb, r, 1)
        self.lolminer_basecolor_cb = QCheckBox("--basecolor"); self._register_widget(self.lolminer_basecolor_cb, f"{prefix}/basecolor", False)
        gen_layout.addWidget(self.lolminer_basecolor_cb, r, 2); r+=1
        gen_layout.addWidget(QLabel("--config:"), r, 0); self.lolminer_config_edit = QLineEdit(); self._register_widget(self.lolminer_config_edit, f"{prefix}/config", "./lolMiner.cfg")
        gen_layout.addWidget(self.lolminer_config_edit, r, 1)
        gen_layout.addWidget(create_browse_button(self.lolminer_config_edit, self, "Välj lolMiner Config"), r, 2); r+=1
        gen_layout.addWidget(QLabel("--json:"), r, 0); self.lolminer_json_edit = QLineEdit(); self._register_widget(self.lolminer_json_edit, f"{prefix}/json", "./user_config.json")
        gen_layout.addWidget(self.lolminer_json_edit, r, 1)
        gen_layout.addWidget(create_browse_button(self.lolminer_json_edit, self, "Välj lolMiner JSON"), r, 2); r+=1
        gen_layout.addWidget(QLabel("--profile:"), r, 0); self.lolminer_profile_edit = QLineEdit(); self._register_widget(self.lolminer_profile_edit, f"{prefix}/profile", "")
        gen_layout.addWidget(self.lolminer_profile_edit, r, 1, 1, 2); r+=1
        self.lolminer_no_cl_cb = QCheckBox("--no-cl"); self._register_widget(self.lolminer_no_cl_cb, f"{prefix}/no-cl", False)
        gen_layout.addWidget(self.lolminer_no_cl_cb, r, 0)
        self.lolminer_version_cb = QCheckBox("-v (version)"); self._register_widget(self.lolminer_version_cb, f"{prefix}/version", False)
        gen_layout.addWidget(self.lolminer_version_cb, r, 1); r+=1
        layout.addWidget(gen_group, row, 0, 1, COLUMNS); row += 1

        man_group = QGroupBox("Managing & Stats"); man_layout = QGridLayout(man_group); r = 0
        man_layout.addWidget(QLabel("--watchdog:"), r, 0); self.lolminer_watchdog_combo = QComboBox(); self.lolminer_watchdog_combo.addItems(["script", "exit", "off"]); self._register_widget(self.lolminer_watchdog_combo, f"{prefix}/watchdog", "script")
        man_layout.addWidget(self.lolminer_watchdog_combo, r, 1)
        man_layout.addWidget(QLabel("--watchdogscript:"), r, 2); self.lolminer_watchdogscript_edit = QLineEdit(); self._register_widget(self.lolminer_watchdogscript_edit, f"{prefix}/watchdogscript", "")
        man_layout.addWidget(self.lolminer_watchdogscript_edit, r, 3); r+=1
        man_layout.addWidget(QLabel("--tstart:"), r, 0); self.lolminer_tstart_spin = QSpinBox(); self.lolminer_tstart_spin.setRange(0,120); self._register_widget(self.lolminer_tstart_spin, f"{prefix}/tstart", 0)
        man_layout.addWidget(self.lolminer_tstart_spin, r, 1)
        man_layout.addWidget(QLabel("--tstop:"), r, 2); self.lolminer_tstop_spin = QSpinBox(); self.lolminer_tstop_spin.setRange(0,120); self._register_widget(self.lolminer_tstop_spin, f"{prefix}/tstop", 0)
        man_layout.addWidget(self.lolminer_tstop_spin, r, 3); r+=1
        man_layout.addWidget(QLabel("--tmode:"), r, 0); self.lolminer_tmode_combo = QComboBox(); self.lolminer_tmode_combo.addItems(["edge", "junction", "memory"]); self._register_widget(self.lolminer_tmode_combo, f"{prefix}/tmode", "edge")
        man_layout.addWidget(self.lolminer_tmode_combo, r, 1); r+=1
        man_layout.addWidget(QLabel("--apiport:"), r, 0); self.lolminer_apiport_spin = QSpinBox(); self.lolminer_apiport_spin.setRange(0,65535); self._register_widget(self.lolminer_apiport_spin, f"{prefix}/apiport", 0)
        man_layout.addWidget(self.lolminer_apiport_spin, r, 1)
        man_layout.addWidget(QLabel("--apihost:"), r, 2); self.lolminer_apihost_edit = QLineEdit(); self._register_widget(self.lolminer_apihost_edit, f"{prefix}/apihost", "0.0.0.0")
        man_layout.addWidget(self.lolminer_apihost_edit, r, 3); r+=1
        man_layout.addWidget(QLabel("--longstats:"), r, 0); self.lolminer_longstats_spin = QSpinBox(); self.lolminer_longstats_spin.setRange(1,9999); self._register_widget(self.lolminer_longstats_spin, f"{prefix}/longstats", 60)
        man_layout.addWidget(self.lolminer_longstats_spin, r, 1)
        man_layout.addWidget(QLabel("--shortstats:"), r, 2); self.lolminer_shortstats_spin = QSpinBox(); self.lolminer_shortstats_spin.setRange(1,9999); self._register_widget(self.lolminer_shortstats_spin, f"{prefix}/shortstats", 15)
        man_layout.addWidget(self.lolminer_shortstats_spin, r, 3); r+=1
        self.lolminer_timeprint_cb = QCheckBox("--timeprint"); self._register_widget(self.lolminer_timeprint_cb, f"{prefix}/timeprint", False)
        man_layout.addWidget(self.lolminer_timeprint_cb, r, 0)
        self.lolminer_compactaccept_cb = QCheckBox("--compactaccept"); self._register_widget(self.lolminer_compactaccept_cb, f"{prefix}/compactaccept", False)
        man_layout.addWidget(self.lolminer_compactaccept_cb, r, 1); r+=1
        self.lolminer_log_cb = QCheckBox("--log"); self._register_widget(self.lolminer_log_cb, f"{prefix}/log", False)
        man_layout.addWidget(self.lolminer_log_cb, r, 0)
        man_layout.addWidget(QLabel("--logfile:"), r, 1); self.lolminer_logfile_edit = QLineEdit(); self._register_widget(self.lolminer_logfile_edit, f"{prefix}/logfile", "")
        man_layout.addWidget(self.lolminer_logfile_edit, r, 2)
        man_layout.addWidget(create_browse_button(self.lolminer_logfile_edit, self, "Välj lolMiner loggfil"), r, 3); r+=1
        layout.addWidget(man_group, row, 0, 1, COLUMNS); row += 1

        oc_group = QGroupBox("Överklockning (Experimentell)"); oc_layout = QGridLayout(oc_group); r=0
        oc_layout.addWidget(QLabel("--cclk:"), r, 0); self.lolminer_cclk_edit = QLineEdit(); self._register_widget(self.lolminer_cclk_edit, f"{prefix}/cclk", "*")
        oc_layout.addWidget(self.lolminer_cclk_edit, r, 1)
        oc_layout.addWidget(QLabel("--mclk:"), r, 2); self.lolminer_mclk_edit = QLineEdit(); self._register_widget(self.lolminer_mclk_edit, f"{prefix}/mclk", "*")
        oc_layout.addWidget(self.lolminer_mclk_edit, r, 3); r+=1
        oc_layout.addWidget(QLabel("--coff:"), r, 0); self.lolminer_coff_edit = QLineEdit(); self._register_widget(self.lolminer_coff_edit, f"{prefix}/coff", "*")
        oc_layout.addWidget(self.lolminer_coff_edit, r, 1)
        oc_layout.addWidget(QLabel("--moff:"), r, 2); self.lolminer_moff_edit = QLineEdit(); self._register_widget(self.lolminer_moff_edit, f"{prefix}/moff", "*")
        oc_layout.addWidget(self.lolminer_moff_edit, r, 3); r+=1
        oc_layout.addWidget(QLabel("--fan:"), r, 0); self.lolminer_fan_edit = QLineEdit(); self._register_widget(self.lolminer_fan_edit, f"{prefix}/fan", "*")
        oc_layout.addWidget(self.lolminer_fan_edit, r, 1)
        oc_layout.addWidget(QLabel("--pl:"), r, 2); self.lolminer_pl_edit = QLineEdit(); self._register_widget(self.lolminer_pl_edit, f"{prefix}/pl", "*")
        oc_layout.addWidget(self.lolminer_pl_edit, r, 3); r+=1
        self.lolminer_no_oc_reset_cb = QCheckBox("--no-oc-reset"); self._register_widget(self.lolminer_no_oc_reset_cb, f"{prefix}/no-oc-reset", False)
        oc_layout.addWidget(self.lolminer_no_oc_reset_cb, r, 0); r+=1
        layout.addWidget(oc_group, row, 0, 1, COLUMNS); row += 1

        eth_group = QGroupBox("Ethash/Altcoin/Dual"); eth_layout = QGridLayout(eth_group); r=0
        eth_layout.addWidget(QLabel("--ethstratum:"), r, 0); self.lolminer_ethstratum_combo = QComboBox(); self.lolminer_ethstratum_combo.addItems(["ETHV1", "ETHPROXY"]); self._register_widget(self.lolminer_ethstratum_combo, f"{prefix}/ethstratum", "ETHV1")
        eth_layout.addWidget(self.lolminer_ethstratum_combo, r, 1)
        eth_layout.addWidget(QLabel("--worker (Eth):"), r, 2); self.lolminer_worker_eth_edit = QLineEdit(); self._register_widget(self.lolminer_worker_eth_edit, f"{prefix}/worker_eth", "eth1.0")
        eth_layout.addWidget(self.lolminer_worker_eth_edit, r, 3); r+=1
        eth_layout.addWidget(QLabel("--lhrtune:"), r, 0); self.lolminer_lhrtune_edit = QLineEdit(); self._register_widget(self.lolminer_lhrtune_edit, f"{prefix}/lhrtune", "auto")
        eth_layout.addWidget(self.lolminer_lhrtune_edit, r, 1); r+=1
        eth_layout.addWidget(QLabel("--dualmode:"), r, 0); self.lolminer_dualmode_combo = QComboBox(); self.lolminer_dualmode_combo.addItems(["none", "zil", "zilEx", "eth", "etc"]); self._register_widget(self.lolminer_dualmode_combo, f"{prefix}/dualmode", "none")
        eth_layout.addWidget(self.lolminer_dualmode_combo, r, 1)
        eth_layout.addWidget(QLabel("--dualpool:"), r, 2); self.lolminer_dualpool_edit = QLineEdit(); self._register_widget(self.lolminer_dualpool_edit, f"{prefix}/dualpool", "")
        eth_layout.addWidget(self.lolminer_dualpool_edit, r, 3); r+=1
        eth_layout.addWidget(QLabel("--dualuser:"), r, 0); self.lolminer_dualuser_edit = QLineEdit(); self._register_widget(self.lolminer_dualuser_edit, f"{prefix}/dualuser", "")
        eth_layout.addWidget(self.lolminer_dualuser_edit, r, 1)
        eth_layout.addWidget(QLabel("--dualpass:"), r, 2); self.lolminer_dualpass_edit = QLineEdit(); self._register_widget(self.lolminer_dualpass_edit, f"{prefix}/dualpass", "")
        eth_layout.addWidget(self.lolminer_dualpass_edit, r, 3); r+=1
        layout.addWidget(eth_group, row, 0, 1, COLUMNS); row += 1

        row = self._add_manual_start_stop(layout, prefix, row)
        layout.setRowStretch(row, 1)

    def _create_trex_tab(self):
        tab_content, layout = self._create_scrollable_tab("T-Rex")
        row, COLUMNS, prefix = 0, 4, "trex"

        path_group = QGroupBox("Sökväg"); path_layout = QGridLayout(path_group)
        path_layout.addWidget(QLabel("T-Rex Program:"), 0, 0)
        self.trex_path_edit = QLineEdit(); self._register_widget(self.trex_path_edit, f"{prefix}/path", DEFAULT_TREX_EXEC)
        path_layout.addWidget(self.trex_path_edit, 0, 1)
        path_layout.addWidget(create_browse_button(self.trex_path_edit, self, "Välj T-Rex"), 0, 2)
        layout.addWidget(path_group, row, 0, 1, COLUMNS); row += 1

        net_group = QGroupBox("Nätverk"); net_layout = QGridLayout(net_group); r=0
        net_layout.addWidget(QLabel("Algorithm (-a):"), r, 0); self.trex_algo_combo = QComboBox(); self.trex_algo_combo.addItems(["autolykos2", "blake3", "etchash", "ethash", "firopow", "kawpow", "mtp", "mtp-tcr", "multi", "octopus", "progpow", "progpow-veil", "progpow-veriblock", "progpowz", "tensority"]); self._register_widget(self.trex_algo_combo, f"{prefix}/algo", "kawpow")
        net_layout.addWidget(self.trex_algo_combo, r, 1, 1, 2); r+=1
        net_layout.addWidget(QLabel("--coin:"), r, 0); self.trex_coin_edit = QLineEdit(); self._register_widget(self.trex_coin_edit, f"{prefix}/coin", "")
        net_layout.addWidget(self.trex_coin_edit, r, 1, 1, 2); r+=1
        net_layout.addWidget(QLabel("URL (-o):"), r, 0)
        net_layout.addWidget(self._create_pool_widget(prefix), r, 1, 1, 3); r+=1
        net_layout.addWidget(QLabel("User (-u):"), r, 0); self.trex_user_edit = QLineEdit(); self._register_widget(self.trex_user_edit, f"{prefix}/user", DEFAULT_USER)
        net_layout.addWidget(self.trex_user_edit, r, 1, 1, 2); r+=1
        net_layout.addWidget(QLabel("Password (-p):"), r, 0); self.trex_pass_edit = QLineEdit(); self._register_widget(self.trex_pass_edit, f"{prefix}/pass", "x")
        net_layout.addWidget(self.trex_pass_edit, r, 1, 1, 2); r+=1
        net_layout.addWidget(QLabel("--worker (-w):"), r, 0); self.trex_worker_edit = QLineEdit(); self._register_widget(self.trex_worker_edit, f"{prefix}/worker", "rig0")
        net_layout.addWidget(self.trex_worker_edit, r, 1, 1, 2); r+=1
        net_layout.addWidget(QLabel("--url2:"), r, 0); self.trex_url2_edit = QLineEdit(); self._register_widget(self.trex_url2_edit, f"{prefix}/url2", "")
        net_layout.addWidget(self.trex_url2_edit, r, 1, 1, 2); r+=1
        net_layout.addWidget(QLabel("--user2:"), r, 0); self.trex_user2_edit = QLineEdit(); self._register_widget(self.trex_user2_edit, f"{prefix}/user2", "")
        net_layout.addWidget(self.trex_user2_edit, r, 1, 1, 2); r+=1
        net_layout.addWidget(QLabel("--pass2:"), r, 0); self.trex_pass2_edit = QLineEdit(); self._register_widget(self.trex_pass2_edit, f"{prefix}/pass2", "")
        net_layout.addWidget(self.trex_pass2_edit, r, 1, 1, 2); r+=1
        net_layout.addWidget(QLabel("--worker2:"), r, 0); self.trex_worker2_edit = QLineEdit(); self._register_widget(self.trex_worker2_edit, f"{prefix}/worker2", "")
        net_layout.addWidget(self.trex_worker2_edit, r, 1, 1, 2); r+=1
        layout.addWidget(net_group, row, 0, 1, COLUMNS); row += 1

        gpu_group = QGroupBox("GPU & Överklockning"); gpu_layout = QGridLayout(gpu_group); r=0
        gpu_layout.addWidget(QLabel("--devices (-d):"), r, 0); self.trex_devices_edit = QLineEdit(); self._register_widget(self.trex_devices_edit, f"{prefix}/devices", "")
        gpu_layout.addWidget(self.trex_devices_edit, r, 1)
        gpu_layout.addWidget(QLabel("--intensity (-i):"), r, 2); self.trex_intensity_edit = QLineEdit(); self._register_widget(self.trex_intensity_edit, f"{prefix}/intensity", "")
        gpu_layout.addWidget(self.trex_intensity_edit, r, 3); r+=1
        gpu_layout.addWidget(QLabel("--pl:"), r, 0); self.trex_pl_edit = QLineEdit(); self._register_widget(self.trex_pl_edit, f"{prefix}/pl", "")
        gpu_layout.addWidget(self.trex_pl_edit, r, 1)
        gpu_layout.addWidget(QLabel("--fan:"), r, 2); self.trex_fan_edit = QLineEdit(); self._register_widget(self.trex_fan_edit, f"{prefix}/fan", "")
        gpu_layout.addWidget(self.trex_fan_edit, r, 3); r+=1
        gpu_layout.addWidget(QLabel("--lock-cclock:"), r, 0); self.trex_lock_cclock_edit = QLineEdit(); self._register_widget(self.trex_lock_cclock_edit, f"{prefix}/lock-cclock", "")
        gpu_layout.addWidget(self.trex_lock_cclock_edit, r, 1)
        gpu_layout.addWidget(QLabel("--cclock:"), r, 2); self.trex_cclock_edit = QLineEdit(); self._register_widget(self.trex_cclock_edit, f"{prefix}/cclock", "")
        gpu_layout.addWidget(self.trex_cclock_edit, r, 3); r+=1
        gpu_layout.addWidget(QLabel("--lock-cv:"), r, 0); self.trex_lock_cv_edit = QLineEdit(); self._register_widget(self.trex_lock_cv_edit, f"{prefix}/lock-cv", "")
        gpu_layout.addWidget(self.trex_lock_cv_edit, r, 1)
        gpu_layout.addWidget(QLabel("--mclock:"), r, 2); self.trex_mclock_edit = QLineEdit(); self._register_widget(self.trex_mclock_edit, f"{prefix}/mclock", "")
        gpu_layout.addWidget(self.trex_mclock_edit, r, 3); r+=1
        gpu_layout.addWidget(QLabel("--mt:"), r, 0); self.trex_mt_edit = QLineEdit(); self._register_widget(self.trex_mt_edit, f"{prefix}/mt", "")
        gpu_layout.addWidget(self.trex_mt_edit, r, 1)
        self.trex_low_load_cb = QCheckBox("--low-load"); self._register_widget(self.trex_low_load_cb, f"{prefix}/low-load", False)
        gpu_layout.addWidget(self.trex_low_load_cb, r, 2); r+=1
        layout.addWidget(gpu_group, row, 0, 1, COLUMNS); row += 1

        lhr_group = QGroupBox("LHR"); lhr_layout = QGridLayout(lhr_group); r=0
        lhr_layout.addWidget(QLabel("--lhr-tune:"), r, 0); self.trex_lhr_tune_edit = QLineEdit(); self._register_widget(self.trex_lhr_tune_edit, f"{prefix}/lhr-tune", "-1")
        lhr_layout.addWidget(self.trex_lhr_tune_edit, r, 1)
        lhr_layout.addWidget(QLabel("--lhr-autotune-mode:"), r, 2); self.trex_lhr_autotune_combo = QComboBox(); self.trex_lhr_autotune_combo.addItems(["off", "down", "full"]); self._register_widget(self.trex_lhr_autotune_combo, f"{prefix}/lhr-autotune-mode", "down")
        lhr_layout.addWidget(self.trex_lhr_autotune_combo, r, 3); r+=1
        layout.addWidget(lhr_group, row, 0, 1, COLUMNS); row += 1

        misc_group = QGroupBox("Diverse"); misc_layout = QGridLayout(misc_group); r=0
        misc_layout.addWidget(QLabel("--api-bind-http:"), r, 0); self.trex_api_bind_edit = QLineEdit(); self._register_widget(self.trex_api_bind_edit, f"{prefix}/api-bind-http", "127.0.0.1:4067")
        misc_layout.addWidget(self.trex_api_bind_edit, r, 1)
        self.trex_api_https_cb = QCheckBox("--api-https"); self._register_widget(self.trex_api_https_cb, f"{prefix}/api-https", False)
        misc_layout.addWidget(self.trex_api_https_cb, r, 2); r+=1
        misc_layout.addWidget(QLabel("--api-key:"), r, 0); self.trex_api_key_edit = QLineEdit(); self._register_widget(self.trex_api_key_edit, f"{prefix}/api-key", "")
        misc_layout.addWidget(self.trex_api_key_edit, r, 1)
        self.trex_api_read_only_cb = QCheckBox("--api-read-only"); self._register_widget(self.trex_api_read_only_cb, f"{prefix}/api-read-only", False)
        misc_layout.addWidget(self.trex_api_read_only_cb, r, 2); r+=1
        self.trex_no_watchdog_cb = QCheckBox("--no-watchdog"); self._register_widget(self.trex_no_watchdog_cb, f"{prefix}/no-watchdog", False)
        misc_layout.addWidget(self.trex_no_watchdog_cb, r, 0)
        self.trex_protocol_dump_cb = QCheckBox("-P, --protocol-dump"); self._register_widget(self.trex_protocol_dump_cb, f"{prefix}/protocol-dump", False)
        misc_layout.addWidget(self.trex_protocol_dump_cb, r, 1); r+=1
        misc_layout.addWidget(QLabel("--log-path (-l):"), r, 0); self.trex_log_path_edit = QLineEdit(); self._register_widget(self.trex_log_path_edit, f"{prefix}/log-path", "")
        misc_layout.addWidget(self.trex_log_path_edit, r, 1)
        self.trex_quiet_cb = QCheckBox("--quiet (-q)"); self._register_widget(self.trex_quiet_cb, f"{prefix}/quiet", False)
        misc_layout.addWidget(self.trex_quiet_cb, r, 2); r+=1
        misc_layout.addWidget(QLabel("--watchdog-exit-mode:"), r, 0); self.trex_watchdog_exit_edit = QLineEdit(); self.trex_watchdog_exit_edit.setToolTip("Ex: r:10,s:600"); self._register_widget(self.trex_watchdog_exit_edit, f"{prefix}/watchdog-exit-mode", "")
        misc_layout.addWidget(self.trex_watchdog_exit_edit, r, 1, 1, 2); r+=1
        misc_layout.addWidget(QLabel("-c, --config:"), r, 0); self.trex_config_edit = QLineEdit(); self._register_widget(self.trex_config_edit, f"{prefix}/config", "")
        misc_layout.addWidget(self.trex_config_edit, r, 1)
        misc_layout.addWidget(create_browse_button(self.trex_config_edit, self, "Välj T-Rex Config"), r, 2); r+=1
        self.trex_benchmark_cb = QCheckBox("-B, --benchmark"); self._register_widget(self.trex_benchmark_cb, f"{prefix}/benchmark", False)
        misc_layout.addWidget(self.trex_benchmark_cb, r, 0)
        self.trex_no_color_cb = QCheckBox("--no-color"); self._register_widget(self.trex_no_color_cb, f"{prefix}/no-color", False)
        misc_layout.addWidget(self.trex_no_color_cb, r, 1); r+=1
        layout.addWidget(misc_group, row, 0, 1, COLUMNS); row += 1

        row = self._add_manual_start_stop(layout, prefix, row)
        layout.setRowStretch(row, 1)

    def _create_xmrig_tab(self):
        tab_content, layout = self._create_scrollable_tab("XMRig")
        row, COLUMNS, prefix = 0, 4, "xmrig"

        path_group = QGroupBox("Sökväg"); path_layout = QGridLayout(path_group)
        path_layout.addWidget(QLabel("XMRig Program:"), 0, 0)
        self.xmrig_path_edit = QLineEdit(); self._register_widget(self.xmrig_path_edit, f"{prefix}/path", DEFAULT_XMRIG_EXEC)
        path_layout.addWidget(self.xmrig_path_edit, 0, 1)
        path_layout.addWidget(create_browse_button(self.xmrig_path_edit, self, "Välj XMRig"), 0, 2)
        layout.addWidget(path_group, row, 0, 1, COLUMNS); row += 1

        xmrig_options_tabs = QTabWidget()
        net_tab = QWidget(); net_layout = QGridLayout(net_tab); r=0
        net_layout.addWidget(QLabel("URL (-o):"), r, 0)
        net_layout.addWidget(self._create_pool_widget(prefix), r, 1, 1, 3); r+=1
        net_layout.addWidget(QLabel("Algo (-a):"), r, 0); self.xmrig_algo_edit = QLineEdit(); self._register_widget(self.xmrig_algo_edit, f"{prefix}/algo", "randomx")
        net_layout.addWidget(self.xmrig_algo_edit, r, 1)
        net_layout.addWidget(QLabel("--coin:"), r, 2); self.xmrig_coin_edit = QLineEdit(); self._register_widget(self.xmrig_coin_edit, f"{prefix}/coin", "")
        net_layout.addWidget(self.xmrig_coin_edit, r, 3); r+=1
        net_layout.addWidget(QLabel("User (-u):"), r, 0); self.xmrig_user_edit = QLineEdit(); self._register_widget(self.xmrig_user_edit, f"{prefix}/user", DEFAULT_USER)
        net_layout.addWidget(self.xmrig_user_edit, r, 1, 1, 3); r+=1
        net_layout.addWidget(QLabel("Password (-p):"), r, 0); self.xmrig_pass_edit = QLineEdit(); self._register_widget(self.xmrig_pass_edit, f"{prefix}/pass", "x")
        net_layout.addWidget(self.xmrig_pass_edit, r, 1)
        net_layout.addWidget(QLabel("User:Pass (-O):"), r, 2); self.xmrig_userpass_edit = QLineEdit(); self._register_widget(self.xmrig_userpass_edit, f"{prefix}/userpass", "")
        net_layout.addWidget(self.xmrig_userpass_edit, r, 3); r+=1
        net_layout.addWidget(QLabel("Proxy (-x):"), r, 0); self.xmrig_proxy_edit = QLineEdit(); self._register_widget(self.xmrig_proxy_edit, f"{prefix}/proxy", "")
        net_layout.addWidget(self.xmrig_proxy_edit, r, 1)
        net_layout.addWidget(QLabel("--rig-id:"), r, 2); self.xmrig_rigid_edit = QLineEdit(); self._register_widget(self.xmrig_rigid_edit, f"{prefix}/rig-id", "")
        net_layout.addWidget(self.xmrig_rigid_edit, r, 3); r+=1
        self.xmrig_keepalive_cb = QCheckBox("-k"); self._register_widget(self.xmrig_keepalive_cb, f"{prefix}/keepalive", False); net_layout.addWidget(self.xmrig_keepalive_cb, r, 0)
        self.xmrig_nicehash_cb = QCheckBox("--nicehash"); self._register_widget(self.xmrig_nicehash_cb, f"{prefix}/nicehash", False); net_layout.addWidget(self.xmrig_nicehash_cb, r, 1)
        self.xmrig_tls_cb = QCheckBox("--tls"); self._register_widget(self.xmrig_tls_cb, f"{prefix}/tls", False); net_layout.addWidget(self.xmrig_tls_cb, r, 2); r+=1
        net_layout.addWidget(QLabel("--tls-fingerprint:"), r, 0); self.xmrig_tls_fp_edit = QLineEdit(); self._register_widget(self.xmrig_tls_fp_edit, f"{prefix}/tls-fingerprint", "")
        net_layout.addWidget(self.xmrig_tls_fp_edit, r, 1, 1, 3); r+=1
        self.xmrig_daemon_cb = QCheckBox("--daemon"); self._register_widget(self.xmrig_daemon_cb, f"{prefix}/daemon", False); net_layout.addWidget(self.xmrig_daemon_cb, r, 0)
        self.xmrig_dns_ipv6_cb = QCheckBox("--dns-ipv6"); self._register_widget(self.xmrig_dns_ipv6_cb, f"{prefix}/dns-ipv6", False); net_layout.addWidget(self.xmrig_dns_ipv6_cb, r, 1); r+=1
        net_layout.setRowStretch(r, 1); xmrig_options_tabs.addTab(net_tab, "Network")

        cpu_tab = QWidget(); cpu_layout = QGridLayout(cpu_tab); r=0
        self.xmrig_no_cpu_cb = QCheckBox("--no-cpu"); self._register_widget(self.xmrig_no_cpu_cb, f"{prefix}/no-cpu", False); cpu_layout.addWidget(self.xmrig_no_cpu_cb, r, 0, 1, 2); r+=1
        cpu_layout.addWidget(QLabel("Threads (-t):"), r, 0); self.xmrig_threads_edit = QLineEdit(); self._register_widget(self.xmrig_threads_edit, f"{prefix}/threads", "")
        cpu_layout.addWidget(self.xmrig_threads_edit, r, 1)
        cpu_layout.addWidget(QLabel("--cpu-affinity:"), r, 2); self.xmrig_cpu_affinity_edit = QLineEdit(); self._register_widget(self.xmrig_cpu_affinity_edit, f"{prefix}/cpu-affinity", "")
        cpu_layout.addWidget(self.xmrig_cpu_affinity_edit, r, 3); r+=1
        cpu_layout.addWidget(QLabel("Algo Var (-v):"), r, 0); self.xmrig_av_spin = QSpinBox(); self.xmrig_av_spin.setRange(0, 99); self._register_widget(self.xmrig_av_spin, f"{prefix}/av", 0)
        cpu_layout.addWidget(self.xmrig_av_spin, r, 1)
        cpu_layout.addWidget(QLabel("--cpu-priority:"), r, 2); self.xmrig_cpu_priority_spin = QSpinBox(); self.xmrig_cpu_priority_spin.setRange(0, 5); self._register_widget(self.xmrig_cpu_priority_spin, f"{prefix}/cpu-priority", 2)
        cpu_layout.addWidget(self.xmrig_cpu_priority_spin, r, 3); r+=1
        self.xmrig_no_huge_pages_cb = QCheckBox("--no-huge-pages"); self._register_widget(self.xmrig_no_huge_pages_cb, f"{prefix}/no-huge-pages", False); cpu_layout.addWidget(self.xmrig_no_huge_pages_cb, r, 0)
        self.xmrig_randomx_no_numa_cb = QCheckBox("--randomx-no-numa"); self._register_widget(self.xmrig_randomx_no_numa_cb, f"{prefix}/randomx-no-numa", False); cpu_layout.addWidget(self.xmrig_randomx_no_numa_cb, r, 1); r+=1
        cpu_layout.setRowStretch(r, 1); xmrig_options_tabs.addTab(cpu_tab, "CPU")

        other_tab = QWidget(); other_layout = QGridLayout(other_tab); r=0
        other_layout.addWidget(QLabel("--http-port:"), r, 0); self.xmrig_http_port_spin = QSpinBox(); self.xmrig_http_port_spin.setRange(0, 65535); self._register_widget(self.xmrig_http_port_spin, f"{prefix}/http-port", 0)
        other_layout.addWidget(self.xmrig_http_port_spin, r, 1)
        other_layout.addWidget(QLabel("--http-access-token:"), r, 2); self.xmrig_http_access_token_edit = QLineEdit(); self._register_widget(self.xmrig_http_access_token_edit, f"{prefix}/http-access-token", "")
        other_layout.addWidget(self.xmrig_http_access_token_edit, r, 3); r+=1
        other_layout.addWidget(QLabel("--log-file (-l):"), r, 0); self.xmrig_log_file_edit = QLineEdit(); self._register_widget(self.xmrig_log_file_edit, f"{prefix}/log-file", "")
        other_layout.addWidget(self.xmrig_log_file_edit, r, 1)
        other_layout.addWidget(create_browse_button(self.xmrig_log_file_edit, self, "Välj loggfil"), r, 2); r+=1
        self.xmrig_verbose_cb = QCheckBox("--verbose"); self._register_widget(self.xmrig_verbose_cb, f"{prefix}/verbose", False); other_layout.addWidget(self.xmrig_verbose_cb, r, 0)
        self.xmrig_background_cb = QCheckBox("-B"); self._register_widget(self.xmrig_background_cb, f"{prefix}/background", False); other_layout.addWidget(self.xmrig_background_cb, r, 1); r+=1
        other_layout.addWidget(QLabel("-c, --config:"), r, 0); self.xmrig_config_file_edit = QLineEdit(); self._register_widget(self.xmrig_config_file_edit, f"{prefix}/config", "")
        other_layout.addWidget(self.xmrig_config_file_edit, r, 1)
        other_layout.addWidget(create_browse_button(self.xmrig_config_file_edit, self, "Välj XMRig Config"), r, 2); r+=1
        other_layout.setRowStretch(r, 1); xmrig_options_tabs.addTab(other_tab, "API/Log/Misc")

        layout.addWidget(xmrig_options_tabs, row, 0, 1, COLUMNS); row += 1

        row = self._add_manual_start_stop(layout, prefix, row)
        layout.setRowStretch(row, 1)

    # ======================================================================
    # === THEME, SETTINGS & POLLING LOGIC ===
    # ======================================================================
    
    def apply_theme(self, theme_name: str):
        self.current_theme = theme_name
        self.log_message(f"Applicerar tema: {theme_name}", color="lightblue")
        
        # Base font size
        font_size = "9pt"
        monospace_font = "Monospace"
        
        # Base styles
        base_style = f"font-size: {font_size};"
        
        # Stylesheets
        style = ""
        if theme_name == "Standard":
            QApplication.instance().setStyleSheet("")
            QApplication.instance().setPalette(QApplication.style().standardPalette())
            self.log_output.setFont(QFont(monospace_font, 9))
            self.update_price_label(self.current_price) # Re-apply label color
            return

        elif theme_name == "Mörkt":
            style = f"""
                QWidget {{ {base_style} background-color: #2b2b2b; color: #f0f0f0; border: 1px solid #3c3c3c; }}
                QMainWindow, QMenuBar, QMenu {{ background-color: #2b2b2b; color: #f0f0f0; }}
                QGroupBox {{ background-color: #313131; border-radius: 4px; padding-top: 10px; margin-top: 5px; }}
                QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top center; padding: 0 5px; }}
                QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background-color: #3c3c3c; color: #f0f0f0; border: 1px solid #555; padding: 2px; }}
                QPushButton {{ background-color: #4d4d4d; color: #f0f0f0; border: 1px solid #555; padding: 5px; }}
                QPushButton:hover {{ background-color: #5a5a5a; }}
                QPushButton:pressed {{ background-color: #636363; }}
                QPushButton:disabled {{ background-color: #404040; color: #888; }}
                QTabWidget::pane {{ border: 1px solid #3c3c3c; }}
                QTabBar::tab {{ background: #2b2b2b; padding: 6px; }}
                QTabBar::tab:selected {{ background: #4d4d4d; }}
                QCheckBox::indicator {{ width: 13px; height: 13px; border: 1px solid #555;}}
                QCheckBox::indicator:checked {{ background-color: #5e81ac; }}
            """
        elif theme_name == "Ljust":
            style = f"""
                QWidget {{ {base_style} background-color: #ffffff; color: #000000; border: 1px solid #dcdcdc; }}
                QMainWindow, QMenuBar, QMenu {{ background-color: #f0f0f0; color: #000000; }}
                QGroupBox {{ background-color: #fafafa; border-radius: 4px; padding-top: 10px; margin-top: 5px; }}
                QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top center; padding: 0 5px; }}
                QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background-color: #ffffff; color: #000000; border: 1px solid #cccccc; padding: 2px; }}
                QPushButton {{ background-color: #e1e1e1; color: #000000; border: 1px solid #cccccc; padding: 5px; }}
                QPushButton:hover {{ background-color: #d1d1d1; }}
                QPushButton:pressed {{ background-color: #c1c1c1; }}
                QPushButton:disabled {{ background-color: #f5f5f5; color: #aaaaaa; }}
                QTabWidget::pane {{ border: 1px solid #dcdcdc; }}
                QTabBar::tab {{ background: #f0f0f0; padding: 6px; }}
                QTabBar::tab:selected {{ background: #ffffff; }}
            """
        elif theme_name == "Nord":
            style = f"""
                QWidget {{ {base_style} background-color: #2E3440; color: #D8DEE9; border: 1px solid #4C566A; }}
                QMainWindow, QMenuBar, QMenu {{ background-color: #2E3440; color: #D8DEE9; }}
                QGroupBox {{ background-color: #3B4252; border-radius: 4px; padding-top: 10px; margin-top: 5px; }}
                QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top center; padding: 0 5px; color: #E5E9F0;}}
                QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background-color: #434C5E; color: #ECEFF4; border: 1px solid #4C566A; padding: 2px; }}
                QPushButton {{ background-color: #5E81AC; color: #ECEFF4; border: none; padding: 5px; }}
                QPushButton:hover {{ background-color: #81A1C1; }}
                QPushButton:pressed {{ background-color: #88C0D0; }}
                QPushButton:disabled {{ background-color: #4C566A; color: #D8DEE9; }}
                QTabWidget::pane {{ border: 1px solid #4C566A; }}
                QTabBar::tab {{ background: #2E3440; padding: 6px; }}
                QTabBar::tab:selected {{ background: #434C5E; }}
                QCheckBox::indicator {{ border: 1px solid #4C566A; }}
                QCheckBox::indicator:checked {{ background-color: #88C0D0; }}
            """
        elif theme_name == "Matrix":
            monospace_font = "Monospace"
            style = f"""
                QWidget {{ {base_style} background-color: #000000; color: #00FF00; border: 1px solid #00FF00; font-family: {monospace_font}; }}
                QMainWindow, QMenuBar, QMenu {{ background-color: #000000; color: #00FF00; }}
                QGroupBox {{ background-color: #0A0A0A; border: 1px solid #00FF00; border-radius: 4px; padding-top: 10px; margin-top: 5px; }}
                QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top center; padding: 0 5px;}}
                QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background-color: #050505; color: #39FF14; border: 1px solid #00FF00; padding: 2px; }}
                QPushButton {{ background-color: #080808; color: #00FF00; border: 1px solid #00FF00; padding: 5px; }}
                QPushButton:hover {{ background-color: #111; color: #39FF14; }}
                QPushButton:pressed {{ background-color: #222; }}
                QPushButton:disabled {{ background-color: #050505; color: #008F00; }}
                QTabWidget::pane {{ border: 1px solid #00FF00; }}
                QTabBar::tab {{ background: #000000; padding: 6px; }}
                QTabBar::tab:selected {{ background: #1A1A1A; }}
            """
        elif theme_name == "Synthwave":
            style = f"""
                QWidget {{ {base_style} background-color: #262335; color: #FFD4E9; border: 1px solid #73479A; }}
                QMainWindow, QMenuBar, QMenu {{ background-color: #1D1A2A; color: #FFD4E9; }}
                QGroupBox {{ background-color: #352F4E; border-radius: 4px; padding-top: 10px; margin-top: 5px; }}
                QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top center; padding: 0 5px; color: #F92A82; }}
                QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background-color: #1D1A2A; color: #FFF; border: 1px solid #73479A; padding: 2px; }}
                QPushButton {{ background-color: #F92A82; color: #FFF; border: none; padding: 5px; }}
                QPushButton:hover {{ background-color: #FF57AC; }}
                QPushButton:pressed {{ background-color: #C72267; }}
                QPushButton:disabled {{ background-color: #73479A; color: #B392C9; }}
                QTabWidget::pane {{ border: 1px solid #73479A; }}
                QTabBar::tab {{ background: #262335; padding: 6px; }}
                QTabBar::tab:selected {{ background: #352F4E; }}
                QCheckBox::indicator {{ border: 1px solid #73479A; }}
                QCheckBox::indicator:checked {{ background-color: #00FFFF; }}
            """
        elif theme_name == "Dracula":
            style = f"""
                QWidget {{ {base_style} background-color: #282a36; color: #f8f8f2; border: 1px solid #44475a; }}
                QMainWindow, QMenuBar, QMenu {{ background-color: #282a36; color: #f8f8f2; }}
                QGroupBox {{ background-color: #333644; border-radius: 4px; padding-top: 10px; margin-top: 5px; }}
                QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top center; padding: 0 5px; color: #bd93f9; }}
                QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background-color: #44475a; color: #f8f8f2; border: 1px solid #6272a4; padding: 2px; }}
                QPushButton {{ background-color: #6272a4; color: #f8f8f2; border: none; padding: 5px; }}
                QPushButton:hover {{ background-color: #7284b8; }}
                QPushButton:pressed {{ background-color: #526294; }}
                QPushButton:disabled {{ background-color: #3b3d4a; color: #6272a4; }}
                QTabWidget::pane {{ border: 1px solid #44475a; }}
                QTabBar::tab {{ background: #282a36; padding: 6px; }}
                QTabBar::tab:selected {{ background: #44475a; }}
                QCheckBox::indicator {{ border: 1px solid #6272a4; }}
                QCheckBox::indicator:checked {{ background-color: #ff79c6; }}
            """

        QApplication.instance().setStyleSheet(style)
        # Apply specific font to log output
        self.log_output.setFont(QFont(monospace_font, 9))
        self.update_price_label(self.current_price) # Re-apply label color
        # Also need to reset the log message color
        self.log_message(f"Tema '{theme_name}' applicerat.", color="#50fa7b" if theme_name == "Dracula" else "lightgreen")


    def save_settings(self):
        self.log_message("Sparar inställningar...")
        # Save theme
        self.settings.setValue("ui/theme", self.current_theme)

        for widget, _ in self.widgets_to_save:
            key = widget.objectName()
            if not key: continue
            value = None
            if isinstance(widget, QLineEdit): value = widget.text()
            elif isinstance(widget, QComboBox): value = widget.currentText()
            elif isinstance(widget, QCheckBox): value = widget.isChecked()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)): value = widget.value()
            if value is not None: self.settings.setValue(key, value)
        self.settings.sync()

    def load_settings(self):
        self.log_message("Laddar inställningar...")
        
        # Load theme first
        theme_name = self.settings.value("ui/theme", "Standard")
        action_name = f"theme_action_{theme_name.lower()}"
        if hasattr(self, action_name):
            getattr(self, action_name).setChecked(True)
        self.apply_theme(theme_name)

        for widget, default_value in self.widgets_to_save:
            key = widget.objectName()
            if not key: continue
            
            value = self.settings.value(key, default_value)

            if isinstance(widget, QLineEdit): widget.setText(str(value))
            elif isinstance(widget, QComboBox): widget.setCurrentText(str(value))
            elif isinstance(widget, QCheckBox): widget.setChecked(str(value).lower() == 'true' if isinstance(value, (str, bool)) else bool(value))
            elif isinstance(widget, QDoubleSpinBox): widget.setValue(float(value))
            elif isinstance(widget, QSpinBox): widget.setValue(int(float(value))) 
    
    def reset_settings(self):
        reply = QMessageBox.question(self, "Återställ Inställningar",
                                     "Är du säker på att du vill återställa alla inställningar till standard?\n"
                                     "Programmet kommer att startas om.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.log_message("Återställer alla inställningar...", color="orange")
            self.settings.clear()
            self.settings.sync()
            QApplication.instance().quit()
            QProcess.startDetached(sys.executable, sys.argv)

    def fetch_and_display_initial_price(self):
        self.log_message("Hämtar initialt elpris...")
        api_url = self.get_api_url()
        prices = self.fetch_prices(api_url)
        price_now = self.get_current_price_from_api(prices)
        if price_now is not None:
            self.current_price = price_now
            self.log_message(f"Initialt elpris: {price_now:.3f} SEK/kWh")
            self.update_price_label(price_now)
        else:
            self.log_message("Kunde inte hämta initialt elpris.", error=True)
            self.update_price_label(None)

    def update_active_miner(self, index):
        if index < 0:
             self.active_miner_key = None
             return
        tab_text = self.miner_tabs.tabText(index).lower()
        if "gminer" in tab_text: self.active_miner_key = "gminer"
        elif "lolminer" in tab_text: self.active_miner_key = "lolminer"
        elif "t-rex" in tab_text: self.active_miner_key = "trex"
        elif "xmrig" in tab_text: self.active_miner_key = "xmrig"
        else: self.active_miner_key = None

    def start_polling(self):
        if self.polling_active: return
        self.polling_active = True
        self.log_message("▶️ Startar elpriskontroll...")
        self.poll_interval = self.poll_interval_spin.value()
        self.poll_timer.start(self.poll_interval * 1000)
        self.start_polling_button.setEnabled(False)
        self.stop_polling_button.setEnabled(True)
        self.poll_prices()

    def stop_polling(self):
        if not self.polling_active: return
        self.polling_active = False
        self.poll_timer.stop()
        self.log_message("⏹ Stoppar elpriskontroll.")
        if self.active_miner_key and self.miner_processes.get(self.active_miner_key):
            self.log_message(f"   ↳ Stoppar {self.active_miner_key.capitalize()} som styrdes av elpriset.")
            self.stop_miner_process(self.active_miner_key)
        self.start_polling_button.setEnabled(True)
        self.stop_polling_button.setEnabled(False)
        self.current_price_label.setText("Elpriskontroll stoppad")
        # Reset background color but respect theme
        price_label_palette = self.current_price_label.palette()
        price_label_palette.setColor(QPalette.ColorRole.Window, self.palette().color(QPalette.ColorRole.Base))
        self.current_price_label.setPalette(price_label_palette)

    def poll_prices(self):
        if not self.polling_active: return
        self.log_message(f"⏰ Polling elpris (Intervall: {self.poll_interval_spin.value()}s)...")
        api_url = self.get_api_url()
        prices = self.fetch_prices(api_url)
        price_now = self.get_current_price_from_api(prices)
        if price_now is not None:
            self.current_price = price_now
            self.log_message(f"Aktuellt elpris: {price_now:.3f} SEK/kWh")
            self.update_price_label(price_now)
            threshold = self.start_mining_spin.value()
            if not self.active_miner_key:
                 self.log_message("Ingen aktiv miner-flik vald för elpriskontroll.")
                 return
            if price_now < threshold:
                self.log_message(f"Pris ({price_now:.3f}) < Tröskel ({threshold:.3f}). Startar/behåller {self.active_miner_key.capitalize()}.")
                self.start_miner_process(self.active_miner_key)
            else:
                self.log_message(f"Pris ({price_now:.3f}) >= Tröskel ({threshold:.3f}). Stoppar {self.active_miner_key.capitalize()}.")
                self.stop_miner_process(self.active_miner_key)
        else:
            self.log_message("Kunde inte hämta aktuellt elpris.", error=True)
            self.update_price_label(None)
            if self.active_miner_key:
                 self.log_message("Stoppar aktiv miner p.g.a. misslyckad prishämtning.", error=True)
                 self.stop_miner_process(self.active_miner_key)

    def get_api_url(self):
        now = datetime.now()
        return BASE_API_URL.format(year=now.year, month_day=now.strftime("%m-%d"), region=self.region_combo.currentText())

    def fetch_prices(self, api_url):
        try:
            resp = requests.get(api_url, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            self.log_message(f"Nätverksfel vid hämtning av priser: {e}", error=True)
            return []
        except json.JSONDecodeError:
            self.log_message(f"Kunde inte tolka JSON-svar från API", error=True)
            return []

    def get_current_price_from_api(self, prices):
        if not prices or not isinstance(prices, list): return None
        try:
            target_tz = pytz.timezone("Europe/Stockholm")
            now_local = datetime.now(target_tz)
            for entry in prices:
                if not isinstance(entry, dict) or not all(k in entry for k in ["time_start", "time_end", "SEK_per_kWh"]): continue
                start_time_local = datetime.fromisoformat(entry["time_start"]).astimezone(target_tz)
                end_time_local = datetime.fromisoformat(entry["time_end"]).astimezone(target_tz)
                if start_time_local <= now_local < end_time_local:
                    return float(entry["SEK_per_kWh"])
            self.log_message("Kunde inte hitta pris för aktuell timme i API-svaret.", error=True)
            return None
        except Exception as e:
            self.log_message(f"Fel vid tolkning av prisdata: {e}", error=True)
            traceback.print_exc()
            return None

    def update_price_label(self, price: Optional[float]):
        # We now use a palette for theming instead of a stylesheet string
        p = self.current_price_label.palette()
        p.setColor(QPalette.ColorRole.WindowText, self.palette().color(QPalette.ColorRole.Text))

        if price is None:
            self.current_price_label.setText("Aktuellt elpris: N/A")
            p.setColor(QPalette.ColorRole.Window, QColor("orange"))
        else:
            self.current_price_label.setText(f"Aktuellt elpris: {price:.3f} SEK/kWh")
            if price < self.start_mining_spin.value():
                p.setColor(QPalette.ColorRole.Window, QColor("lightgreen"))
            else:
                p.setColor(QPalette.ColorRole.Window, QColor("salmon"))
        self.current_price_label.setPalette(p)


    # ======================================================================
    # === MINER PROCESS HANDLING ===
    # ======================================================================

    def start_miner_manual(self, miner_key: str):
        if self.polling_active and self.active_miner_key == miner_key:
             QMessageBox.warning(self, "Konflikt", f"{miner_key.capitalize()} styrs av elpriset. Stoppa elpriskontrollen först.")
             return
        self.log_message(f"Försöker starta {miner_key.capitalize()} manuellt...")
        self.start_miner_process(miner_key, manual_start=True)

    def stop_miner_manual(self, miner_key: str):
        if self.polling_active and self.active_miner_key == miner_key:
             QMessageBox.warning(self, "Konflikt", f"{miner_key.capitalize()} styrs av elpriset. Stoppa elpriskontrollen först.")
             return
        self.log_message(f"Försöker stoppa {miner_key.capitalize()} manuellt...")
        self.stop_miner_process(miner_key, manual_stop=True)

    def start_miner_process(self, miner_key: str, manual_start: bool = False):
        if self.miner_processes.get(miner_key) and self.miner_processes[miner_key].state() != QProcess.ProcessState.NotRunning:
            if manual_start: self.log_message(f"{miner_key.capitalize()} körs redan.")
            return
        builder_func = getattr(self, f"build_{miner_key}_command", None)
        if not builder_func: return
        cmd_list = builder_func()
        if not cmd_list: return
        executable, args = cmd_list[0], cmd_list[1:]
        if not check_executable(executable):
             self.log_message(f"Körbar fil för {miner_key.capitalize()} ({executable}) hittades inte.", error=True)
             return
        self.log_message(f"Startar {miner_key.capitalize()}: {shlex.join(cmd_list)}")
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(lambda mk=miner_key: self.handle_miner_output(mk))
        process.finished.connect(lambda exitCode, exitStatus, mk=miner_key: self.handle_miner_finished(mk, exitCode, exitStatus))
        try:
            process.start(executable, args)
            if process.state() == QProcess.ProcessState.NotRunning: raise RuntimeError(process.errorString())
            self.miner_processes[miner_key] = process
            self.log_message(f"{miner_key.capitalize()} startad (PID: {process.processId()}).")
            self._update_specific_manual_buttons(miner_key, is_running=True)
        except Exception as e:
            self.log_message(f"Misslyckades starta {miner_key.capitalize()}: {e}", error=True)
            self._update_specific_manual_buttons(miner_key, is_running=False)

    def stop_miner_process(self, miner_key: str, manual_stop: bool = False):
        process = self.miner_processes.get(miner_key)
        if process and process.state() != QProcess.ProcessState.NotRunning:
            self.log_message(f"Stoppar {miner_key.capitalize()} (PID: {process.processId()})...")
            process.kill()
            process.waitForFinished(5000)
        elif manual_stop:
            self.log_message(f"{miner_key.capitalize()} kördes inte.")
        self._update_specific_manual_buttons(miner_key, is_running=False)

    def handle_miner_output(self, miner_key: str):
        process = self.miner_processes.get(miner_key)
        if process and process.bytesAvailable() > 0:
            output_bytes = process.readAllStandardOutput()
            try:
                output_text = output_bytes.data().decode('utf-8', errors='replace').strip()
                if output_text:
                    cleaned_text = strip_ansi_codes(output_text)
                    log_color = {"Dracula": "#8be9fd", "Synthwave": "#00FFFF"}.get(self.current_theme, "#00008B") # DarkBlue
                    for line in cleaned_text.splitlines():
                         self.log_message(f"[{miner_key.upper()}] {line}", color=log_color)
            except Exception:
                 self.log_message(f"Kunde inte avkoda output från {miner_key}", error=True)

    def handle_miner_finished(self, miner_key: str, exitCode: int, exitStatus: QProcess.ExitStatus):
        status_desc = "kraschade" if exitStatus == QProcess.ExitStatus.CrashExit else "avslutades normalt"
        is_error = exitStatus == QProcess.ExitStatus.CrashExit or exitCode != 0
        self.log_message(f"{miner_key.capitalize()} {status_desc} (Kod: {exitCode}).", error=is_error)
        self.miner_processes[miner_key] = None
        self._update_specific_manual_buttons(miner_key, is_running=False)

    def _update_specific_manual_buttons(self, miner_key: str, is_running: bool):
         start_button = getattr(self, f"{miner_key}_start_button", None)
         stop_button = getattr(self, f"{miner_key}_stop_button", None)
         can_start = self.exec_status.get(miner_key, False)
         if start_button: start_button.setEnabled(can_start and not is_running)
         if stop_button: stop_button.setEnabled(is_running)

    # ======================================================================
    # === COMMAND BUILDERS (FULLY RESTORED) ===
    # ======================================================================

    def build_gminer_command(self) -> Optional[List[str]]:
        try:
            path = self.gminer_path_edit.text().strip()
            if not path: return None
            cmd = [path]
            config_path = self.gminer_config_edit.text().strip()
            if config_path: return ["--config", config_path]
            pool_url = self._get_selected_pool("gminer")
            if not pool_url: return None
            cmd += ["-s", pool_url]
            if self.gminer_algo_combo.currentText(): cmd += ["-a", self.gminer_algo_combo.currentText()]
            if self.gminer_user_edit.text(): cmd += ["-u", self.gminer_user_edit.text()]
            if self.gminer_pass_edit.text(): cmd += ["-p", self.gminer_pass_edit.text()]
            if self.gminer_ssl_combo.currentText() == "on": cmd += ["--ssl", "1"]
            if self.gminer_proto_combo.currentText() != "stratum": cmd += ["--proto", self.gminer_proto_combo.currentText()]
            if self.gminer_proxy_edit.text(): cmd += ["--proxy", self.gminer_proxy_edit.text()]
            if self.gminer_devices_edit.text(): cmd += ["-d", self.gminer_devices_edit.text()]
            if self.gminer_intensity_edit.text(): cmd += ["-i", self.gminer_intensity_edit.text()]
            if self.gminer_dual_intensity_edit.text(): cmd += ["-di", self.gminer_dual_intensity_edit.text()]
            if self.gminer_fan_edit.text(): cmd += ["--fan", self.gminer_fan_edit.text()]
            if self.gminer_pl_edit.text(): cmd += ["--pl", self.gminer_pl_edit.text()]
            if self.gminer_cclock_edit.text(): cmd += ["--cclock", self.gminer_cclock_edit.text()]
            if self.gminer_mclock_edit.text(): cmd += ["--mclock", self.gminer_mclock_edit.text()]
            if self.gminer_lock_cclock_edit.text(): cmd += ["--lock_cclock", self.gminer_lock_cclock_edit.text()]
            if self.gminer_lock_mclock_edit.text(): cmd += ["--lock_mclock", self.gminer_lock_mclock_edit.text()]
            if self.gminer_mt_edit.text(): cmd += ["--mt", self.gminer_mt_edit.text()]
            if self.gminer_logfile_edit.text(): cmd += ["-l", self.gminer_logfile_edit.text()]
            if self.gminer_log_date_spin.value() == 1: cmd += ["--log_date", "1"]
            if self.gminer_log_newjob_spin.value() == 0: cmd += ["--log_newjob", "0"]
            if self.gminer_api_edit.text(): cmd += ["--api", self.gminer_api_edit.text()]
            if not self.gminer_color_cb.isChecked(): cmd += ["-c", "0"]
            if not self.gminer_watchdog_cb.isChecked(): cmd += ["-w", "0"]
            return cmd
        except Exception as e:
             self.log_message(f"Fel vid byggande av GMiner-kommando: {e}", error=True)
             return None

    def build_lolminer_command(self) -> Optional[List[str]]:
        try:
            path = self.lolminer_path_edit.text().strip()
            if not path: return None
            cmd = [path]
            if self.lolminer_config_edit.text().strip() != "./lolMiner.cfg": cmd += ["--config", self.lolminer_config_edit.text().strip()]
            if self.lolminer_json_edit.text().strip() != "./user_config.json": cmd += ["--json", self.lolminer_json_edit.text().strip()]
            if self.lolminer_profile_edit.text().strip(): cmd += ["--profile", self.lolminer_profile_edit.text().strip()]
            if self.lolminer_nocolor_cb.isChecked(): cmd.append("--nocolor")
            if self.lolminer_basecolor_cb.isChecked(): cmd.append("--basecolor")
            if self.lolminer_no_cl_cb.isChecked(): cmd.append("--no-cl")
            if self.lolminer_version_cb.isChecked(): return cmd + ["-v"]
            if not self.lolminer_profile_edit.text().strip():
                if self.lolminer_algo_edit.text().strip(): cmd += ["--algo", self.lolminer_algo_edit.text().strip()]
                pool_url = self._get_selected_pool("lolminer")
                if not pool_url and not self.lolminer_benchmark_edit.text().strip(): return None
                if pool_url: cmd += ["--pool", pool_url]
                if self.lolminer_user_edit.text().strip(): cmd += ["--user", self.lolminer_user_edit.text().strip()]
                if self.lolminer_pass_edit.text().strip(): cmd += ["--pass", self.lolminer_pass_edit.text().strip()]
            if self.lolminer_benchmark_edit.text().strip(): cmd += ["--benchmark", self.lolminer_benchmark_edit.text().strip()]
            if self.lolminer_tls_combo.currentText() == "on": cmd += ["--tls", "on"]
            if self.lolminer_devices_edit.text().strip().upper() != "ALL": cmd += ["--devices", self.lolminer_devices_edit.text().strip()]
            if self.lolminer_devicesbypcie_cb.isChecked(): cmd.append("--devicesbypcie")
            if self.lolminer_socks5_edit.text().strip(): cmd += ["--socks5", self.lolminer_socks5_edit.text().strip()]
            if self.lolminer_doh_spin.value() != 1: cmd += ["--dns-over-https", str(self.lolminer_doh_spin.value())]
            if self.lolminer_watchdog_combo.currentText() != "script": cmd += ["--watchdog", self.lolminer_watchdog_combo.currentText()]
            if self.lolminer_watchdogscript_edit.text().strip(): cmd += ["--watchdogscript", self.lolminer_watchdogscript_edit.text().strip()]
            if self.lolminer_tstart_spin.value() != 0: cmd += ["--tstart", str(self.lolminer_tstart_spin.value())]
            if self.lolminer_tstop_spin.value() != 0: cmd += ["--tstop", str(self.lolminer_tstop_spin.value())]
            if self.lolminer_tmode_combo.currentText() != "edge": cmd += ["--tmode", self.lolminer_tmode_combo.currentText()]
            if self.lolminer_apiport_spin.value() != 0: cmd += ["--apiport", str(self.lolminer_apiport_spin.value())]
            if self.lolminer_apihost_edit.text().strip() != "0.0.0.0": cmd += ["--apihost", self.lolminer_apihost_edit.text().strip()]
            if self.lolminer_longstats_spin.value() != 60: cmd += ["--longstats", str(self.lolminer_longstats_spin.value())]
            if self.lolminer_shortstats_spin.value() != 15: cmd += ["--shortstats", str(self.lolminer_shortstats_spin.value())]
            if self.lolminer_timeprint_cb.isChecked(): cmd.append("--timeprint")
            if self.lolminer_compactaccept_cb.isChecked(): cmd.append("--compactaccept")
            if self.lolminer_log_cb.isChecked(): cmd.append("--log")
            if self.lolminer_logfile_edit.text().strip(): cmd += ["--logfile", self.lolminer_logfile_edit.text().strip()]
            def add_oc(p, w):
                if w.text().strip() and w.text().strip() != "*": cmd.extend([p, w.text().strip()])
            add_oc("--cclk", self.lolminer_cclk_edit); add_oc("--mclk", self.lolminer_mclk_edit)
            add_oc("--coff", self.lolminer_coff_edit); add_oc("--moff", self.lolminer_moff_edit)
            add_oc("--fan", self.lolminer_fan_edit); add_oc("--pl", self.lolminer_pl_edit)
            if self.lolminer_no_oc_reset_cb.isChecked(): cmd.append("--no-oc-reset")
            if self.lolminer_ethstratum_combo.currentText() != "ETHPROXY": cmd += ["--ethstratum", self.lolminer_ethstratum_combo.currentText()]
            if self.lolminer_lhrtune_edit.text().strip().lower() != "auto": cmd += ["--lhrtune", self.lolminer_lhrtune_edit.text().strip()]
            if self.lolminer_dualmode_combo.currentText() != "none":
                cmd += ["--dualmode", self.lolminer_dualmode_combo.currentText()]
                if self.lolminer_dualpool_edit.text().strip(): cmd += ["--dualpool", self.lolminer_dualpool_edit.text().strip()]
                if self.lolminer_dualuser_edit.text().strip(): cmd += ["--dualuser", self.lolminer_dualuser_edit.text().strip()]
                if self.lolminer_dualpass_edit.text().strip(): cmd += ["--dualpass", self.lolminer_dualpass_edit.text().strip()]
            return cmd
        except Exception as e:
             self.log_message(f"Fel vid byggande av lolMiner-kommando: {e}", error=True)
             return None

    def build_trex_command(self) -> Optional[List[str]]:
        try:
            path = self.trex_path_edit.text().strip()
            if not path: return None
            cmd = [path]
            if self.trex_config_edit.text().strip(): return cmd + ["-c", self.trex_config_edit.text().strip()]
            if self.trex_benchmark_cb.isChecked():
                cmd.append("-B")
                if self.trex_algo_combo.currentText(): cmd += ["-a", self.trex_algo_combo.currentText()]
                return cmd
            pool_url = self._get_selected_pool("trex")
            if not pool_url: return None
            cmd += ["-o", pool_url]
            if self.trex_algo_combo.currentText(): cmd += ["-a", self.trex_algo_combo.currentText()]
            if self.trex_coin_edit.text(): cmd += ["--coin", self.trex_coin_edit.text()]
            if self.trex_user_edit.text(): cmd += ["-u", self.trex_user_edit.text()]
            if self.trex_pass_edit.text(): cmd += ["-p", self.trex_pass_edit.text()]
            if self.trex_worker_edit.text(): cmd += ["-w", self.trex_worker_edit.text()]
            if self.trex_url2_edit.text(): cmd += ["--url2", self.trex_url2_edit.text()]
            if self.trex_user2_edit.text(): cmd += ["--user2", self.trex_user2_edit.text()]
            if self.trex_pass2_edit.text(): cmd += ["--pass2", self.trex_pass2_edit.text()]
            if self.trex_worker2_edit.text(): cmd += ["--worker2", self.trex_worker2_edit.text()]
            if self.trex_devices_edit.text(): cmd += ["-d", self.trex_devices_edit.text()]
            if self.trex_intensity_edit.text(): cmd += ["-i", self.trex_intensity_edit.text()]
            if self.trex_low_load_cb.isChecked(): cmd.append("--low-load")
            if self.trex_fan_edit.text(): cmd += ["--fan", self.trex_fan_edit.text()]
            if self.trex_pl_edit.text(): cmd += ["--pl", self.trex_pl_edit.text()]
            if self.trex_cclock_edit.text(): cmd += ["--cclock", self.trex_cclock_edit.text()]
            if self.trex_lock_cclock_edit.text(): cmd += ["--lock-cclock", self.trex_lock_cclock_edit.text()]
            if self.trex_mclock_edit.text(): cmd += ["--mclock", self.trex_mclock_edit.text()]
            if self.trex_lock_cv_edit.text(): cmd += ["--lock-cv", self.trex_lock_cv_edit.text()]
            if self.trex_mt_edit.text(): cmd += ["--mt", self.trex_mt_edit.text()]
            if self.trex_lhr_tune_edit.text() != "-1": cmd += ["--lhr-tune", self.trex_lhr_tune_edit.text()]
            if self.trex_lhr_autotune_combo.currentText() != "down": cmd += ["--lhr-autotune-mode", self.trex_lhr_autotune_combo.currentText()]
            if self.trex_api_bind_edit.text() != "127.0.0.1:4067": cmd += ["--api-bind-http", self.trex_api_bind_edit.text()]
            if self.trex_api_https_cb.isChecked(): cmd.append("--api-https")
            if self.trex_api_key_edit.text(): cmd += ["--api-key", self.trex_api_key_edit.text()]
            if self.trex_api_read_only_cb.isChecked(): cmd.append("--api-read-only")
            if self.trex_quiet_cb.isChecked(): cmd.append("-q")
            if self.trex_no_color_cb.isChecked(): cmd.append("--no-color")
            if self.trex_log_path_edit.text(): cmd += ["-l", self.trex_log_path_edit.text()]
            if self.trex_protocol_dump_cb.isChecked(): cmd.append("-P")
            if self.trex_no_watchdog_cb.isChecked(): cmd.append("--no-watchdog")
            if self.trex_watchdog_exit_edit.text(): cmd += ["--watchdog-exit-mode", self.trex_watchdog_exit_edit.text()]
            return cmd
        except Exception as e:
             self.log_message(f"Fel vid byggande av T-Rex-kommando: {e}", error=True)
             return None

    def build_xmrig_command(self) -> Optional[List[str]]:
        try:
            path = self.xmrig_path_edit.text().strip()
            if not path: return None
            cmd = [path]
            if self.xmrig_config_file_edit.text().strip(): return cmd + ["-c", self.xmrig_config_file_edit.text().strip()]
            pool_url = self._get_selected_pool("xmrig")
            if not pool_url: return None
            cmd += ["-o", pool_url]
            if self.xmrig_algo_edit.text(): cmd += ["-a", self.xmrig_algo_edit.text()]
            if self.xmrig_coin_edit.text(): cmd += ["--coin", self.xmrig_coin_edit.text()]
            if self.xmrig_userpass_edit.text(): cmd += ["-O", self.xmrig_userpass_edit.text()]
            else:
                if self.xmrig_user_edit.text(): cmd += ["-u", self.xmrig_user_edit.text()]
                if self.xmrig_pass_edit.text(): cmd += ["-p", self.xmrig_pass_edit.text()]
            if self.xmrig_proxy_edit.text(): cmd += ["-x", self.xmrig_proxy_edit.text()]
            if self.xmrig_keepalive_cb.isChecked(): cmd.append("-k")
            if self.xmrig_nicehash_cb.isChecked(): cmd.append("--nicehash")
            if self.xmrig_rigid_edit.text(): cmd += ["--rig-id", self.xmrig_rigid_edit.text()]
            if self.xmrig_tls_cb.isChecked(): cmd.append("--tls")
            if self.xmrig_tls_fp_edit.text(): cmd += ["--tls-fingerprint", self.xmrig_tls_fp_edit.text()]
            if self.xmrig_daemon_cb.isChecked(): cmd.append("--daemon")
            if self.xmrig_dns_ipv6_cb.isChecked(): cmd.append("--dns-ipv6")
            if self.xmrig_no_cpu_cb.isChecked(): cmd.append("--no-cpu")
            else:
                if self.xmrig_threads_edit.text(): cmd += ["-t", self.xmrig_threads_edit.text()]
                if self.xmrig_cpu_affinity_edit.text(): cmd += ["--cpu-affinity", self.xmrig_cpu_affinity_edit.text()]
                if self.xmrig_av_spin.value() != 0: cmd += ["-v", str(self.xmrig_av_spin.value())]
                if self.xmrig_cpu_priority_spin.value() != 2: cmd += ["--cpu-priority", str(self.xmrig_cpu_priority_spin.value())]
                if self.xmrig_no_huge_pages_cb.isChecked(): cmd.append("--no-huge-pages")
                if self.xmrig_randomx_no_numa_cb.isChecked(): cmd.append("--randomx-no-numa")
            if self.xmrig_http_port_spin.value() != 0: cmd += ["--http-port", str(self.xmrig_http_port_spin.value())]
            if self.xmrig_http_access_token_edit.text(): cmd += ["--http-access-token", self.xmrig_http_access_token_edit.text()]
            if self.xmrig_log_file_edit.text(): cmd += ["-l", self.xmrig_log_file_edit.text()]
            if self.xmrig_verbose_cb.isChecked(): cmd.append("--verbose")
            if self.xmrig_background_cb.isChecked(): cmd.append("-B")
            return cmd
        except Exception as e:
             self.log_message(f"Fel vid byggande av XMRig-kommando: {e}", error=True)
             return None

    # ======================================================================
    # === EVENT HANDLING & UTILITIES ===
    # ======================================================================

    def closeEvent(self, event):
        self.log_message("Avslutar Miner Controller...")
        self.save_settings()
        self.stop_polling()
        for miner_key in list(self.miner_processes.keys()):
             process = self.miner_processes.get(miner_key)
             if process and process.state() != QProcess.ProcessState.NotRunning:
                  self.log_message(f"Försöker stoppa {miner_key.capitalize()} vid avslut...")
                  self.stop_miner_process(miner_key, manual_stop=True)
                  process.waitForFinished(1000)
        event.accept()

# --- Main Execution ---
if __name__ == "__main__":
    QApplication.setOrganizationName("MinerHub")
    QApplication.setApplicationName("Unified-Miner-Controller")

    app = QApplication(sys.argv)
    hub = MinerHubGUI()
    hub.show()
    sys.exit(app.exec_())
