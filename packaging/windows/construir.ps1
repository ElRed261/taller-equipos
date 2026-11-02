# Construye el instalador de Windows.
#
#   powershell -ExecutionPolicy Bypass -File packaging\windows\construir.ps1
#
# Hace lo mismo que scripts/empaquetar.sh en Linux y después compila el .exe del
# instalador con Inno Setup. Requiere, en la máquina Windows:
#
#   - uv (https://docs.astral.sh/uv/)
#   - Inno Setup 6 (winget install JRSoftware.InnoSetup)
#
# No se puede ejecutar desde Linux: PyInstaller arma el binario que corre en el
# sistema donde se ejecuta, así que este archivo se corre en Windows o en el runner
# windows-latest del flujo de trabajo de GitHub.

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $raiz

Write-Host "Regenerando el icono del ejecutable…"
uv run python scripts\generar_icono.py

Write-Host "Empaquetando con PyInstaller…"
uv run pyinstaller packaging\taller-equipos.spec --noconfirm --clean --distpath dist --workpath build

$ejecutable = Join-Path $raiz "dist\taller-equipos\taller-equipos.exe"
if (-not (Test-Path $ejecutable)) {
    throw "PyInstaller no generó $ejecutable"
}

$version = & $ejecutable --version
Write-Host "Versión del binario: $version"

# El instalador no puede llevar la marca de una organizacion: la marca se configura
# en la aplicacion, en la carpeta del usuario.
$marca = Get-ChildItem -Path (Join-Path $raiz "dist\taller-equipos") -Recurse -File |
    Select-String -Pattern "indomet" -SimpleMatch -List
if ($marca) {
    throw "El paquete contiene la marca institucional: $($marca.Path -join ', ')"
}

$iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    $rutas = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    $encontrado = $rutas | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $encontrado) {
        throw "No encuentro ISCC.exe. Instalá Inno Setup 6: winget install JRSoftware.InnoSetup"
    }
    $iscc = $encontrado
} else {
    $iscc = $iscc.Source
}

Write-Host "Compilando el instalador con $iscc…"
& $iscc "packaging\windows\taller-equipos.iss"

$instalador = Get-ChildItem -Path (Join-Path $raiz "dist") -Filter "*-instalador.exe" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $instalador) {
    throw "Inno Setup no dejó ningún instalador en dist\"
}

Write-Host ""
Write-Host "Listo: $($instalador.FullName)"
Write-Host "Tamaño: $([math]::Round($instalador.Length / 1MB, 1)) MB"
