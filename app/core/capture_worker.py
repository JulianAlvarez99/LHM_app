"""
CaptureWorker — QThread que encapsula la lógica de TelemetryLogger.
Hereda directamente de capture.py (sin duplicar código).
"""

import sys
import os
import time
import logging

from PySide6.QtCore import QThread, Signal

# Agregar el directorio raíz al path para poder importar capture.py
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

log = logging.getLogger("CaptureWorker")


class CaptureWorker(QThread):
    """
    Worker que corre TelemetryLogger.run() en un hilo secundario.
    Emite señales para comunicarse con la GUI sin bloquearla.
    """

    # Señales para la GUI
    status_changed = Signal(str)   # "running" | "stopped" | "error"
    log_message    = Signal(str)   # mensaje para el panel de logs
    db_connected   = Signal(bool)  # True/False según estado de conexión DB

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._logger_instance = None
        self._stop_requested = False

    # ─── Ciclo principal del hilo ─────────────────────────────────────────────

    def run(self):
        """Ejecuta el bucle de captura en segundo plano."""
        self._stop_requested = False
        self.status_changed.emit("running")
        self.log_message.emit("Inicializando captura de telemetría...")

        try:
            # Importar aquí para que el chdir de capture.py ocurra en este contexto
            from capture import TelemetryLogger

            self._logger_instance = TelemetryLogger()
            self.db_connected.emit(True)
            self.log_message.emit("Conexión a base de datos establecida.")
            self.status_changed.emit("running")

            # Bucle de captura adaptado para poder detenerlo desde la GUI
            import clr  # noqa: F401  ya cargado por TelemetryLogger.__init__
            import psycopg2
            from psycopg2 import extras
            from datetime import datetime

            inst = self._logger_instance
            LHM_TO_DB_HW = {
                "Cpu": "CPU", "GpuNvidia": "GPU", "GpuAti": "GPU",
                "Motherboard": "MOTHERBOARD", "SuperIO": "MOTHERBOARD",
                "Memory": "MEMORIA RAM", "Storage": "ALMACENAMIENTO",
            }

            self.log_message.emit(
                f"Captura iniciada. Intervalo: {inst.update_time}s | "
                f"Tabla: {inst.table_name}"
            )
            
            fallos_consecutivos = 0
            
            while not self._stop_requested:
                try:
                    now = datetime.now()
                    raw_sensors = inst._get_sensors_recursive(inst.pc.Hardware)
                    to_db = []

                    for lhm_hw_type, _, s_name, s_type, s_val in raw_sensors:
                        if s_name == "Memory" and "Virtual Memory" in _:
                            s_name = "Virtual Memory"
                        db_hw_type = LHM_TO_DB_HW.get(lhm_hw_type, "").upper()
                        h_id = inst.cache_hw.get(db_hw_type)
                        s_id = inst._resolve_sensor_id(s_name, s_type)
                        if h_id is not None and s_id is not None:
                            val = float(s_val) if s_val is not None else 0.0
                            to_db.append((now, h_id, s_id, _, val))

                    if to_db:
                        with inst.conn.cursor() as cur:
                            query = (
                                f"INSERT INTO {inst.table_name} "
                                "(timestamp, hardware_id, sensor_id, hardware_name, value) VALUES %s"
                            )
                            extras.execute_values(cur, query, to_db)
                            inst.conn.commit()

                        msg = f"✓ {len(to_db)} registros insertados"
                        self.log_message.emit(msg)

                    fallos_consecutivos = 0

                    # Esperar en intervalos pequeños para responder a stop_requested
                    for _ in range(inst.update_time * 2):
                        if self._stop_requested:
                            break
                        time.sleep(0.5)

                except Exception as e:
                    fallos_consecutivos += 1
                    is_connection_error = isinstance(e, (psycopg2.OperationalError, psycopg2.InterfaceError))
                    
                    if is_connection_error:
                        self.db_connected.emit(False)
                        self.log_message.emit(f"⚠ Error crítico de conexión: {e}. Reconectando...")
                        inst._reconnect_db()
                        self.db_connected.emit(True)
                        self.log_message.emit("✓ Reconexión exitosa.")
                        fallos_consecutivos = 0
                    else:
                        self.log_message.emit(f"✗ Error en ciclo (Fallo {fallos_consecutivos}/3): {e}")
                        log.error(f"Error ciclo captura (Fallo {fallos_consecutivos}/3): {e}", exc_info=True)
                        if fallos_consecutivos >= 3:
                            self.log_message.emit("Reconectando DB forzadamente tras fallos sucesivos...")
                            inst._reconnect_db()
                            self.db_connected.emit(True)
                            fallos_consecutivos = 0
                        else:
                            for _ in range(10):  # Esperar 5s (intento)
                                if self._stop_requested:
                                    break
                                time.sleep(0.5)

        except Exception as e:
            self.status_changed.emit("error")
            self.db_connected.emit(False)
            self.log_message.emit(f"✗ Error al inicializar: {e}")
            log.critical(f"Error fatal en CaptureWorker: {e}", exc_info=True)
            return

        finally:
            self._cleanup()

        self.status_changed.emit("stopped")
        self.log_message.emit("Captura detenida correctamente.")

    def _cleanup(self):
        """Libera recursos de LHM y DB."""
        try:
            if self._logger_instance:
                inst = self._logger_instance
                inst.pc.Close()
                if inst.conn and not inst.conn.closed:
                    inst.conn.close()
                self.log_message.emit("Recursos LHM y DB liberados.")
        except Exception as e:
            log.warning(f"Error durante cleanup: {e}")

    # ─── Control externo ──────────────────────────────────────────────────────

    def stop(self):
        """Solicita la detención del hilo de captura."""
        self._stop_requested = True
        self.log_message.emit("Deteniendo captura...")
