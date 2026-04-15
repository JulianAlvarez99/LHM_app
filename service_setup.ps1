$TaskName = "LHM Telemetry Agent"
$Description = "Agente de telemetría LHM (System Tray) con permisos elevados."

$WorkingDir = $PSScriptRoot
if (-not $WorkingDir) { $WorkingDir = Get-Location }

$RunExe = Join-Path $WorkingDir "Updater.exe"

# 1. Eliminar tarea existente si ya estaba creada
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Host "[WAIT] Eliminando tarea programada anterior..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# 2. Configurar el comando para correr el ejecutable (la GUI se auto-oculta en bandeja)
$Action = New-ScheduledTaskAction -Execute $RunExe -WorkingDirectory $WorkingDir

# 3. Disparador: Al iniciar sesión
$Trigger = New-ScheduledTaskTrigger -AtStartup

# 4. Configuración principal: Ejecutar con Privilege Más Alto y de forma Interactiva
# "S-1-5-32-544" es el identificador (SID) universal de Administradores en cualquier idioma
$Principal = New-ScheduledTaskPrincipal -GroupId "S-1-5-32-544" -RunLevel Highest

# 5. Ajustes adicionales
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Days 0) # Infinito

# 6. Registro de la tarea
Register-ScheduledTask -TaskName $TaskName `
                       -Description $Description `
                       -Action $Action `
                       -Trigger $Trigger `
                       -Principal $Principal `
                       -Settings $Settings

Write-Host "[OK] Tarea Programada interactiva '$TaskName' creada correctamente."
Write-Host "La app lanzara Updater.exe -> LHM_Capture.exe de forma automatica en cada inicio."

