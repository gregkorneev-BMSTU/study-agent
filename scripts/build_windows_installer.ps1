$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$publishDirectory = Join-Path $root "build\windows-publish"
$outputDirectory = Join-Path $root "build\windows-installer"
$prerequisiteDirectory = Join-Path $root "build\windows-prerequisites"
$webViewBootstrapper = Join-Path $prerequisiteDirectory "MicrosoftEdgeWebview2Setup.exe"
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

New-Item -ItemType Directory -Path $prerequisiteDirectory -Force | Out-Null
if (-not (Test-Path $webViewBootstrapper)) {
    Invoke-WebRequest -Uri "https://go.microsoft.com/fwlink/p/?LinkId=2124703" -OutFile $webViewBootstrapper
}
$signature = Get-AuthenticodeSignature -LiteralPath $webViewBootstrapper
if ($signature.Status -ne "Valid" -or $signature.SignerCertificate.Subject -notlike "*CN=Microsoft Corporation*") {
    throw "WebView2 bootstrapper is not signed by Microsoft or its signature is invalid: $webViewBootstrapper"
}

New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
$env:STUDY_AGENT_PUBLISH_DIR = $publishDirectory
$env:STUDY_AGENT_WEBVIEW_BOOTSTRAPPER = $webViewBootstrapper
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
