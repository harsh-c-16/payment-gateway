[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location -LiteralPath $PSScriptRoot
$demoHeaders = @{Origin='http://127.0.0.1:8001'}
$demoRecovery = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8010/shutdown' -Headers $demoHeaders -TimeoutSec 60
if (!$demoRecovery.recovered) { throw 'Recovery is incomplete. Restore services and use dashboard Recover before stopping the controller.' }
$demoPidFile = Join-Path $PSScriptRoot 'artifacts/failure-demo/controller.pid'
if (Test-Path -LiteralPath $demoPidFile) {
    $demoProcessId = [int](Get-Content -LiteralPath $demoPidFile)
    $demoProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $demoProcessId"
    if ($demoProcess -and $demoProcess.CommandLine -match '\-m\s+benchmarks\.failure_demo\.controller(?:\s|$)') {
        # Windows venv launchers can leave a child interpreter serving port 8010.
        Get-CimInstance Win32_Process -Filter "ParentProcessId = $demoProcessId" | Where-Object {
            $_.CommandLine -match '\-m\s+benchmarks\.failure_demo\.controller(?:\s|$)'
        } | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
        Stop-Process -Id $demoProcessId
    } elseif ($demoProcess) { throw 'Saved PID no longer belongs to this failure controller; refusing to stop it.' }
    else {
        Get-CimInstance Win32_Process -Filter "ParentProcessId = $demoProcessId" | Where-Object {
            $_.CommandLine -match '\-m\s+benchmarks\.failure_demo\.controller(?:\s|$)'
        } | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
    }
}
& (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') -m benchmarks.failure_demo.setup disable
if ($LASTEXITCODE -ne 0) { throw 'Hook support could not be disabled; no data or volume was removed.' }
Write-Host 'Failure controller stopped, faults recovered and local hook support disabled. Prototype services remain available.'
