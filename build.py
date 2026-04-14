"""
Script de empaquetado — genera los dos ejecutables con PyInstaller:
  • Lanzador.exe  → updater/main_updater.py  (consola visible para feedback)
  • App_Interna.exe → app/main_app.py        (noconsole, vive en System Tray)
"""

import subprocess
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def run(cmd: list[str]):
    print(f"\n{'='*60}")
    print(f"  Ejecutando: {' '.join(cmd)}")
    print(f"{'='*60}\n")
    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode != 0:
        print(f"[ERROR] Falló con código {result.returncode}")
        sys.exit(result.returncode)


def build_updater():
    """Compila el Bootstrapper como Lanzador.exe."""
    run([
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--onefile",
        "--name", "Lanzador",
        "--icon", "app/assets/icon.ico",
        "--add-data", f"app/assets/style.qss{os.pathsep}app/assets",
        "updater/main_updater.py",
    ])


def build_app():
    """Compila la aplicación principal como App_Interna.exe (sin consola)."""
    # Incluir DLLs de LibreHardwareMonitor y la hoja de estilos
    run([
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--onefile",
        "--noconsole",
        "--name", "App_Interna",
        "--icon", "app/assets/icon.ico",
        "--add-data", f"app/assets/style.qss{os.pathsep}app/assets",
        "--add-data", f"app/assets/icon.ico{os.pathsep}app/assets",
        # Incluir DLLs .NET necesarias
        "--add-binary", f"LibreHardwareMonitorLib.dll{os.pathsep}.",
        "--collect-all", "pythonnet",
        "app/main_app.py",
    ])


if __name__ == "__main__":
    print("======================================")
    print("  LHM Telemetry Agent - Build Script  ")
    print("======================================")

    build_updater()
    build_app()

    print("\n[OK] Compilacion completa. Ejecutables en ./dist/")
    print("  * dist/Lanzador.exe      -> punto de entrada (auto-update)")
    print("  * dist/App_Interna.exe   -> aplicacion principal")
