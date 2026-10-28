$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$build = Join-Path $root "build\windows-backend"
$entry = Join-Path $root "src\study_agent\mac_bridge.py"
$archive = Join-Path $build "StudyAgentBackend.zip"

if (-not (Test-Path $python)) {
    throw "Python .venv не найден."
}

& $python -m PyInstaller --version

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller не установлен."
}

& $python -m pip show chandra-ocr torch pypdfium2 python-docx | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Не установлены backend-зависимости. Выполните: .\.venv\Scripts\python.exe -m pip install '.[dev,ocr,packaging]'"
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
        --collect-all chandra `
        --collect-all torch `
        --collect-all torchvision `
        --collect-all transformers `
        --collect-all huggingface_hub `
        --collect-all PIL `
        --collect-all pypdfium2 `
        --runtime-hook (Join-Path $root "scripts\windows_utf8_hook.py") `
        $entry

    if ($LASTEXITCODE -ne 0) {
        throw "Сборка backend завершилась с ошибкой."
    }

    $exe = Join-Path $build "dist\StudyAgentBackend\StudyAgentBackend.exe"

    if (-not (Test-Path $exe)) {
        throw "StudyAgentBackend.exe не найден."
    }

    if (Test-Path $archive) { Remove-Item $archive -Force }
    $packageScript = Join-Path $PSScriptRoot "package_windows_backend.py"
    & $python $packageScript (Join-Path $build "dist\StudyAgentBackend") $archive
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $archive)) {
        throw "Не удалось создать StudyAgentBackend.zip для Release MSIX."
    }

    Write-Host ""
    Write-Host "Backend успешно собран:"
    Write-Host $exe
    Write-Host "Release archive: $archive"
}
finally {
    Pop-Location
}

