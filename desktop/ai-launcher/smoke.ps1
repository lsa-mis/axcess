# Smoke test for axcess-ai-launcher.exe on Windows (run by the Windows job in
# .github/workflows/ai-sandbox.yml). No AI model is used: llama-server runs
# in router mode with an empty preset, which loads nothing and starts no
# child process.
#
#   pwsh -File desktop/ai-launcher/smoke.ps1 -Launcher <exe> -Runtime <dir> -WorkDir <dir>
#
# Checks, in order:
#   a. "check" exits 0 and prints all three OK lines (and again with --gpu).
#   b. "serve" starts llama-server on a UNIX socket; GET /health through the
#      launcher's port answers 200 to this PowerShell process (--client-pid).
#   c. The same port closes a connection from another process (curl.exe).
#   d. Closing the launcher's stdin ends llama-server.exe within 10 seconds.
# Prints the launcher and llama-server log when anything fails.
param(
    [Parameter(Mandatory = $true)][string]$Launcher,
    [Parameter(Mandatory = $true)][string]$Runtime,
    [Parameter(Mandatory = $true)][string]$WorkDir
)

$ErrorActionPreference = "Stop"

$Launcher = [System.IO.Path]::GetFullPath($Launcher)
$Runtime = [System.IO.Path]::GetFullPath($Runtime)
$WorkDir = [System.IO.Path]::GetFullPath($WorkDir)
$scratch = Join-Path $WorkDir "scratch"
$models = Join-Path $WorkDir "models"
$log = Join-Path $WorkDir "launcher.log"
foreach ($dir in $scratch, $models) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
$utf8 = [System.Text.UTF8Encoding]::new($false)

$server = Get-ChildItem -Path (Join-Path $Runtime "cpu") -Recurse -Filter "llama-server.exe" |
    Select-Object -First 1
if (-not $server) { throw "No CPU llama-server.exe under $Runtime\cpu." }
$server = $server.FullName

function Show-Log {
    if (Test-Path $log) {
        Write-Host "----- launcher and llama-server log ($log) -----"
        Get-Content $log -Tail 300 | ForEach-Object { Write-Host $_ }
        Write-Host "----- end of log -----"
    }
}

function Invoke-Check([string[]]$Extra) {
    $out = @(& $Launcher check --scratch $scratch --runtime $Runtime --models $models --log $log @Extra)
    $code = $LASTEXITCODE
    $out | ForEach-Object { Write-Host "check $($Extra -join ' '): $_" }
    if ($code -ne 0) { throw "check $($Extra -join ' ') exited with $code." }
    foreach ($want in "AXCESS_NETWORK_BLOCKED *", "AXCESS_FILES_LIMITED", "AXCESS_SOCKET_OK") {
        if (-not ($out | Where-Object { $_ -like $want })) { throw "check did not print '$want'." }
    }
    if (Test-Path (Join-Path $scratch "probe.sock")) { throw "check left probe.sock behind." }
}

function Start-Launcher([string[]]$Arguments) {
    $psi = [System.Diagnostics.ProcessStartInfo]::new($Launcher)
    foreach ($a in $Arguments) { $psi.ArgumentList.Add($a) }
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.StandardOutputEncoding = $utf8
    return [System.Diagnostics.Process]::Start($psi)
}

$script:pending = $null
function Read-LauncherLine($Process, [int]$Seconds) {
    $task = $script:pending
    if (-not $task) { $task = $Process.StandardOutput.ReadLineAsync() }
    if (-not $task.Wait($Seconds * 1000)) { $script:pending = $task; return $null }
    $script:pending = $null
    return $task.Result
}

function Write-Spec([string]$Path, [string]$Program, [string]$Socket, [string]$Preset) {
    $lines = @(
        "MODEL router",
        "SOCKET $Socket",
        "ARG $Program",
        "ARG --models-preset",
        "ARG $Preset",
        "ARG --host",
        "ARG $Socket",
        "ARG --no-webui",
        "ARG --offline",
        ""
    )
    [System.IO.File]::WriteAllText($Path, ($lines -join "`n"), $utf8)
}

