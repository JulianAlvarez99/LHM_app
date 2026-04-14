[Setup]
AppName=LHM Telemetry Agent
AppVersion=1.0.0
DefaultDirName={pf}\LHM Telemetry Agent
DefaultGroupName=LHM Telemetry Agent
UninstallDisplayIcon={app}\Lanzador.exe
Compression=lzma2
SolidCompression=yes
OutputDir=dist
OutputBaseFilename=LHM_Setup
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64

[Files]
; Ejecutables principales
Source: "dist\Lanzador.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\App_Interna.exe"; DestDir: "{app}"; Flags: ignoreversion
; Directorio de entorno y scripts
Source: "*"; DestDir: "{app}"; Excludes: "venv\*,__pycache__\*,dist\*,*.pyc,.git\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "install.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\LHM Telemetry Agent"; Filename: "{app}\Lanzador.exe"
Name: "{group}\Desinstalar LHM Telemetry Agent"; Filename: "{uninstallexe}"
Name: "{commonstartup}\LHM Telemetry Agent"; Filename: "{app}\Lanzador.exe"

[Run]
; Inicializar repositorio local y sincronizar 
Filename: "git"; Parameters: "init"; WorkingDir: "{app}"; Flags: runhidden; StatusMsg: "Iniciando repositorio local..."
Filename: "git"; Parameters: "remote add origin https://github.com/TU_USUARIO/LHM_app.git"; WorkingDir: "{app}"; Flags: runhidden; StatusMsg: "Configuracion de origen..."
Filename: "git"; Parameters: "fetch origin"; WorkingDir: "{app}"; Flags: runhidden; StatusMsg: "Descargando actualizaciones..."
Filename: "git"; Parameters: "branch --set-upstream-to=origin/main main"; WorkingDir: "{app}"; Flags: runhidden; StatusMsg: "Integrando repositorio..."
Filename: "git"; Parameters: "reset --hard origin/main"; WorkingDir: "{app}"; Flags: runhidden; StatusMsg: "Sincronizando versiones..."
; Ejecutar install.bat como administrador
Filename: "{app}\install.bat"; Parameters: ""; WorkingDir: "{app}"; Flags: runascurrentuser waituntilterminated; StatusMsg: "Instalando entorno y configurando base de datos..."
; Lanzar la aplicación al finalizar
Filename: "{app}\Lanzador.exe"; Description: "Lanzar LHM Telemetry Agent"; Flags: nowait postinstall runascurrentuser
