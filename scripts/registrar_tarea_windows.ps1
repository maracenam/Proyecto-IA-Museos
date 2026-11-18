# Registra en el Programador de tareas de Windows la ejecución diaria de procesar_pendientes.ps1.
#   powershell -ExecutionPolicy Bypass -File scripts\registrar_tarea_windows.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\registrar_tarea_windows.ps1 -Hora 21:30
# Corre como tu usuario, solo con la sesión iniciada, y se pone al día si el PC estaba apagado
# a la hora programada. Para quitarla: Unregister-ScheduledTask -TaskName "Observatorio SURDOC"

param([string]$Hora = "20:00")

$script = Join-Path $PSScriptRoot "procesar_pendientes.ps1"
$accion = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory (Split-Path -Parent $PSScriptRoot)
$disparador = New-ScheduledTaskTrigger -Daily -At $Hora
$opciones = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName "Observatorio SURDOC" -Action $accion -Trigger $disparador `
    -Settings $opciones -Description "Normalización y embeddings pendientes del Observatorio SURDOC" `
    -Force | Out-Null

Write-Host "Tarea 'Observatorio SURDOC' registrada: todos los días a las $Hora."
Write-Host "Para probarla ahora: Start-ScheduledTask -TaskName 'Observatorio SURDOC' (registro en logs\)."
