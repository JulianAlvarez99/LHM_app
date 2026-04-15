"""
Bootstrapper / Auto-Updater
Verifica si hay actualizaciones en el repositorio Git y realiza un git pull
antes de lanzar la aplicación principal.
"""

import sys
import os
import subprocess
import time
import logging

# ─── Rutas ─────────────────────────────────────────────────────────────────────
# Cuando se compila con PyInstaller, sys.executable apunta al exe real.
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LOG_FILE = os.path.join(BASE_DIR, "updater.log")
MAIN_APP  = os.path.join(BASE_DIR, "app", "main_app.py")

# ─── Logger ─────────────────────────────────────────────────────────────────────
logging.basicConfig(
    filename=LOG_FILE,
    filemode="a",
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger("Updater")
# También imprimir en consola durante desarrollo
_ch = logging.StreamHandler(sys.stdout)
_ch.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s", "%H:%M:%S"))
log.addHandler(_ch)


# ─── Helpers ────────────────────────────────────────────────────────────────────

def _git(*args, cwd=BASE_DIR) -> tuple[int, str, str]:
    """Ejecuta un comando git y retorna (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return -1, "", "Git no encontrado en el PATH del sistema."
    except subprocess.TimeoutExpired:
        return -2, "", "Timeout esperando respuesta de git."


def check_internet() -> bool:
    """Comprueba conectividad intentando resolver github.com."""
    import socket
    try:
        socket.setdefaulttimeout(5)
        socket.getaddrinfo("github.com", 443)
        return True
    except OSError:
        return False


def check_for_updates() -> bool:
    """Devuelve True si hay commits nuevos en el remoto."""
    log.info("Verificando actualizaciones (git fetch)...")
    code, _, err = _git("fetch", "origin")
    if code != 0:
        log.warning(f"No se pudo hacer fetch: {err}")
        return False

    # Comparar HEAD local con origin/HEAD
    code, local,  _ = _git("rev-parse", "HEAD")
    code, remote, _ = _git("rev-parse", "@{u}")   # upstream

    if local != remote:
        log.info(f"Actualización disponible: {local[:7]} → {remote[:7]}")
        return True

    log.info("La aplicación ya está en la última versión.")
    return False


def apply_update() -> bool:
    """Realiza git pull. Retorna True si fue exitoso."""
    log.info("Aplicando actualización (git pull)...")
    code, out, err = _git("pull", "--rebase", "origin")
    if code == 0:
        log.info(f"Pull exitoso:\n{out}")
        return True

    log.error(f"Error durante git pull (código {code}):\n{err}")
    # Intento de recuperación: abortar rebase si quedó pendiente
    _git("rebase", "--abort")
    return False


def launch_app():
    """Lanza la aplicación principal."""
    # Como los .py se actualizan desde GitHub, debemos ejecutar Python del venv local.
    python = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
    
    # Fallback por si lo ejecutan en la misma pc de desarollo (sin compilar)
    if not os.path.exists(python):
        python = sys.executable
        
    log.info(f"Lanzando aplicación principal: {MAIN_APP} con {python}")
    try:
        proc = subprocess.Popen(
            [python, MAIN_APP],
            cwd=BASE_DIR,
        )
        proc.wait()
        log.info(f"Aplicación finalizada con código {proc.returncode}.")
    except Exception as e:
        log.critical(f"No se pudo iniciar la aplicación principal: {e}")
        sys.exit(1)


# ─── Main ────────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("LHM Telemetry App - Bootstrapper iniciado")
    log.info("=" * 60)

    # 1. Verificar internet
    if check_internet():
        try:
            if check_for_updates():
                ok = apply_update()
                if not ok:
                    log.warning("Actualización fallida; se lanzará la versión local actual.")
        except Exception as exc:
            log.error(f"Error inesperado durante actualización: {exc}", exc_info=True)
    else:
        log.warning("Sin conexión a internet. Se omite la búsqueda de actualizaciones.")

    # 2. Lanzar app
    launch_app()


if __name__ == "__main__":
    main()
