$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$packageRoot = Join-Path $root "windows\StudyAgent.Windows\AppPackages"
$outputDirectory = Join-Path $root "build\windows-installer"
$script = Join-Path $root "windows\StudyAgentSetup.iss"

if (-not (Test-Path $script)) {
    throw "Inno Setup definition not found: $script"
}

$compilerCandidates = @(
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
)
$compiler = $compilerCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $compiler) {
    throw "Inno Setup 6 compiler not found. Install it before building the Windows installer."
}

$packages = @(Get-ChildItem -LiteralPath $packageRoot -Filter "*_x64.msix" -File -Recurse)
if ($packages.Count -ne 1) {
    throw "Expected exactly one x64 MSIX under $packageRoot; found $($packages.Count)."
}

New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
$env:STUDY_AGENT_MSIX = $packages[0].FullName
$env:STUDY_AGENT_INSTALLER_OUTPUT = $outputDirectory
& $compiler /Qp $script
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with exit code $LASTEXITCODE."
}

$installer = Join-Path $outputDirectory "StudyAgentSetup.exe"
if (-not (Test-Path $installer)) {
    throw "Inno Setup did not create the expected installer: $installer"
}
Write-Host "Windows setup executable created: $installer ($((Get-Item $installer).Length) bytes)"
