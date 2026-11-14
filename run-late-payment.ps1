[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location -LiteralPath $PSScriptRoot
$latePython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
$lateEvidence = 'artifacts/windows/late-' + [Guid]::NewGuid().ToString('N')
& $latePython -c 'from benchmarks.windows.evidence import desktop_only; desktop_only()'
if ($LASTEXITCODE -ne 0) { throw 'Use the Windows Desktop checkout.' }
try {
    & (Join-Path $PSScriptRoot 'verify-desktop-controls.ps1')
    & $latePython -m benchmarks.failure_demo.setup enable
    if ($LASTEXITCODE -ne 0) { throw 'Could not enable scoped payment hooks.' }
    & $latePython -m benchmarks.manual.verify_failure_demo --simulate-purchases --scenario late --out $lateEvidence
    if ($LASTEXITCODE -ne 0) { throw 'Late-payment reconciliation failed; inspect the retained evidence.' }
} finally {
    try {
        & $latePython -m benchmarks.failure_demo.setup disable
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Hook disable failed; containers will still be removed.' }
    } finally {
        & (Join-Path $PSScriptRoot 'stop-prototype.ps1')
    }
}
Write-Host "35-second expiry/cancellation verified. Evidence: $lateEvidence. Project containers removed; volumes retained."
