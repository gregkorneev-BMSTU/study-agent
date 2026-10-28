$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$publishDirectory = Join-Path $root "build\windows-publish"
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

foreach ($required in @("StudyAgent.Windows.exe", "Backend.zip", "Microsoft.UI.Xaml.dll")) {
    if (-not (Test-Path (Join-Path $publishDirectory $required))) {
        throw "Required published application file is missing: $publishDirectory\$required. Publish the self-contained app first."
    }
}

New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
$env:STUDY_AGENT_PUBLISH_DIR = $publishDirectory
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
