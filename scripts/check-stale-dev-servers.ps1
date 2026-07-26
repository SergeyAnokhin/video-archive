# Warns (does not block or kill anything) if something is already
# listening on the dev ports before `npm run dev` starts fresh ones.
#
# This repo's dev servers (`vite --host 0.0.0.0`, `uvicorn --reload --host
# 0.0.0.0`) are easy to orphan on Windows: closing a terminal, a crashed
# reload cycle, or a previous Claude Code chat's own tooling can all leave
# one running in the background. An orphan keeps answering requests with
# its own (possibly outdated) code while a freshly started server on the
# same port silently fails to bind -- see docs/development.md's "stale
# uvicorn --reload worker" note for the full failure mode.

$portChecks = @(
    [pscustomobject]@{ Port = 5173; Label = "frontend (vite)" }
    [pscustomobject]@{ Port = 8010; Label = "backend (uvicorn)" }
)
$foundStale = $false

foreach ($check in $portChecks) {
    $conns = Get-NetTCPConnection -LocalPort $check.Port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $conns) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($conn.OwningProcess)" -ErrorAction SilentlyContinue
        if ($proc) {
            $foundStale = $true
            Write-Host ""
            Write-Host "WARNING: port $($check.Port) ($($check.Label)) is already in use." -ForegroundColor Yellow
            Write-Host "  PID $($proc.ProcessId), started $($proc.CreationDate)" -ForegroundColor Yellow
            Write-Host "  $($proc.CommandLine)" -ForegroundColor Yellow
        }
    }
}

if ($foundStale) {
    Write-Host ""
    Write-Host "This looks like a leftover dev server from an earlier session (this repo's own terminal, or a previous Claude Code chat) rather than the one about to start." -ForegroundColor Yellow
    Write-Host "It will keep answering requests with its own code instead of the fresh server -- close it first (Task Manager, or 'Stop-Process -Id <pid> -Force') if you want a clean run." -ForegroundColor Yellow
    Write-Host "See docs/development.md's stale-uvicorn-worker note for background." -ForegroundColor Yellow
    Write-Host ""
} else {
    $portList = ($portChecks | ForEach-Object { $_.Port }) -join ', '
    Write-Host "No stale dev server found on ports $portList." -ForegroundColor Green
}

exit 0
