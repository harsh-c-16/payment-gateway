[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location -LiteralPath $PSScriptRoot
$demoPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
$demoDirectory = Join-Path $PSScriptRoot 'artifacts/failure-demo'
New-Item -ItemType Directory -Force -Path $demoDirectory | Out-Null
$demoState = $null
try {
    $demoState = Invoke-RestMethod -Uri 'http://127.0.0.1:8010/state' -Headers @{Origin='http://127.0.0.1:8001'} -TimeoutSec 3
} catch { }
if ($demoState -and $demoState.available) {
    $demoContextPath = Join-Path $PSScriptRoot 'artifacts/infra/prototype-local/context.json'
    $demoContext = Get-Content -LiteralPath $demoContextPath -Raw | ConvertFrom-Json
    if ($demoState.namespace -ne $demoContext.RUN_NAMESPACE) {
        throw 'The helper observes an older namespace. Run stop-failure-demo.ps1, then start-failure-demo.ps1 to bind the active presentation.'
    }
    if ($demoState.scenarios.PSObject.Properties.Name -notcontains 'refund' -or
        $demoState.PSObject.Properties.Name -notcontains 'journey_schema') {
        throw 'An older helper is running. Run stop-failure-demo.ps1, then start-failure-demo.ps1 to load the new scenarios.'
    }
    $demoSupport = Join-Path $demoDirectory 'hook-support.json'
    if (!(Test-Path -LiteralPath $demoSupport) -or !(Get-Content -LiteralPath $demoSupport -Raw | ConvertFrom-Json).enabled) {
        & $demoPython -m benchmarks.failure_demo.setup enable
        if ($LASTEXITCODE -ne 0) { throw 'Could not restore scoped hook support.' }
    }
    Write-Host 'Local failure and infrastructure helper already running. Open http://127.0.0.1:8001/dashboard'
    return
}
& $demoPython -m benchmarks.failure_demo.setup enable
if ($LASTEXITCODE -ne 0) { throw 'Could not enable the scoped local hooks. Start the prototype first.' }
$demoProcess = Start-Process -FilePath $demoPython -ArgumentList '-m benchmarks.failure_demo.controller' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $demoDirectory 'controller.log') -RedirectStandardError (Join-Path $demoDirectory 'controller-error.log')
$demoProcess.Id | Set-Content -LiteralPath (Join-Path $demoDirectory 'controller.pid')
$demoDeadline = [DateTime]::UtcNow.AddSeconds(20)
while ([DateTime]::UtcNow -lt $demoDeadline) {
    try {
        $demoState = Invoke-RestMethod -Uri 'http://127.0.0.1:8010/state' -Headers @{Origin='http://127.0.0.1:8001'} -TimeoutSec 2
        if ($demoState.available) { Write-Host 'Failure demos ready: http://127.0.0.1:8001/dashboard#failure-demo'; return }
    } catch { }
    Start-Sleep -Milliseconds 500
}
throw 'Controller did not start. Inspect artifacts/failure-demo/controller-error.log.'
