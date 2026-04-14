Como desarrollador full stack senior, entiendo perfectamente el objetivo: transformar este conjunto de scripts de captura y dependencias (LibreHardwareMonitor) en una aplicación de escritorio robusta, mantenible y con capacidad de auto-actualización. 

Para lograr esto respetando principios de arquitectura limpia (como SRP y DRY, separando responsabilidades), lo ideal es dividir el sistema en dos componentes principales: un **Bootstrapper (Actualizador)** y la **Aplicación Principal (GUI + Daemon de captura)**.

Aquí tienes la planificación estratégica y técnica paso a paso para construir esta aplicación en tu entorno Windows.

### Fase 1: Arquitectura del Auto-Updater (Bootstrapper)

Depender de un `git pull` directo en producción tiene un riesgo: si hay conflictos locales o el cliente no tiene Git instalado, el proceso falla. Sin embargo, para un entorno de estación de trabajo controlada, es un MVP válido. La mejor práctica es crear un pequeño ejecutable independiente (el Bootstrapper) que se lance primero.

1.  **Lógica del Bootstrapper:**
    * Al ejecutar la app, el sistema operativo llama al Bootstrapper.
    * Este verifica la conexión a internet y hace un `git fetch` + `git status` (o consulta la API de GitHub para ver si hay un nuevo *Release*).
    * Si hay actualización: realiza el `git pull` (o descarga y extrae el nuevo código/binario), sobrescribiendo los archivos antiguos.
    * Una vez actualizado (o si ya está en la última versión), el Bootstrapper lanza el subproceso de la Aplicación Principal y se cierra.
2.  **Implementación:** Puedes escribir este actualizador en un script de Python independiente (`updater.py`) que luego compilarás como el ejecutable principal (`app.exe`).

### Fase 2: La Interfaz Gráfica (GUI) y el System Tray

Dado que el núcleo de la herramienta es la captura de telemetría de hardware, la aplicación no debería molestar en la barra de tareas todo el tiempo. Lo ideal es una aplicación que viva en la bandeja del sistema (System Tray).

1.  **Framework Recomendado:** **PySide6** (o PyQt6). Es extremadamente potente para Windows 11, permite integraciones nativas y es fácil de empaquetar. Alternativamente, si buscas algo más ligero, `CustomTkinter` es una excelente opción moderna.
2.  **Diseño de la Interfaz:**
    * **Dashboard Principal:** Una ventana que muestre el estado del servicio (LHM corriendo, estado de la conexión a la base de datos).
    * **Controles:** Botones para Iniciar/Detener la captura manualmente, y forzar la búsqueda de actualizaciones.
    * **System Tray:** Un icono junto al reloj que permita minimizar la app. Un clic derecho desplegaría un menú contextual (Estado, Configuración, Salir).

### Fase 3: Refactorización y Gestión del Daemon de Captura

El código actual tiene la lógica de captura (`capture.py`), la configuración de la base de datos (`db_setup.py`) y el manejo de LibreHardwareMonitor en scripts separados. En la app de escritorio, esto se convierte en el "Daemon" o hilo en segundo plano (Background Worker).

1.  **Aislamiento del Hilo (QThread):** Para que la interfaz gráfica no se congele mientras el script lee los sensores o escribe en la base de datos, toda la ejecución de `capture.py` debe moverse a un hilo secundario (por ejemplo, usando `QThread` en PySide6).
2.  **Gestión de Subprocesos (LHM):** La aplicación Python ahora será la responsable de asegurar que `LibreHardwareMonitor.exe` se inicie silenciosamente cuando la captura comience y se cierre correctamente al salir de la aplicación.
3.  **Lógica de Base de Datos:** El trabajador en segundo plano seguirá manejando la inserción de métricas en las particiones de 1 hora en TimescaleDB. Es crucial que este mismo demonio (o una tarea programada interna de la app) valide y ejecute la política de compresión para todos los datos que tengan más de 7 días de antigüedad, manteniendo la base de datos optimizada sin intervención manual.

### Fase 4: Estructura de Directorios Propuesta

Para mantener el código escalable, te sugiero reorganizar el repositorio de la siguiente manera antes de construir la GUI:

```text
/proyecto-telemetria
│
├── /updater                # Lógica del bootstrapper y git pull
│   └── main_updater.py
│
├── /app                    # Aplicación principal
│   ├── /gui                # Vistas y componentes PySide6
│   ├── /core               # capture.py, db_setup.py adaptados a clases
│   └── main_app.py         # Punto de entrada de la interfaz
│
├── /bin                    # LHM y sus .dlls
│
├── requirements.txt
└── build.py                # Script para generar los ejecutables
```

### Fase 5: Empaquetado y Distribución

Una vez que el actualizador y la aplicación funcionan juntos, necesitas empaquetarlo para que se comporte como una aplicación nativa de Windows.

1.  **PyInstaller:** Utiliza PyInstaller para compilar ambos puntos de entrada. 
    * Compila `main_updater.py` como `Lanzador.exe` (con un icono bonito).
    * Compila `main_app.py` como `App_Interna.exe` (en modo `--noconsole` para que no abra la ventana negra de CMD).
2.  **Persistencia de Datos:** Asegúrate de que, al compilar, las rutas a `LibreHardwareMonitor.exe` y a los archivos de configuración (o variables de entorno de la DB) se resuelvan dinámicamente usando `sys._MEIPASS` o rutas relativas al ejecutable, para que la app no se rompa al actualizarse en la carpeta de destino.

**Próximos pasos:** Si estás de acuerdo con esta arquitectura, el primer paso sería crear la clase del Bootstrapper en Python que se encargue del proceso de actualización mediante Git. ¿Quieres que empecemos diseñando el código de ese módulo actualizador o prefieres que armemos el esqueleto de la interfaz gráfica primero?