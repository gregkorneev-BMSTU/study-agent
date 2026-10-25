$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$build = Join-Path $root "build\windows-backend"
$entry = Join-Path $root "src\study_agent\mac_bridge.py"

if (-not (Test-Path $python)) {
    throw "Python .venv не найден."
}

& $python -m PyInstaller --version

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller не установлен."
}

Push-Location $root

try {
    & $python -m PyInstaller `
        --noconfirm `
        --clean `
        --onedir `
        --console `
        --name StudyAgentBackend `
        --paths (Join-Path $root "src") `
        --distpath (Join-Path $build "dist") `
        --workpath (Join-Path $build "work") `
        --specpath $build `
        --exclude-module PySide6 `
        --runtime-hook (Join-Path $root "scripts\windows_utf8_hook.py") `
        $entry

    if ($LASTEXITCODE -ne 0) {
        throw "Сборка backend завершилась с ошибкой."
    }

    $exe = Join-Path $build "dist\StudyAgentBackend\StudyAgentBackend.exe"

    if (-not (Test-Path $exe)) {
        throw "StudyAgentBackend.exe не найден."
    }

    Write-Host ""
    Write-Host "Backend успешно собран:"
    Write-Host $exe
}
finally {
    Pop-Location
}

