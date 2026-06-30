$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Binaries = Join-Path $Root "src-tauri\binaries"
$TargetTriple = "x86_64-pc-windows-msvc"
$SidecarName = "backend-sidecar"
$SidecarExe = Join-Path $Binaries "$SidecarName-$TargetTriple.exe"

if (-not (Test-Path $Python)) {
    py -m venv $Venv
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $Root "requirements.txt") pyinstaller

New-Item -ItemType Directory -Force $Binaries | Out-Null

Get-CimInstance Win32_Process |
    Where-Object { $_.ExecutablePath -eq $SidecarExe } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Push-Location $Root
try {
    & $Python -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --noconsole `
        --name $SidecarName `
        --collect-all dashscope `
        --collect-all fastapi `
        --collect-all starlette `
        --collect-all uvicorn `
        --hidden-import multipart `
        backend_api.py

    $BuiltExe = Join-Path $Root "dist\$SidecarName.exe"
    for ($Attempt = 1; $Attempt -le 10; $Attempt++) {
        try {
            Copy-Item -LiteralPath $BuiltExe -Destination $SidecarExe -Force
            break
        }
        catch {
            if ($Attempt -eq 10) {
                throw
            }
            Start-Sleep -Milliseconds 700
        }
    }
    Write-Host "Sidecar built: $SidecarExe"
}
finally {
    Pop-Location
}
