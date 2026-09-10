# Disposable local app only. Required inputs are process environment variables.
$ErrorActionPreference = 'Stop'
foreach ($qaRequired in @('QA_PYTHON', 'QA_NODE', 'QA_HARNESS_ROOT', 'QA_BASE_URL', 'QA_RUN_ID', 'LANTERN_DATABASE_URL', 'QA_SERVICE_LOG_DIR')) {
    if (-not [Environment]::GetEnvironmentVariable($qaRequired)) { throw "Missing $qaRequired" }
}
$qaTarget = [Uri]$env:QA_BASE_URL
if ($qaTarget.Host -notin @('localhost', '127.0.0.1')) { throw 'Loopback app required' }
$qaRepo = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$qaBefore = Join-Path $PSScriptRoot 'live-browser-before.json'
$qaAfter = Join-Path $PSScriptRoot 'live-browser-after.json'
& $env:QA_PYTHON (Join-Path $PSScriptRoot 'live-browser-state.py') $qaBefore
if ($LASTEXITCODE -ne 0) { throw 'Before-state verification failed' }
$env:QA_USER = 'local-qa'
$env:QA_PASS = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')
$env:LANTERN_WEB_USERS = $env:QA_USER + ':' + $env:QA_PASS
$env:LANTERN_WEB_SECRET = [Guid]::NewGuid().ToString('N')
$qaService = $null
try {
    $qaService = Start-Process -FilePath $env:QA_PYTHON -ArgumentList @('-m', 'uvicorn', 'app:app', '--host', '127.0.0.1', '--port', $qaTarget.Port) -WorkingDirectory (Join-Path $env:QA_HARNESS_ROOT 'tools/mission-control') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $env:QA_SERVICE_LOG_DIR 'qa-web.stdout.log') -RedirectStandardError (Join-Path $env:QA_SERVICE_LOG_DIR 'qa-web.stderr.log')
    $qaReady = $false
    for ($qaTry = 0; $qaTry -lt 25; $qaTry++) {
        if ($qaService.HasExited) { throw 'Local application exited before readiness' }
        try {
            $qaResponse = Invoke-WebRequest -Uri ($env:QA_BASE_URL + '/login') -TimeoutSec 2
            if ($qaResponse.StatusCode -eq 200) { $qaReady = $true; break }
        } catch { Start-Sleep -Milliseconds 300 }
    }
    if (-not $qaReady) { throw 'Local application did not become ready' }
    & $env:QA_NODE (Join-Path $qaRepo 'tools/qa-recorder/agent-infrastructure-live.mjs')
    $qaBrowserExit = $LASTEXITCODE
    & $env:QA_PYTHON (Join-Path $PSScriptRoot 'live-browser-state.py') $qaAfter $qaBefore
    if ($LASTEXITCODE -ne 0) { throw 'After-state verification failed' }
    if ($qaBrowserExit -ne 0) { throw 'Browser checks failed; see preserved results' }
} finally {
    if ($qaService -and -not $qaService.HasExited) { Stop-Process -Id $qaService.Id }
    foreach ($qaTemporary in @('QA_USER', 'QA_PASS', 'LANTERN_WEB_USERS', 'LANTERN_WEB_SECRET')) {
        [Environment]::SetEnvironmentVariable($qaTemporary, $null, 'Process')
    }
}
