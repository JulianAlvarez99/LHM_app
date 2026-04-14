"""
UpdateWorker — QThread que ejecuta la lógica del bootstrapper
sin bloquear la interfaz gráfica.
"""

import sys
import os
import subprocess
import socket
import logging

from PySide6.QtCore import QThread, Signal

log = logging.getLogger("UpdateWorker")


class UpdateWorker(QThread):
    """Realiza git fetch + git pull en segundo plano."""

    progress = Signal(str)  # mensajes de texto para la GUI
    finished  = Signal(bool)  # True si hubo actualización exitosa

    def __init__(self, repo_dir: str, parent=None):
        super().__init__(parent)
        self.repo_dir = repo_dir

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _git(self, *args) -> tuple[int, str, str]:
        try:
            r = subprocess.run(
                ["git"] + list(args),
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return r.returncode, r.stdout.strip(), r.stderr.strip()
        except FileNotFoundError:
            return -1, "", "Git no encontrado."
        except subprocess.TimeoutExpired:
            return -2, "", "Timeout."

    def _has_internet(self) -> bool:
        try:
            socket.setdefaulttimeout(5)
            socket.getaddrinfo("github.com", 443)
            return True
        except OSError:
            return False

    # ─── Ciclo principal ──────────────────────────────────────────────────────

    def run(self):
        self.progress.emit("Verificando conexión a internet...")

        if not self._has_internet():
            self.progress.emit("Sin conexión. Se omite la búsqueda de actualizaciones.")
            self.finished.emit(False)
            return

        self.progress.emit("Conectado. Buscando actualizaciones (git fetch)...")
        code, _, err = self._git("fetch", "origin")
        if code != 0:
            self.progress.emit(f"Error al contactar el repositorio remoto: {err}")
            self.finished.emit(False)
            return

        _, local,  _ = self._git("rev-parse", "HEAD")
        _, remote, _ = self._git("rev-parse", "@{u}")

        if local == remote:
            self.progress.emit("✓ La aplicación está en la última versión.")
            self.finished.emit(False)
            return

        self.progress.emit(f"Actualización disponible ({local[:7]} → {remote[:7]}). Aplicando...")
        code, out, err = self._git("pull", "--rebase", "origin")

        if code == 0:
            self.progress.emit(f"✓ Actualización aplicada correctamente.\n{out}")
            self.finished.emit(True)
        else:
            self.progress.emit(f"✗ Error al aplicar la actualización:\n{err}")
            self._git("rebase", "--abort")
            self.finished.emit(False)
