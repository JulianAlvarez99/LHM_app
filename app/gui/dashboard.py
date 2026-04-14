"""
Dashboard principal — ventana con System Tray.
Muestra estado del servicio, logs y controles.
"""

import sys
import os
import logging
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QFrame,
    QSystemTrayIcon, QMenu, QApplication,
    QSizePolicy, QSpacerItem,
)
from PySide6.QtCore import Qt, QSize, QTimer, Slot
from PySide6.QtGui import QIcon, QColor, QPalette, QFont, QPixmap, QPainter, QBrush

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

log = logging.getLogger("Dashboard")


# ─── Helpers de icono ─────────────────────────────────────────────────────────

def _make_tray_icon(color: str = "#4ade80") -> QIcon:
    """Genera un ícono de bandeja de sistema sencillo con un círculo de color."""
    px = QPixmap(32, 32)
    px.fill(Qt.transparent)  # type: ignore[attr-defined]
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)  # type: ignore[attr-defined]
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.NoPen)  # type: ignore[attr-defined]
    p.drawEllipse(4, 4, 24, 24)
    p.end()
    return QIcon(px)


# ─── Panel de estado ──────────────────────────────────────────────────────────

class StatusCard(QFrame):
    """Tarjeta pequeña que muestra un KPI (etiqueta + valor)."""

    def __init__(self, title: str, initial: str = "—", parent=None):
        super().__init__(parent)
        self.setObjectName("statusCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        self._title = QLabel(title)
        self._title.setObjectName("cardTitle")
        layout.addWidget(self._title)

        self._value = QLabel(initial)
        self._value.setObjectName("cardValue")
        layout.addWidget(self._value)

    def set_value(self, text: str, color: str = "#e2e8f0"):
        self._value.setText(text)
        self._value.setStyleSheet(f"color: {color};")


# ─── Ventana principal ────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LHM Telemetry Agent")
        self.setMinimumSize(880, 620)
        self._capture_worker = None
        self._update_worker  = None
        self._records_count  = 0
        self._start_time     = None

        self._setup_ui()
        self._setup_tray()
        self._setup_uptime_timer()

    # ─── UI ───────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ──
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(64)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(24, 0, 24, 0)

        logo_label = QLabel("⚡ LHM Telemetry Agent")
        logo_label.setObjectName("appTitle")
        h_layout.addWidget(logo_label)

        h_layout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self._version_label = QLabel("Comprobando versión...")
        self._version_label.setObjectName("versionLabel")
        h_layout.addWidget(self._version_label)

        root.addWidget(header)

        # ── Cuerpo principal ──
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(24, 24, 24, 24)
        body_layout.setSpacing(20)

        # Panel izquierdo (controles + KPIs)
        left_panel = QWidget()
        left_panel.setFixedWidth(280)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(16)

        # KPIs
        self._card_status = StatusCard("Estado del servicio", "Detenido")
        self._card_db     = StatusCard("Base de datos", "Desconectada")
        self._card_uptime = StatusCard("Tiempo activo", "—")
        self._card_count  = StatusCard("Registros enviados", "0")

        for card in (self._card_status, self._card_db, self._card_uptime, self._card_count):
            left_layout.addWidget(card)

        left_layout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))

        # Botones
        self._btn_start = QPushButton("▶  Iniciar captura")
        self._btn_start.setObjectName("btnPrimary")
        self._btn_start.clicked.connect(self._on_start)

        self._btn_stop = QPushButton("■  Detener captura")
        self._btn_stop.setObjectName("btnDanger")
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._on_stop)

        self._btn_update = QPushButton("↻  Buscar actualizaciones")
        self._btn_update.setObjectName("btnSecondary")
        self._btn_update.clicked.connect(self._on_check_update)

        for btn in (self._btn_start, self._btn_stop, self._btn_update):
            btn.setMinimumHeight(40)
            left_layout.addWidget(btn)

        body_layout.addWidget(left_panel)

        # Panel derecho (log)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        log_header = QHBoxLayout()
        log_title = QLabel("Registro de eventos")
        log_title.setObjectName("sectionTitle")
        log_header.addWidget(log_title)
        log_header.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))

        btn_clear = QPushButton("Limpiar")
        btn_clear.setObjectName("btnGhost")
        btn_clear.setFixedWidth(80)
        btn_clear.clicked.connect(self._on_clear_log)
        log_header.addWidget(btn_clear)

        right_layout.addLayout(log_header)

        self._log_view = QTextEdit()
        self._log_view.setObjectName("logView")
        self._log_view.setReadOnly(True)
        self._log_view.setFont(QFont("Consolas", 9))
        right_layout.addWidget(self._log_view)

        body_layout.addWidget(right_panel)
        root.addWidget(body)

        # ── Status bar ──
        self._status_bar = QLabel("Listo.")
        self._status_bar.setObjectName("statusBar")
        self._status_bar.setFixedHeight(28)
        self._status_bar.setContentsMargins(16, 0, 16, 0)
        root.addWidget(self._status_bar)

    def _setup_tray(self):
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(_make_tray_icon("#94a3b8"))
        self._tray.setToolTip("LHM Telemetry Agent – Detenido")

        menu = QMenu()
        menu.addAction("Mostrar ventana", self.show_window)
        menu.addSeparator()
        menu.addAction("Iniciar captura",   self._on_start)
        menu.addAction("Detener captura",   self._on_stop)
        menu.addSeparator()
        menu.addAction("Salir",             self._on_quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _setup_uptime_timer(self):
        self._uptime_timer = QTimer(self)
        self._uptime_timer.setInterval(1000)
        self._uptime_timer.timeout.connect(self._update_uptime)

    # ─── Slots ────────────────────────────────────────────────────────────────

    @Slot()
    def _on_start(self):
        if self._capture_worker and self._capture_worker.isRunning():
            return

        from app.core.capture_worker import CaptureWorker
        self._capture_worker = CaptureWorker()
        self._capture_worker.status_changed.connect(self._on_capture_status)
        self._capture_worker.log_message.connect(self._append_log)
        self._capture_worker.db_connected.connect(self._on_db_status)
        self._capture_worker.start()

        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._start_time = datetime.now()
        self._uptime_timer.start()
        self._records_count = 0
        self._card_count.set_value("0")

    @Slot()
    def _on_stop(self):
        if self._capture_worker:
            self._capture_worker.stop()
            self._capture_worker.wait(5000)

        self._uptime_timer.stop()
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._card_uptime.set_value("—")

    @Slot()
    def _on_check_update(self):
        from app.core.update_worker import UpdateWorker
        self._update_worker = UpdateWorker(BASE_DIR)
        self._update_worker.progress.connect(self._append_log)
        self._update_worker.finished.connect(self._on_update_finished)
        self._btn_update.setEnabled(False)
        self._update_worker.start()

    @Slot(bool)
    def _on_update_finished(self, updated: bool):
        self._btn_update.setEnabled(True)
        if updated:
            self._append_log("🔄 Reinicia la aplicación para aplicar los cambios.")
            self._version_label.setText("¡Actualización aplicada! Reinicia la app.")
            self._version_label.setStyleSheet("color: #fbbf24;")
        else:
            self._version_label.setText("✓ Versión actual")
            self._version_label.setStyleSheet("color: #4ade80;")

    @Slot(str)
    def _on_capture_status(self, status: str):
        colors = {"running": "#4ade80", "stopped": "#94a3b8", "error": "#f87171"}
        labels = {"running": "En ejecución", "stopped": "Detenido", "error": "Error"}
        color = colors.get(status, "#94a3b8")
        label = labels.get(status, status)

        self._card_status.set_value(label, color)
        self._tray.setIcon(_make_tray_icon(color))
        tip = f"LHM Telemetry Agent – {label}"
        self._tray.setToolTip(tip)
        self._status_bar.setText(f"Estado: {label}")

    @Slot(bool)
    def _on_db_status(self, connected: bool):
        if connected:
            self._card_db.set_value("Conectada", "#4ade80")
        else:
            self._card_db.set_value("Desconectada", "#f87171")

    @Slot(str)
    def _append_log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_view.append(f"[{ts}] {msg}")
        # Auto-scroll
        sb = self._log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

        # Contar registros insertados
        if msg.startswith("✓") and "registros" in msg:
            try:
                n = int(msg.split()[1])
                self._records_count += n
                self._card_count.set_value(f"{self._records_count:,}")
            except (IndexError, ValueError):
                pass

    @Slot()
    def _on_clear_log(self):
        self._log_view.clear()

    @Slot()
    def _update_uptime(self):
        if self._start_time:
            delta = datetime.now() - self._start_time
            total = int(delta.total_seconds())
            h, rem = divmod(total, 3600)
            m, s   = divmod(rem, 60)
            self._card_uptime.set_value(f"{h:02d}:{m:02d}:{s:02d}", "#e2e8f0")

    @Slot()
    def show_window(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    @Slot()
    def _on_quit(self):
        self._on_stop()
        QApplication.quit()

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window()

    # ─── Eventos de ventana ───────────────────────────────────────────────────

    def closeEvent(self, event):
        """Minimizar al tray en vez de cerrar."""
        event.ignore()
        self.hide()
        self._tray.showMessage(
            "LHM Telemetry Agent",
            "La aplicación sigue corriendo en la bandeja del sistema.",
            QSystemTrayIcon.Information,
            2500,
        )
