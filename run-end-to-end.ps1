[CmdletBinding()]
param([ValidateRange(1,3)][int]$Repetitions=3,
      [ValidateRange(1,20)][int]$Searches=3,
      [switch]$KeepRunning)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
Set-Location -LiteralPath $PSScriptRoot
$e2ePython=Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
& $e2ePython -c 'from benchmarks.windows.evidence import desktop_only; desktop_only()'
if ($LASTEXITCODE -ne 0) { throw 'Use the prepared Windows Desktop checkout.' }
try {
    & $e2ePython -m benchmarks.failure_demo.setup enable
    if ($LASTEXITCODE -ne 0) { throw 'Start the prototype before running end-to-end measurements.' }
    Write-Host "Running $($Repetitions*2) explicitly authorized simulated purchases with real HTTP/Kafka/Gold observations."
    & $e2ePython -m benchmarks.windows.end_to_end --simulate-purchases --repetitions $Repetitions --searches $Searches
    if ($LASTEXITCODE -ne 0) { throw 'End-to-end run failed; retained evidence records unresolved work.' }
} finally {
    try {
        & $e2ePython -m benchmarks.failure_demo.setup disable
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Hook disable failed; inspect retained evidence.' }
    } finally {
        if (!$KeepRunning) { & (Join-Path $PSScriptRoot 'stop-prototype.ps1') }
    }
}
