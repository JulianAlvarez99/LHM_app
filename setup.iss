[Setup]
AppName=LHM Telemetry Agent
AppVersion=1.0.0
DefaultDirName={pf}\LHM Telemetry Agent
DefaultGroupName=LHM Telemetry Agent
UninstallDisplayIcon={app}\Updater.exe
Compression=lzma2
SolidCompression=yes
OutputDir=dist
OutputBaseFilename=LHM_Setup
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64

[Files]
; Ejecutables principales
Source: "dist\Updater.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\LHM_Capture.exe"; DestDir: "{app}"; Flags: ignoreversion
; Directorio de entorno y scripts
Source: "*"; DestDir: "{app}"; Excludes: "venv\*,__pycache__\*,dist\*,*.pyc,.git\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "overide_client_name.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "install.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\LHM Telemetry Agent"; Filename: "{app}\Updater.exe"
Name: "{group}\Desinstalar LHM Telemetry Agent"; Filename: "{uninstallexe}"
[Code]
var
  ClientPage: TInputQueryWizardPage;
  UserClientName: String;

procedure InitializeWizard;
begin
  ClientPage := CreateInputQueryPage(wpSelectDir,
    'Configuracion del Cliente',
    'Nombre del cliente',
    'Por favor ingrese el identificador del cliente. El prefijo "recursos_" se agregara de forma automatica.');
  
  // Agregamos el campo
  ClientPage.Add('Nombre del Cliente (ej. julian, maquina_2):', False);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ClientPage.ID then
  begin
    if Trim(ClientPage.Values[0]) = '' then
    begin
      MsgBox('Debe ingresar un nombre de cliente valido para continuar.', mbError, MB_OK);
      Result := False;
    end
    else
    begin
      UserClientName := Trim(ClientPage.Values[0]);
    end;
  end;
end;

function GetClientName(Param: String): String;
begin
  Result := UserClientName;
end;

[Run]
; Inicializar repositorio local y sincronizar 
Filename: "git"; Parameters: "init"; WorkingDir: "{app}"; Flags: runhidden; StatusMsg: "Iniciando repositorio local..."
Filename: "git"; Parameters: "remote add origin https://github.com/Camet-Robotica/LHM_app.git"; WorkingDir: "{app}"; Flags: runhidden; StatusMsg: "Configuracion de origen..."
Filename: "git"; Parameters: "fetch origin"; WorkingDir: "{app}"; Flags: runhidden; StatusMsg: "Descargando actualizaciones..."
Filename: "git"; Parameters: "branch --set-upstream-to=origin/main main"; WorkingDir: "{app}"; Flags: runhidden; StatusMsg: "Integrando repositorio..."
Filename: "git"; Parameters: "reset --hard origin/main"; WorkingDir: "{app}"; Flags: runhidden; StatusMsg: "Sincronizando versiones..."
; Ejecutar script de PowerShell para sobreescribir el .env de forma segura
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\overide_client_name.ps1"" -EnvPath ""{app}\.env"" -ClientName ""{code:GetClientName}"""; WorkingDir: "{app}"; Flags: runhidden runascurrentuser waituntilterminated; StatusMsg: "Configurando nombre de cliente en destino..."
; --- INTEGRACIÓN DEL INSTALL.BAT DENTRO DEL INSTALADOR (MODO SILENCIOSO Y VISUAL) ---
Filename: "python"; Parameters: "-m venv venv"; WorkingDir: "{app}"; Flags: runhidden waituntilterminated; StatusMsg: "Creando entorno virtual (1/5)..."
Filename: "{app}\venv\Scripts\python.exe"; Parameters: "-m pip install --upgrade pip"; WorkingDir: "{app}"; Flags: runhidden waituntilterminated; StatusMsg: "Actualizando administrador de paquetes (2/5)..."
Filename: "{app}\venv\Scripts\pip.exe"; Parameters: "install -r requirements.txt"; WorkingDir: "{app}"; Flags: runhidden waituntilterminated; StatusMsg: "Instalando dependencias necesarias (3/5)..."
Filename: "{app}\venv\Scripts\python.exe"; Parameters: "init_master_tables.py"; WorkingDir: "{app}"; Flags: runhidden waituntilterminated; StatusMsg: "Inicializando tablas maestras de la base de datos (4/5)..."
Filename: "{app}\venv\Scripts\python.exe"; Parameters: "db_setup.py"; WorkingDir: "{app}"; Flags: runhidden waituntilterminated; StatusMsg: "Configurando hipertablas y politicas del cliente (5/5)..."
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -NoProfile -File ""{app}\service_setup.ps1"""; WorkingDir: "{app}"; Flags: runhidden runascurrentuser waituntilterminated; StatusMsg: "Registrando el servicio de auto-arranque..."

; Lanzar la aplicación al finalizar
Filename: "{app}\Updater.exe"; Description: "Lanzar LHM Telemetry Agent"; Flags: nowait postinstall runascurrentuser


