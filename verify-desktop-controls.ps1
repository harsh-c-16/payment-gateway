[CmdletBinding()]
param([double]$MaxClockErrorMs = 500)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location -LiteralPath $PSScriptRoot
& (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') -m benchmarks.windows.evidence --max-clock-error-ms $MaxClockErrorMs
if ($LASTEXITCODE -ne 0) { throw 'Resource/clock verification failed; inspect artifacts/windows/live-controls.json.' }
