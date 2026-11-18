# Procesa lo pendiente en el PC: normalización (reglas + gemma2:2b en Ollama) y embeddings.
# Lo ejecuta el Programador de tareas de Windows (ver registrar_tarea_windows.ps1) o a mano:
#   powershell -ExecutionPolicy Bypass -File scripts\procesar_pendientes.ps1
# Solo trabaja sobre lo pendiente: si no hay fichas nuevas o cambiadas, termina en segundos.
# Si Ollama no está abierto, la normalización se detiene sin perder lo avanzado y se reintenta
# en la próxima ejecución.

# "Continue": en Windows PowerShell 5.1, con "Stop", redirigir stderr de un programa externo
# lo convierte en error al primer mensaje de registro de Python. Los códigos de salida se
# revisan a mano en Paso().
$ErrorActionPreference = "Continue"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location -Path $raiz

New-Item -ItemType Directory -Force -Path "logs" | Out-Null
$registro = Join-Path "logs" ("procesar_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmm"))

function Paso($nombre, [scriptblock]$comando) {
    "== $nombre ($(Get-Date -Format s))" | Out-File -FilePath $registro -Append -Encoding utf8
    & $comando *>&1 | Out-File -FilePath $registro -Append -Encoding utf8
    if ($LASTEXITCODE -ne 0) {
        "== $nombre falló con código $LASTEXITCODE" | Out-File -FilePath $registro -Append -Encoding utf8
        exit $LASTEXITCODE
    }
}

Paso "Normalización" { uv run python -m pipeline.normalize correr }
Paso "Embeddings" { uv run --group embed python -m pipeline.embed generar }

# Conserva solo los últimos 30 registros.
Get-ChildItem "logs\procesar_*.log" | Sort-Object Name -Descending | Select-Object -Skip 30 |
    Remove-Item -ErrorAction SilentlyContinue

"== Listo ($(Get-Date -Format s))" | Out-File -FilePath $registro -Append -Encoding utf8
