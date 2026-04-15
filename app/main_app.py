"""
Punto de entrada — Aplicación principal (GUI + Daemon de captura).
Carga el estilo, instancia la ventana y arranca el event loop de Qt.
"""

import sys
import os
import logging
from logging.handlers import RotatingFileHandler

# ─── Rutas ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR  = os.path.dirname(os.path.abspath(__file__))

# Al compilar con PyInstaller usamos sys._MEIPASS para localizar assets
def _resource(rel_path: str) -> str:
    base = getattr(sys, "_MEIPASS", BASE_DIR)
    return os.path.join(base, rel_path)

# ─── Logger global ────────────────────────────────────────────────────────────
log_file = os.path.join(BASE_DIR, "app.log")
logging.basicConfig(
    handlers=[
        RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=2, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
    format="[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger("MainApp")

# ─── PySide6 ─────────────────────────────────────────────────────────────────
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Agregar rutas al sys.path para resolver imports relativos
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.gui.dashboard import MainWindow


def _load_stylesheet(app: QApplication):
    qss_path = os.path.join(APP_DIR, "assets", "style.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
        log.info(f"Stylesheet cargado: {qss_path}")
    else:
        log.warning(f"Stylesheet no encontrado en {qss_path}")


def main():
    # Separación nativa en Taskbar y DPI para Windows
    if os.name == 'nt':
        try:
            import ctypes
            myappid = 'camet.lhm.telemetry.1.0'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    from PySide6.QtGui import QIcon
    icon_path = os.path.join(APP_DIR, "assets", "icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    app.setApplicationName("LHM Telemetry Agent")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Camet")

    # Mantener app corriendo aunque se cierren todas las ventanas (vive en tray)
    app.setQuitOnLastWindowClosed(False)

    _load_stylesheet(app)

    window = MainWindow()
    # Ticket 2: Arrancar en el System Tray
    # window.show()

    # Ticket 3: Iniciar captura automaticamente
    window._on_start()

    log.info("Aplicación iniciada en System Tray.")
    ret = app.exec()
    log.info(f"Aplicación cerrada con código {ret}.")
    sys.exit(ret)


if __name__ == "__main__":
    main()
