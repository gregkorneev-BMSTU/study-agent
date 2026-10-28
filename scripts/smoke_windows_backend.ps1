param(
    [string]$Executable = (Join-Path (Split-Path -Parent $PSScriptRoot) "build\windows-backend\dist\StudyAgentBackend\StudyAgentBackend.exe")
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $Executable)) { throw "Packaged backend executable not found: $Executable" }

function Invoke-Backend([object[]]$Requests, [string]$DataDirectory) {
    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = (Resolve-Path $Executable).Path
    $start.WorkingDirectory = Split-Path -Parent (Resolve-Path $Executable).Path
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.StandardInputEncoding = [System.Text.UTF8Encoding]::new($false)
    $start.StandardOutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $start.Environment["STUDY_AGENT_DATA_DIR"] = $DataDirectory
    $start.Environment["PYTHONIOENCODING"] = "utf-8"
    $start.Environment["PYTHONUTF8"] = "1"
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $start
    $process.Start() | Out-Null
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    foreach ($request in $Requests) {
        $process.StandardInput.WriteLine(($request | ConvertTo-Json -Compress -Depth 10))
    }
    $process.StandardInput.Close()
    if (-not $process.WaitForExit(120000)) {
        $process.Kill($true)
        throw "Packaged backend smoke timed out."
    }
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    if ($process.ExitCode -ne 0) { throw "Backend exited $($process.ExitCode): $stderr" }
    $messages = @($stdout -split "`r?`n" | Where-Object { $_ } | ForEach-Object { $_ | ConvertFrom-Json })
    $final = @{}
    foreach ($message in $messages) {
        if ($message.event -ne "progress" -and $message.request_id) { $final[$message.request_id] = $message }
    }
    return @{ Messages = $messages; Final = $final }
}

$sandbox = Join-Path ([System.IO.Path]::GetTempPath()) ("Study Agent тест " + [guid]::NewGuid())
$root = Join-Path $sandbox "Учебные материалы"
$moved = Join-Path $sandbox "offline"
$data = Join-Path $sandbox "data"
New-Item -ItemType Directory -Path $root -Force | Out-Null
New-Item -ItemType Directory -Path $data -Force | Out-Null
Set-Content -LiteralPath (Join-Path $root "лекция.txt") -Encoding utf8 "Синтетический материал про кинематику и равномерное движение."
Set-Content -LiteralPath (Join-Path $root "notes.md") -Encoding utf8 "# Тестовая заметка`n`nСкорость равна пути, делённому на время."
try {
    $first = Invoke-Backend @(
        @{request_id="diag"; command="diagnose_backend"},
        @{request_id="sync"; command="sync_source"; root=$root},
        @{request_id="status"; command="index_status"; root=$root},
        @{request_id="search"; command="search"; roots=@($root); query="кинематику"; search_mode="lexical"}
    ) $data
    foreach ($id in @("diag", "sync", "status", "search")) {
        if (-not $first.Final.ContainsKey($id) -or -not $first.Final[$id].ok) {
            throw "Smoke command '$id' failed: $($first.Final[$id] | ConvertTo-Json -Compress -Depth 8)"
        }
    }
    if (-not $first.Final.diag.result.backend_healthy) { throw "Backend diagnostics reported unhealthy." }
    if ($first.Final.search.result.hits.Count -lt 1) { throw "Synthetic lexical search returned no hits." }
    $progressCount = @($first.Messages | Where-Object { $_.event -eq "progress" -and $_.request_id -eq "sync" }).Count

    Move-Item -LiteralPath $root -Destination $moved
    $offline = Invoke-Backend @(
        @{request_id="offline"; command="search"; roots=@($root); query="кинематику"; search_mode="lexical"},
        @{request_id="remove"; command="remove_index_source"; root=$root},
        @{request_id="after-remove"; command="search"; roots=@($root); query="кинематику"; search_mode="lexical"}
    ) $data
    foreach ($id in @("offline", "remove", "after-remove")) {
        if (-not $offline.Final.ContainsKey($id) -or -not $offline.Final[$id].ok) {
            throw "Smoke command '$id' failed: $($offline.Final[$id] | ConvertTo-Json -Compress -Depth 8)"
        }
    }
    if ($offline.Final.offline.result.hits.Count -lt 1) { throw "Offline source stopped participating in saved-index search." }
    if ($offline.Final["after-remove"].result.hits.Count -ne 0) { throw "Removing a source left searchable index records." }
    Write-Host "Packaged backend smoke passed: diagnostics, progress ($progressCount events), Cyrillic indexing/search, offline search, status, and removal."
}
finally {
    Remove-Item $sandbox -Recurse -Force -ErrorAction SilentlyContinue
}
