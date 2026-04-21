"""
CaptureWorker — QThread que encapsula la lógica de TelemetryLogger.
Delega completamente en capture.py: no duplica el bucle de captura.
El esquema productor-consumidor y la resolución de IDs están en capture.py.
"""

import sys
import os
import logging
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import QThread, Signal

# Agregar el directorio raíz al path para poder importar capture.py
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# ─── Conectar al mismo logger y archivo de log que capture.py ─────────────────
# capture.py registra el RotatingFileHandler al importarse, pero nos aseguramos
# de que exista incluso si capture.py aún no fue importado.
_log_file = os.path.join(BASE_DIR, 'telemetry_capture.log')
_log_formatter = logging.Formatter(
    '[%(asctime)s] - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

_hw_logger = logging.getLogger('HardwareTelemetry')
if not any(isinstance(h, RotatingFileHandler) for h in _hw_logger.handlers):
    _file_handler = RotatingFileHandler(
        _log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8'
    )
    _file_handler.setFormatter(_log_formatter)
    _hw_logger.addHandler(_file_handler)
    _hw_logger.setLevel(logging.INFO)

# Logger propio del worker (hereda handlers del root configurado por main_app.py)
log = logging.getLogger("CaptureWorker")


class CaptureWorker(QThread):
    """
    Worker que corre TelemetryLogger.run() en un hilo secundario.
    Emite señales para comunicarse con la GUI sin bloquearla.

    Arquitectura interna de capture.py (delegada aquí por completo):
    - __init__:  carga cache BD + construye sensor_plan (resolución única de IDs)
    - run():     lanza hilo SensorProducer (_producer_loop) y ejecuta el
                 consumidor (_consumer_loop) en el hilo llamante.
    - stop():    setea _stop_event para apagado limpio de ambos hilos.
    """

    # Señales para la GUI
    status_changed = Signal(str)   # "running" | "stopped" | "error"
    log_message    = Signal(str)   # mensaje para el panel de logs
    db_connected   = Signal(bool)  # True/False según estado de conexión DB

    def __init__(self, parent=None):
        super().__init__(parent)
        self._logger_instance = None

    # ─── Ciclo principal del QThread ──────────────────────────────────────────

    def run(self):
        """
        Inicializa TelemetryLogger y delega en su run().
        TelemetryLogger.run() lanza internamente el hilo SensorProducer y
        bloquea en el _consumer_loop hasta que _stop_event sea seteado.
        """
        self.status_changed.emit("running")
        self.log_message.emit("Inicializando captura de telemetría...")
        _hw_logger.info("CaptureWorker: iniciando inicialización de TelemetryLogger.")

        try:
            # Importar aquí para que el os.chdir() de capture.py ocurra en
            # este contexto de hilo, no en el principal.
            from capture import TelemetryLogger

            # __init__ realiza: conexión DB + init LHM + carga cache + build sensor_plan
            self._logger_instance = TelemetryLogger()

            self.db_connected.emit(True)
            self.log_message.emit(
                f"Conexión a base de datos establecida. "
                f"Plan: {len(self._logger_instance.sensor_plan)} sensores activos. "
                f"Intervalo: {self._logger_instance.update_time}s | "
                f"Tabla: {self._logger_instance.table_name}"
            )
            self.status_changed.emit("running")

        except Exception as e:
            self.status_changed.emit("error")
            self.db_connected.emit(False)
            self.log_message.emit(f"✗ Error al inicializar: {e}")
            _hw_logger.error(f"CaptureWorker: error fatal durante inicialización: {e}", exc_info=True)
            log.critical(f"Error fatal en CaptureWorker.__init__: {e}", exc_info=True)
            return

        try:
            # TelemetryLogger.run() bloquea aquí hasta que _stop_event sea seteado.
            # Internamente lanza SensorProducer (daemon thread) y corre _consumer_loop.
            self._logger_instance.run()

        except Exception as e:
            self.status_changed.emit("error")
            self.db_connected.emit(False)
            self.log_message.emit(f"✗ Error durante captura: {e}")
            _hw_logger.error(f"CaptureWorker: error fatal durante run(): {e}", exc_info=True)
            log.critical(f"Error fatal en CaptureWorker.run(): {e}", exc_info=True)
            return

        # Llegamos aquí solo si _consumer_loop terminó limpiamente
        self.db_connected.emit(False)
        self.status_changed.emit("stopped")
        self.log_message.emit("Captura detenida correctamente.")
        _hw_logger.info("CaptureWorker: captura finalizada correctamente.")

    # ─── Control externo ──────────────────────────────────────────────────────

    def stop(self):
        """
        Solicita la detención limpia del ciclo de captura.
        Setea _stop_event de TelemetryLogger para interrumpir el productor
        y el consumidor. TelemetryLogger.run() se encarga del join y cleanup.
        """
        self.log_message.emit("Deteniendo captura...")
        _hw_logger.info("CaptureWorker: detención solicitada por la GUI.")

        if self._logger_instance is not None:
            # _stop_event interrumpe: _producer_loop (wait), _consumer_loop (get timeout)
            # y _reconnect_db (wait). capture.py hace join + pc.Close() + conn.close().
            self._logger_instance._stop_event.set()
        else:
            log.warning("CaptureWorker.stop() llamado antes de que la instancia existiera.")
