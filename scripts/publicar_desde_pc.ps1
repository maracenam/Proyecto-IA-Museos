# Publica la app desde este PC con un enlace público temporal (túnel gratuito de Cloudflare).
#
#   powershell -ExecutionPolicy Bypass -File scripts\publicar_desde_pc.ps1
#
# Qué hace:
#   1. Lee de .env SOLO la dirección de Supabase y la clave pública (anon): la app solo puede leer.
#      La cadena de conexión de la base (DATABASE_URL) nunca llega a la app publicada.
#   2. Inicia la app en este PC (http://localhost:8501).
#   3. Abre un túnel de Cloudflare y muestra el enlace https://….trycloudflare.com para compartir.
#      No hace falta cuenta, abrir puertos del router ni tocar el firewall.
# Para dejar de publicar: Ctrl+C en esta ventana (o cerrarla). El enlace cambia cada vez.

param([int]$Puerto = 8501)

# "Continue": los programas externos escriben en stderr y no debe tratarse como error.
$ErrorActionPreference = "Continue"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location -Path $raiz
New-Item -ItemType Directory -Force -Path "logs" | Out-Null

function Fallar($mensaje) {
    Write-Host ""
    Write-Host "No se pudo publicar: $mensaje" -ForegroundColor Red
    exit 1
}

# 1. Requisitos
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Fallar "falta uv. Instálalo con: winget install astral-sh.uv (y abre una ventana nueva de PowerShell)."
}
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Fallar "falta cloudflared. Instálalo con: winget install --id Cloudflare.cloudflared (y abre una ventana nueva de PowerShell)."
}
if (-not (Test-Path ".env")) {
    Fallar "no existe el archivo .env. Cópialo de .env.example y completa SUPABASE_URL y SUPABASE_ANON_KEY."
}

# 2. Solo valores públicos desde .env
$config = @{}
foreach ($linea in Get-Content ".env") {
    if ($linea -match '^\s*(SUPABASE_URL|SUPABASE_ANON_KEY|EMBEDDING_MODELO)\s*=\s*(.*?)\s*$') {
        $config[$Matches[1]] = $Matches[2].Trim('"').Trim("'")
    }
}
if (-not $config["SUPABASE_URL"] -or -not $config["SUPABASE_ANON_KEY"]) {
    Fallar "completa SUPABASE_URL y SUPABASE_ANON_KEY en .env (Supabase → Connect → pestaña Framework)."
}
if ($config["SUPABASE_ANON_KEY"] -match "service_role|sb_secret_") {
    Fallar "SUPABASE_ANON_KEY parece una clave secreta. Usa la clave pública (publishable / anon), nunca la service_role."
}
$env:SUPABASE_URL = $config["SUPABASE_URL"]
$env:SUPABASE_ANON_KEY = $config["SUPABASE_ANON_KEY"]
if ($config["EMBEDDING_MODELO"]) { $env:EMBEDDING_MODELO = $config["EMBEDDING_MODELO"] }
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue  # la app publicada nunca usa la cadena de la base

$app = $null
$tunel = $null
try {
    # 3. La app
    Write-Host "Iniciando la app en este PC…" -ForegroundColor Cyan
    $app = Start-Process -FilePath "uv" -PassThru -WindowStyle Hidden `
        -ArgumentList "run --group embed streamlit run app/app.py --server.headless true --server.port $Puerto" `
        -RedirectStandardOutput "logs\app.log" -RedirectStandardError "logs\app_errores.log"
    $lista = $false
    for ($i = 0; $i -lt 90; $i++) {
        Start-Sleep -Seconds 1
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:$Puerto/_stcore/health" -UseBasicParsing -TimeoutSec 2
            if ($r.Content -match "ok") { $lista = $true; break }
        } catch { }
        if ($app.HasExited) { break }
    }
    if (-not $lista) { Fallar "la app no arrancó. Revisa logs\app_errores.log." }

    # 4. El túnel
    Write-Host "Abriendo el enlace público…" -ForegroundColor Cyan
    Remove-Item "logs\tunel.log" -ErrorAction SilentlyContinue
    $tunel = Start-Process -FilePath "cloudflared" -PassThru -WindowStyle Hidden `
        -ArgumentList "tunnel --no-autoupdate --url http://localhost:$Puerto" `
        -RedirectStandardError "logs\tunel.log" -RedirectStandardOutput "logs\tunel_salida.log"
    $enlace = $null
    for ($i = 0; $i -lt 60 -and -not $enlace; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Path "logs\tunel.log") {
            $m = Select-String -Path "logs\tunel.log" -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1
            if ($m) { $enlace = $m.Matches[0].Value }
        }
        if ($tunel.HasExited) { break }
    }
    if (-not $enlace) { Fallar "no se pudo abrir el túnel. Revisa logs\tunel.log (¿hay conexión a internet?)." }

    Set-Clipboard -Value $enlace
    Write-Host ""
    Write-Host "  La app está publicada en:" -ForegroundColor Green
    Write-Host "  $enlace" -ForegroundColor Green
    Write-Host ""
    Write-Host "  El enlace ya está copiado: pégalo donde quieras compartirlo."
    Write-Host "  Funciona mientras esta ventana siga abierta y el PC encendido."
    Write-Host "  Para dejar de publicar: Ctrl+C o cerrar esta ventana."
    Write-Host ""
    Start-Process $enlace

    while (-not $app.HasExited -and -not $tunel.HasExited) { Start-Sleep -Seconds 2 }
    if ($app.HasExited) { Write-Host "La app se detuvo. Revisa logs\app_errores.log." -ForegroundColor Yellow }
    if ($tunel.HasExited) { Write-Host "El túnel se cerró. Vuelve a ejecutar el script para obtener un enlace nuevo." -ForegroundColor Yellow }
}
finally {
    # Ctrl+C también pasa por aquí: se cierran la app y el túnel con todos sus procesos.
    foreach ($p in @($tunel, $app)) {
        if ($p -and -not $p.HasExited) { taskkill /PID $p.Id /T /F | Out-Null }
    }
    Write-Host "Publicación detenida." -ForegroundColor Cyan
}
