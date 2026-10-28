param(
    [Parameter(Mandatory = $true)] [string]$SetupPath
)

$ErrorActionPreference = "Stop"
$uninstallKey = "Software\Microsoft\Windows\CurrentVersion\Uninstall\{A6D533F4-96F9-4F91-810B-5721FF5A86CA}_is1"
if ((Test-Path "HKCU:\$uninstallKey") -or (Test-Path "HKLM:\$uninstallKey")) {
    throw "An existing Study Agent installation was found; run this smoke test on a clean machine."
}
$existingData = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'StudyAgent'
if (Test-Path -LiteralPath $existingData) {
    throw "Study Agent user data already exists; run this smoke test on a clean machine."
}
$sandbox = Join-Path $env:TEMP ("Study Agent setup smoke " + [guid]::NewGuid())
$installDir = Join-Path $sandbox "installed app"
$log = Join-Path $sandbox "setup.log"
New-Item -ItemType Directory -Path $sandbox -Force | Out-Null
try {
    $process = Start-Process -FilePath (Resolve-Path $SetupPath).Path `
        -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/DIR=`"$installDir`"", "/LOG=`"$log`"") `
        -Wait -PassThru
    if (Test-Path $log) { Get-Content -LiteralPath $log | Write-Host }
    if ($process.ExitCode -ne 0) { throw "Installer exited with code $($process.ExitCode)." }
    foreach ($file in @('StudyAgent.Windows.exe', 'Backend.zip', 'Microsoft.UI.Xaml.dll', 'unins000.exe')) {
        if (-not (Test-Path -LiteralPath (Join-Path $installDir $file))) { throw "Installed file missing: $file" }
    }

    $backendDirectory = Join-Path $sandbox 'backend'
    [System.IO.Compression.ZipFile]::ExtractToDirectory((Join-Path $installDir 'Backend.zip'), $backendDirectory)
    & (Join-Path $PSScriptRoot 'smoke_windows_backend.ps1') -Executable (Join-Path $backendDirectory 'StudyAgentBackend.exe')

    $app = Start-Process -FilePath (Join-Path $installDir 'StudyAgent.Windows.exe') `
        -WorkingDirectory $installDir -PassThru
    Start-Sleep -Seconds 15
    $app.Refresh()
    if ($app.HasExited) { throw "Installed application exited at startup with code $($app.ExitCode)." }
    Stop-Process -Id $app.Id -Force
    $app.WaitForExit()
    New-Item -ItemType Directory -Path $existingData -Force | Out-Null
    $marker = Join-Path $existingData 'uninstall-preservation-smoke.txt'
    Set-Content -LiteralPath $marker -Value 'synthetic user data' -Encoding utf8
    $uninstall = Start-Process -FilePath (Join-Path $installDir 'unins000.exe') `
        -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -Wait -PassThru
    if ($uninstall.ExitCode -ne 0 -or (Test-Path (Join-Path $installDir 'StudyAgent.Windows.exe'))) {
        throw "Uninstall failed with code $($uninstall.ExitCode)."
    }
    if (-not (Test-Path -LiteralPath $marker)) { throw "Uninstall removed user data." }
    Write-Host 'Installed application, synthetic backend, startup and uninstall smoke passed.'
}
finally {
    try { [System.IO.Directory]::Delete($sandbox, $true) }
    catch { Write-Warning "Could not remove temporary smoke-test files: $sandbox" }
}