$proc = $null
try {
    Write-Host "== a. check"
    Invoke-Check @()
    Write-Host "== a2. check with GPU capabilities (registryRead, lpacPnpNotifications)"
    Invoke-Check @("--gpu")

    Write-Host "== spec rejects a program outside --runtime"
    $badSpec = Join-Path $WorkDir "bad.spec"
    Write-Spec $badSpec "$env:SystemRoot\System32\cmd.exe" (Join-Path $scratch "bad.sock") (Join-Path $scratch "models.ini")
    $bad = @(& $Launcher serve --scratch $scratch --runtime $Runtime --models $models --log $log --client-pid $PID --spec $badSpec)
    $badCode = $LASTEXITCODE
    $bad | ForEach-Object { Write-Host "serve (bad spec): $_" }
    if ($badCode -eq 0 -or -not ($bad | Where-Object { $_ -like "AXCESS_ERROR spec_program *" })) {
        throw "serve accepted a program outside --runtime."
    }

    Write-Host "== b. serve llama-server (router mode, empty preset) on a UNIX socket"
    $preset = Join-Path $scratch "models.ini"
    [System.IO.File]::WriteAllText($preset, "version = 1`n", $utf8)
    $sock = Join-Path $scratch "llama.sock"
    $spec = Join-Path $WorkDir "serve.spec"
    Write-Spec $spec $server $sock $preset
    $proc = Start-Launcher @("serve", "--scratch", $scratch, "--runtime", $Runtime, "--models", $models,
        "--log", $log, "--client-pid", "$PID", "--spec", $spec)
    $port = $null
    while ($true) {
        $line = Read-LauncherLine $proc 30
        if ($null -eq $line) { throw "The launcher printed no READY line." }
        Write-Host "serve: $line"
        if ($line -match '^PORT router (\d+)$') { $port = [int]$Matches[1] }
        if ($line -eq "READY") { break }
        if ($line -like "AXCESS_ERROR*" -or $line -like "EXIT*") { throw "serve failed: $line" }
    }
    if (-not $port) { throw "The launcher printed no PORT line." }
    $url = "http://127.0.0.1:$port/health"

    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.UseProxy = $false
    $client = [System.Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(10)
    $deadline = (Get-Date).AddSeconds(120)
    $status = $null
    while ((Get-Date) -lt $deadline) {
        try {
            $response = $client.GetAsync($url).GetAwaiter().GetResult()
            $status = [int]$response.StatusCode
            $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            if ($status -eq 200) { break }
        } catch {
            $status = $null
        }
        Start-Sleep -Milliseconds 500
    }
    if ($status -ne 200) { throw "GET /health through the launcher did not answer 200 (last: $status)." }
    Write-Host "GET /health -> 200 $body"

    for ($i = 0; $i -lt 10; $i++) {
        $fresh = [System.Net.Http.HttpClient]::new([System.Net.Http.HttpClientHandler]@{ UseProxy = $false })
        $r = $fresh.GetAsync($url).GetAwaiter().GetResult()
        if ([int]$r.StatusCode -ne 200) { throw "Sequential request $i answered $([int]$r.StatusCode)." }
        $fresh.Dispose()
    }
    $tasks = @(1..4 | ForEach-Object {
        [System.Net.Http.HttpClient]::new([System.Net.Http.HttpClientHandler]@{ UseProxy = $false }).GetAsync($url)
    })
    [System.Threading.Tasks.Task]::WaitAll([System.Threading.Tasks.Task[]]$tasks)
    foreach ($t in $tasks) {
        if ([int]$t.Result.StatusCode -ne 200) { throw "A concurrent request answered $([int]$t.Result.StatusCode)." }
    }
    Write-Host "10 sequential and 4 concurrent requests -> 200"

    Write-Host "== c. another process (curl.exe) is refused"
    $curlOut = & curl.exe --silent --show-error --noproxy "*" --max-time 10 --output NUL --write-out "%{http_code}" $url 2>&1
    $curlCode = $LASTEXITCODE
    Write-Host "curl.exe exit $curlCode, output: $curlOut"
    if ($curlCode -eq 0) { throw "curl.exe, a different process, reached the service." }
    $again = $client.GetAsync($url).GetAwaiter().GetResult()
    if ([int]$again.StatusCode -ne 200) { throw "The service stopped answering after the refused connection." }

    Write-Host "== d. closing stdin stops llama-server"
    $proc.StandardInput.Close()
    $stopped = (Get-Date).AddSeconds(10)
    while ((Get-Date) -lt $stopped -and (Get-Process -Name "llama-server" -ErrorAction SilentlyContinue)) {
        Start-Sleep -Milliseconds 200
    }
    if (Get-Process -Name "llama-server" -ErrorAction SilentlyContinue) {
        throw "llama-server.exe was still running 10 s after the launcher's stdin closed."
    }
    if (-not $proc.WaitForExit(10000)) { throw "The launcher did not exit after its stdin closed." }
    while ($true) {
        $line = Read-LauncherLine $proc 2
        if ($null -eq $line) { break }
        Write-Host "serve: $line"
    }
    if ($proc.ExitCode -ne 0) { throw "The launcher exited with $($proc.ExitCode)." }
    if (Test-Path $log) {
        $unix = Select-String -Path $log -Pattern "unix://" | Select-Object -First 1
        Write-Host "llama-server log line with unix://: $(if ($unix) { $unix.Line } else { '(none)' })"
    }
    Write-Host "All launcher smoke checks passed."
    Show-Log
} catch {
    Write-Host "FAILED: $_"
    Show-Log
    if ($proc -and -not $proc.HasExited) { $proc.Kill() }
    exit 1
}
