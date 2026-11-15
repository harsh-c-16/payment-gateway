[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $projectPython)) { throw 'The prepared Python environment is missing.' }
$dashboardHelper = $null
try {
    $dashboardHelper = Invoke-RestMethod -Uri 'http://127.0.0.1:8010/state' -Headers @{Origin='http://127.0.0.1:8001'} -TimeoutSec 3
} catch { }
if ($dashboardHelper -and $dashboardHelper.available) {
    $activeContext = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'artifacts/infra/prototype-local/context.json') -Raw | ConvertFrom-Json
    if ($dashboardHelper.namespace -ne $activeContext.RUN_NAMESPACE) {
        throw 'The dashboard helper belongs to another namespace. Stop its demo before removing project containers.'
    }
    & (Join-Path $PSScriptRoot 'stop-failure-demo.ps1')
}
# Compose scopes removal to this project's labelled containers/network. Never use -v or prune.
& $projectPython -c "from infra import prototype, postgres; print(prototype.compose('--profile', '*', 'down', '--remove-orphans', '--timeout', '40')); remaining=postgres.command(['docker','ps','--all','--quiet','--filter','label=com.docker.compose.project='+postgres.PROJECT]); raise SystemExit('Project containers remain after cleanup' if remaining else 0)"
if ($LASTEXITCODE -ne 0) { throw "Project container cleanup failed (exit $LASTEXITCODE)." }
Write-Host 'Project containers removed. Database/Kafka/lakehouse volumes, model files and images retained.' -ForegroundColor Green
