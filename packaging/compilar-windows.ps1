# Compila G3G3AI en tu propio PC con Windows (sin depender de GitHub Actions).
# Uso: doble clic en packaging\compilar-windows.bat  (o: powershell -ExecutionPolicy Bypass -File packaging\compilar-windows.ps1)
# Resultado en la carpeta dist:
#   G3G3AI.exe                     versión ligera
#   G3G3AI-windows-completo.zip    edición completa (llama.cpp, stable-diffusion.cpp, Python y Git incluidos)
param([switch]$SinCompleta)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
function Paso($t) { Write-Host ""; Write-Host "==> $t" -ForegroundColor Cyan }

function Buscar-Python {
    foreach ($c in @(@{exe = "py"; args = @("-3.12")}, @{exe = "py"; args = @("-3")}, @{exe = "python"; args = @()})) {
        $cmd = Get-Command $c.exe -ErrorAction SilentlyContinue
        if (-not $cmd -or $cmd.Source -like "*WindowsApps*") { continue }   # el alias de la Tienda no es un Python real
        try {
            $v = & $c.exe @($c.args + "--version") 2>&1
            if ($LASTEXITCODE -eq 0 -and "$v" -match "Python 3\.(1[0-9])") { return $c }
        } catch { }
    }
    return $null
}

Paso "Buscando Python 3.10 o posterior"
$py = Buscar-Python
if (-not $py) {
    Paso "No hay Python: lo instalo con winget (Python 3.12, solo para tu usuario)"
    winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
    $py = Buscar-Python
    if (-not $py) { throw "No se pudo instalar Python. Instálalo desde https://www.python.org/downloads/ (marca 'Add to PATH') y vuelve a ejecutar." }
}
Write-Host ("Usando: " + $py.exe + " " + ($py.args -join " "))

Paso "Preparando un entorno aislado (.build-venv)"
if (-not (Test-Path ".build-venv\Scripts\python.exe")) { & $py.exe @($py.args + @("-m", "venv", ".build-venv")) }
$vpy = Join-Path $root ".build-venv\Scripts\python.exe"
& $vpy -m pip install --upgrade pip --quiet
& $vpy -m pip install -r requirements.txt pyinstaller pywebview --quiet
if ($LASTEXITCODE -ne 0) { throw "Falló la instalación de dependencias" }

Paso "Compilando G3G3AI.exe (tarda unos minutos)"
& $vpy -m PyInstaller --noconfirm --distpath dist packaging\g3g3ai.spec
if ($LASTEXITCODE -ne 0 -or -not (Test-Path "dist\G3G3AI.exe")) { throw "Falló la compilación" }

if (-not $SinCompleta) {
    Paso "Edición completa: descargando llama.cpp, stable-diffusion.cpp, Python y Git portátiles"
    if (Test-Path "dist\full") { Remove-Item -Recurse -Force "dist\full" }
    & $vpy packaging\fetch_extras.py windows dist\full\G3G3AI-extras
    Copy-Item dist\G3G3AI.exe dist\full\G3G3AI.exe -Force
    if (Test-Path "dist\G3G3AI-windows-completo.zip") { Remove-Item "dist\G3G3AI-windows-completo.zip" -Force }
    Compress-Archive -Path dist\full\* -DestinationPath dist\G3G3AI-windows-completo.zip
}

Paso "Listo"
Write-Host "  dist\G3G3AI.exe" -ForegroundColor Green
if (-not $SinCompleta) { Write-Host "  dist\G3G3AI-windows-completo.zip   (o directamente dist\full\G3G3AI.exe con su carpeta G3G3AI-extras)" -ForegroundColor Green }
Start-Process explorer.exe (Join-Path $root "dist")
