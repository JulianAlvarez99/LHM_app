## 🗂️ Planificación — LHM Telemetry Agent

### Contexto del problema

Actualmente hay **dos ejecutables con roles ambiguos**: `LHM_Capture.exe` (updater/bootstrapper) y `App_Interna.exe` (captura real), pero el flujo entre ellos no está implementado. El updater no hace update, no lanza la app interna, y ambas tienen interfaces que se repiten o confunden al usuario.

---

### 🎯 Objetivo final

```
Usuario abre LHM_Capture.exe
        ↓
[Updater] Conecta al repo → git pull
        ↓
[Updater] Se cierra solo
        ↓
[App_Interna] Se abre → System Tray → captura inicia automáticamente
```

---

### 📋 Tickets

---

#### TICKET 1 — Implementar lógica de auto-update en `updater/main_updater.py`
**Prioridad: Alta**

El updater actualmente no hace nada concreto con el repositorio. Necesita:

- Ejecutar `git fetch origin` y `git reset --hard origin/main` desde el directorio de instalación
- Mostrar progreso en su ventana de consola (ya tiene `console=True` en el spec)
- Manejar el caso sin conexión (timeout, skip silencioso con log)
- Al terminar (éxito o skip), lanzar `App_Interna.exe` con `subprocess.Popen` y luego llamar `sys.exit(0)`

**Archivos:** `updater/main_updater.py`

---

#### TICKET 2 — Eliminar la interfaz duplicada / unificar UX
**Prioridad: Alta**

El problema reportado: *"dos launchers iguales pero con interfaz distinta"*. La causa probable es que `App_Interna.exe` también muestra alguna pantalla de splash o ventana de inicio que replica lo que hace el updater.

- Definir claramente: el updater tiene consola visible con feedback de texto plano
- `App_Interna` arranca **directo al System Tray**, sin ventana de bienvenida ni splash
- Si hay una ventana de "iniciando..." en `app/main_app.py`, eliminarla o convertirla en notificación del tray

**Archivos:** `app/main_app.py`, `updater/main_updater.py`

---

#### TICKET 3 — Arranque automático de captura al iniciar `App_Interna`
**Prioridad: Alta**

Actualmente la captura en `capture.py` se inicia como proceso separado (Scheduled Task). Lo que se busca es que `App_Interna.exe` la inicie internamente:

- Al crear el ícono del tray, lanzar `TelemetryLogger().run()` en un **thread daemon**
- El ícono del tray debe reflejar el estado: capturando / error / detenido
- Menú del tray: "Detener captura", "Reiniciar captura", "Ver logs", "Salir"

**Archivos:** `app/main_app.py`, integración con `capture.py`

---

#### TICKET 4 — Revisar y corregir `service_setup.ps1` y Scheduled Task
**Prioridad: Media**

Con el Ticket 3 implementado, el Scheduled Task debería apuntar a `LHM_Capture.exe` (el updater/bootstrapper), no a un script de PowerShell intermedio. Revisar:

- `run_capture.ps1` referenciado en el `.ps1` probablemente no existe o apunta a lo incorrecto
- El trigger debería lanzar `LHM_Capture.exe` directamente con privilegios de admin
- Evaluar si el `WorkingDir` del task queda bien resuelto post-instalación de Inno Setup

**Archivos:** `service_setup.ps1`, `setup.iss`

---

#### TICKET 5 — Hardening del `setup.iss` (instalador Inno Setup)
**Prioridad: Media**

El instalador actual tiene un riesgo: si `git remote add origin` falla (porque el remote ya existe en reinstalaciones), todo el bloque `[Run]` puede cortarse. Correcciones:

- Agregar `git remote set-url origin ...` como fallback o usar `|| true`
- Verificar que `install.bat` esté siendo llamado con `waituntilterminated` correctamente
- El ícono en `{commonstartup}` debería apuntar a `LHM_Capture.exe` ✅ (ya está bien)

**Archivos:** `setup.iss`

---

#### TICKET 6 — Logging unificado
**Prioridad: Baja**

`capture.py` tiene buen logging con rotación. El updater y `main_app.py` probablemente no. Unificar:

- Un directorio de logs compartido (ej: `%APPDATA%\LHM_Agent\logs\`)
- `updater.log`, `app.log`, `telemetry_capture.log` en el mismo lugar
- Accesible desde el menú del tray (Ticket 3)

**Archivos:** `updater/main_updater.py`, `app/main_app.py`

---

### 🔢 Orden de ejecución sugerido

| Sprint | Tickets | Por qué |
|--------|---------|---------|
| 1 | T2 + T3 | Unifica la UX y hace que la app funcione de punta a punta |
| 2 | T1 | El auto-update tiene sentido una vez que el flujo base funciona |
| 3 | T4 + T5 | Packaging limpio para distribución |
| 4 | T6 | Pulido final |

---